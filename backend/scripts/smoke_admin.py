"""Smoke test API admin: thống kê corpus, phân quyền, quản lý user."""
from __future__ import annotations

import asyncio
import uuid

import httpx
from fastapi import FastAPI

from src.config import get_settings
from src.core.rate_limit import install_rate_limiter
from src.routers import admin_router, auth_router, lab_router


def build_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = get_settings()
    install_rate_limiter(app, app.state.settings)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(lab_router)
    return app


async def promote(email: str) -> None:
    """Nâng quyền admin trực tiếp trong DB (hệ thống đã có admin từ trước)."""

    from sqlalchemy import update

    from src.core.database import get_session_factory
    from src.models import User, UserRole

    async with get_session_factory()() as session:
        await session.execute(
            update(User).where(User.email == email).values(role=UserRole.ADMIN)
        )
        await session.commit()


async def main() -> int:
    app = build_app()
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    user_email = f"member-{uuid.uuid4().hex[:8]}@example.com"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as client:
        password = "SmokeTest#2026"
        for email, role in ((admin_email, "owner"), (user_email, "accountant")):
            created = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "full_name": "Người Dùng",
                    "role": role,
                },
            )
            assert created.status_code == 201, created.text

        await promote(admin_email)
        admin_login = await client.post(
            "/api/v1/auth/login", json={"email": admin_email, "password": password}
        )
        assert admin_login.json()["user"]["role"] == "admin", admin_login.json()["user"]
        admin_headers = {
            "Authorization": f"Bearer {admin_login.json()['tokens']['access_token']}"
        }
        member_login = await client.post(
            "/api/v1/auth/login", json={"email": user_email, "password": password}
        )
        member_headers = {
            "Authorization": f"Bearer {member_login.json()['tokens']['access_token']}"
        }

        # Người dùng thường không được vào admin hay lab.
        for path in ("/api/v1/admin/corpus/stats", "/api/v1/admin/users"):
            denied = await client.get(path, headers=member_headers)
            assert denied.status_code == 403, (path, denied.status_code)
        lab_denied = await client.post("/api/v1/lab/batch", json={"items": []}, headers=member_headers)
        assert lab_denied.status_code == 403, lab_denied.status_code
        print("non-admin -> 403 trên admin + lab")

        anon = await client.get("/api/v1/admin/corpus/stats")
        assert anon.status_code == 401, anon.status_code
        print("không token -> 401")

        stats = await client.get("/api/v1/admin/corpus/stats", headers=admin_headers)
        assert stats.status_code == 200, stats.text
        data = stats.json()
        print(
            f"corpus stats -> {data['total_articles']} điều, {data['total_laws']} văn bản,"
            f" index_ready={data['index_ready']} ({data['indexed_vectors']} vector),"
            f" model={data['embedding_model']}"
        )
        print("  theo loại:", data["by_doc_type"])
        print("  top 3 văn bản:")
        for law in data["largest_laws"][:3]:
            print(f"    {law['law_id']} [{law['category']}] {law['article_count']} điều")
        assert data["total_articles"] > 0 and data["total_laws"] > 0

        # Import file JSON sai cấu trúc phải bị chặn với thông báo rõ ràng.
        import io

        bad = await client.post(
            "/api/v1/admin/corpus/import",
            files={"file": ("bad.json", io.BytesIO(b"{not json"), "application/json")},
            headers=admin_headers,
        )
        assert bad.status_code == 400, bad.status_code
        print("import JSON lỗi ->", bad.status_code, bad.json()["detail"][:45])

        missing_field = await client.post(
            "/api/v1/admin/corpus/import",
            files={
                "file": (
                    "x.json",
                    io.BytesIO(b'[{"id": 1, "law_id": "X"}]'),
                    "application/json",
                )
            },
            headers=admin_headers,
        )
        assert missing_field.status_code == 400, missing_field.status_code
        print("import thiếu field ->", missing_field.status_code, missing_field.json()["detail"][:55])

        users = await client.get("/api/v1/admin/users", headers=admin_headers)
        assert users.status_code == 200, users.text
        print("list users ->", users.json()["total"])

        found = await client.get(
            "/api/v1/admin/users", params={"q": user_email.split("@")[0]}, headers=admin_headers
        )
        assert found.json()["total"] == 1, found.json()
        target = found.json()["items"][0]
        print("tìm user ->", target["email"], target["role"])

        promoted = await client.patch(
            f"/api/v1/admin/users/{target['id']}",
            json={"role": "hr", "is_active": False},
            headers=admin_headers,
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["role"] == "hr" and promoted.json()["is_active"] is False
        print("đổi role + vô hiệu hóa ->", promoted.json()["role"], promoted.json()["is_active"])

        # Tài khoản bị vô hiệu hóa không đăng nhập được nữa.
        blocked = await client.post(
            "/api/v1/auth/login", json={"email": user_email, "password": password}
        )
        assert blocked.status_code == 403, blocked.status_code
        print("login tài khoản đã khóa ->", blocked.status_code)

        # Admin không được tự hạ quyền chính mình.
        self_edit = await client.patch(
            f"/api/v1/admin/users/{admin_login.json()['user']['id']}",
            json={"role": "owner"},
            headers=admin_headers,
        )
        assert self_edit.status_code == 400, self_edit.status_code
        print("admin tự đổi quyền ->", self_edit.status_code)

        ghost = await client.patch(
            f"/api/v1/admin/users/{uuid.uuid4()}",
            json={"is_active": True},
            headers=admin_headers,
        )
        assert ghost.status_code == 404, ghost.status_code
        print("user không tồn tại ->", ghost.status_code)

    await cleanup([admin_email, user_email])
    print("\nSMOKE OK")
    return 0


async def cleanup(emails: list[str]) -> None:
    from sqlalchemy import delete

    from src.core.database import get_session_factory
    from src.models import User

    async with get_session_factory()() as session:
        await session.execute(delete(User).where(User.email.in_(emails)))
        await session.commit()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
