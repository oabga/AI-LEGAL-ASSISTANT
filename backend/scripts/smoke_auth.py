"""Smoke test auth + conversations bằng ASGI transport, không cần chạy server.

Dùng httpx.ASGITransport nên không đụng tới lifespan (bỏ qua bước dựng index
retrieval tốn thời gian), chỉ kiểm tra phần DB và JWT.
"""
from __future__ import annotations

import asyncio
import uuid

import httpx
from fastapi import FastAPI

from src.core.rate_limit import install_rate_limiter
from src.config import get_settings
from src.routers import auth_router, conversations_router


def build_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = get_settings()
    install_rate_limiter(app, app.state.settings)
    app.include_router(auth_router)
    app.include_router(conversations_router)
    return app


async def main() -> int:
    app = build_app()
    suffix = uuid.uuid4().hex[:8]
    email = f"smoke-{suffix}@example.com"
    password = "SmokeTest#2026"
    # Mã số thuế phải khác nhau mỗi lần chạy vì organizations.tax_code là unique.
    tax_code = f"01{uuid.uuid4().int % 10**8:08d}"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": "Người Dùng Smoke",
                "role": "owner",
                "organization": {
                    "name": "Công ty TNHH Smoke Test",
                    "tax_code": tax_code,
                    "business_type": "llc",
                    "employee_count": 12,
                    "vat_period": "quarterly",
                },
            },
        )
        assert response.status_code == 201, (response.status_code, response.text)
        body = response.json()
        print("register ->", response.status_code, body["user"]["email"], body["user"]["role"])

        # Trùng email phải bị chặn.
        duplicate = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Trùng"},
        )
        assert duplicate.status_code == 409, (duplicate.status_code, duplicate.text)
        print("duplicate email ->", duplicate.status_code)

        # Trùng mã số thuế phải ra 409 có thông báo, không phải 500.
        duplicate_tax = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"tax-{email}",
                "password": password,
                "full_name": "Trùng MST",
                "organization": {"name": "Công ty khác", "tax_code": tax_code},
            },
        )
        assert duplicate_tax.status_code == 409, (duplicate_tax.status_code, duplicate_tax.text)
        print("duplicate tax code ->", duplicate_tax.status_code, duplicate_tax.json()["detail"])

        # Mật khẩu yếu phải bị chặn.
        weak = await client.post(
            "/api/v1/auth/register",
            json={"email": f"weak-{email}", "password": "123456", "full_name": "Yếu"},
        )
        assert weak.status_code == 422, (weak.status_code, weak.text)
        print("weak password ->", weak.status_code)

        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert login.status_code == 200, (login.status_code, login.text)
        tokens = login.json()["tokens"]
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        print("login ->", login.status_code)

        bad_login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "SaiMatKhau#1"}
        )
        assert bad_login.status_code == 401, bad_login.status_code
        print("wrong password ->", bad_login.status_code)

        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200, me.text
        print("me ->", me.status_code, me.json()["organization"]["name"])

        anon = await client.get("/api/v1/conversations")
        assert anon.status_code == 401, anon.status_code
        print("conversations without token ->", anon.status_code)

        refreshed = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refreshed.status_code == 200, refreshed.text
        print("refresh ->", refreshed.status_code)

        # Refresh token không được dùng như access token.
        misuse = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
        )
        assert misuse.status_code == 401, misuse.status_code
        print("refresh token as access ->", misuse.status_code)

        created = await client.post(
            "/api/v1/conversations", json={"title": "Hỏi về thuế GTGT"}, headers=headers
        )
        assert created.status_code == 201, created.text
        conversation_id = created.json()["id"]
        print("create conversation ->", created.status_code, created.json()["title"])

        listing = await client.get("/api/v1/conversations", headers=headers)
        assert listing.status_code == 200, listing.text
        print("list conversations ->", listing.json()["total"])

        renamed = await client.patch(
            f"/api/v1/conversations/{conversation_id}",
            json={"title": "Thuế GTGT theo quý"},
            headers=headers,
        )
        assert renamed.status_code == 200, renamed.text
        print("rename ->", renamed.json()["title"])

        messages = await client.get(
            f"/api/v1/conversations/{conversation_id}/messages", headers=headers
        )
        assert messages.status_code == 200, messages.text
        print("messages ->", messages.status_code, len(messages.json()))

        # Người khác không được đọc hội thoại này.
        other = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"other-{email}",
                "password": password,
                "full_name": "Người Khác",
            },
        )
        assert other.status_code == 201, other.text
        other_headers = {"Authorization": f"Bearer {other.json()['tokens']['access_token']}"}
        forbidden = await client.get(
            f"/api/v1/conversations/{conversation_id}", headers=other_headers
        )
        assert forbidden.status_code == 404, forbidden.status_code
        print("cross-user access ->", forbidden.status_code)

        deleted = await client.delete(
            f"/api/v1/conversations/{conversation_id}", headers=headers
        )
        assert deleted.status_code == 204, deleted.status_code
        print("delete ->", deleted.status_code)

    await cleanup(email)
    print("\nSMOKE OK")
    return 0


async def cleanup(email: str) -> None:
    """Xóa dữ liệu smoke test để chạy lại được nhiều lần."""

    from sqlalchemy import delete, select

    from src.core.database import get_session_factory
    from src.models import Organization, User

    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(User.id, User.organization_id).where(User.email.like(f"%{email}"))
            )
        ).all()
        user_ids = [row[0] for row in rows]
        org_ids = [row[1] for row in rows if row[1] is not None]
        if user_ids:
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        if org_ids:
            await session.execute(delete(Organization).where(Organization.id.in_(org_ids)))
        await session.commit()
        print(f"cleanup -> {len(user_ids)} user, {len(org_ids)} organization")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
