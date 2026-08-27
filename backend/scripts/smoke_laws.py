"""Smoke test API tra cứu văn bản, chạy qua ASGI nên không cần server."""
from __future__ import annotations

import asyncio
import uuid

import httpx
from fastapi import FastAPI

from src.config import get_settings
from src.core.rate_limit import install_rate_limiter
from src.routers import auth_router, laws_router


def build_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = get_settings()
    install_rate_limiter(app, app.state.settings)
    app.include_router(auth_router)
    app.include_router(laws_router)
    return app


async def main() -> int:
    app = build_app()
    email = f"laws-{uuid.uuid4().hex[:8]}@example.com"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as client:
        registered = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "SmokeTest#2026", "full_name": "Tra Cứu"},
        )
        assert registered.status_code == 201, registered.text
        headers = {
            "Authorization": f"Bearer {registered.json()['tokens']['access_token']}"
        }

        listing = await client.get("/api/v1/laws", headers=headers)
        assert listing.status_code == 200, listing.text
        body = listing.json()
        print("laws ->", body["total"], "văn bản")
        print("categories ->", ", ".join(body["categories"]))
        print("doc_types  ->", ", ".join(body["doc_types"]))

        filtered = await client.get("/api/v1/laws?category=Thuế", headers=headers)
        assert filtered.status_code == 200, filtered.text
        print("filter category=Thuế ->", filtered.json()["total"])

        by_name = await client.get("/api/v1/laws?q=doanh nghiep", headers=headers)
        assert by_name.status_code == 200, by_name.text
        print(
            "search tên không dấu 'doanh nghiep' ->",
            [item["law_id"] for item in by_name.json()["items"]][:4],
        )

        law_id = body["items"][0]["law_id"]
        tree = await client.get(f"/api/v1/laws/{law_id}/articles", headers=headers)
        assert tree.status_code == 200, tree.text
        chapters = tree.json()["chapters"]
        print(
            f"tree {law_id} ->",
            len(chapters),
            "chương,",
            sum(len(c["articles"]) for c in chapters),
            "điều",
        )
        print("  chương đầu:", chapters[0]["chapter"])

        article = chapters[0]["articles"][0]["article"]
        detail = await client.get(
            f"/api/v1/laws/{law_id}/articles/{article}", headers=headers
        )
        assert detail.status_code == 200, detail.text
        data = detail.json()
        print(
            f"detail {article} ->",
            data["article_title"],
            "| related:",
            len(data["related"]),
            "| next:",
            data["next_article"],
        )

        missing = await client.get(
            f"/api/v1/laws/{law_id}/articles/Điều 99999", headers=headers
        )
        assert missing.status_code == 404, missing.status_code
        print("điều không tồn tại ->", missing.status_code)

        for query, note in [
            ("thành lập doanh nghiệp", "full-text nhiều từ"),
            ("thue gia tri gia tang", "không dấu"),
            ("Điều 5 Luật Doanh nghiệp", "theo số điều"),
            ("hop dong lao dong", "không dấu, cụm từ"),
            ("bảo hiểm xã hội bắt buộc", "full-text"),
        ]:
            found = await client.get(
                "/api/v1/laws/search", params={"q": query}, headers=headers
            )
            assert found.status_code == 200, found.text
            payload = found.json()
            top = payload["items"][0] if payload["items"] else None
            print(
                f"search {query!r} [{note}] -> {payload['total']} hit,"
                f" strategy={payload['strategy']}"
            )
            if top:
                print(
                    f"    #1 {top['law_id']} {top['article']}: {top['article_title'][:60]}"
                )
            if payload["terms"]:
                print(f"    terms: {payload['terms']}")

        # Truy vấn vô nghĩa vẫn phải trả 200 với danh sách rỗng.
        nonsense = await client.get(
            "/api/v1/laws/search", params={"q": "zzzqqqxxx"}, headers=headers
        )
        assert nonsense.status_code == 200, nonsense.text
        print("truy vấn vô nghĩa ->", nonsense.json()["total"], "hit")

        anon = await client.get("/api/v1/laws")
        assert anon.status_code == 401, anon.status_code
        print("không token ->", anon.status_code)

    await cleanup(email)
    print("\nSMOKE OK")
    return 0


async def cleanup(email: str) -> None:
    from sqlalchemy import delete

    from src.core.database import get_session_factory
    from src.models import User

    async with get_session_factory()() as session:
        await session.execute(delete(User).where(User.email == email))
        await session.commit()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
