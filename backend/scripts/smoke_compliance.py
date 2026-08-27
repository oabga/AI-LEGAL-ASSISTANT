"""Smoke test API lịch tuân thủ."""
from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from datetime import date, timedelta

import httpx
from fastapi import FastAPI

from src.config import get_settings
from src.core.rate_limit import install_rate_limiter
from src.routers import auth_router, compliance_router


def build_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = get_settings()
    install_rate_limiter(app, app.state.settings)
    app.include_router(auth_router)
    app.include_router(compliance_router)
    return app


async def main() -> int:
    app = build_app()
    email = f"comp-{uuid.uuid4().hex[:8]}@example.com"
    tax_code = f"02{uuid.uuid4().int % 10**8:08d}"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as client:
        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "SmokeTest#2026",
                "full_name": "Kế Toán",
                "role": "accountant",
                "organization": {
                    "name": "Công ty TNHH Tuân Thủ",
                    "tax_code": tax_code,
                    "business_type": "llc",
                    "employee_count": 25,
                    "vat_period": "quarterly",
                },
            },
        )
        assert registered.status_code == 201, registered.text
        headers = {"Authorization": f"Bearer {registered.json()['tokens']['access_token']}"}

        rules = await client.get("/api/v1/compliance/rules", headers=headers)
        assert rules.status_code == 200, rules.text
        rule_items = rules.json()
        grounded = sum(1 for r in rule_items if r["references"])
        print(f"rules -> {len(rule_items)} nghĩa vụ, {grounded} có căn cứ phân giải được")
        for rule in rule_items[:3]:
            refs = ", ".join(
                f"{ref['law_id']} {ref['article']}" for ref in rule["references"][:2]
            )
            print(f"  [{rule['category']}] {rule['title'][:52]} <- {refs or 'chưa map'}")

        # Đăng ký đã sinh lịch sẵn, dashboard không được rỗng.
        summary = await client.get("/api/v1/compliance/summary", headers=headers)
        assert summary.status_code == 200, summary.text
        data = summary.json()
        print(
            f"summary -> total={data['total']} pending={data['pending']}"
            f" overdue={data['overdue']} due_soon={data['due_soon']}"
        )
        assert data["total"] > 0, "đăng ký xong phải có lịch tuân thủ"
        next_due = data["next_due"]
        print(
            f"  sắp tới: {next_due['rule']['title'][:50]} ({next_due['period_label']})"
            f" hạn {next_due['due_date']}, còn {next_due['days_remaining']} ngày"
        )

        tasks = await client.get("/api/v1/compliance/tasks", headers=headers)
        assert tasks.status_code == 200, tasks.text
        items = tasks.json()["items"]
        print("tasks ->", tasks.json()["total"])
        print("  theo chu kỳ:", dict(Counter(t["rule"]["frequency"] for t in items)))
        print("  theo lĩnh vực:", dict(Counter(t["rule"]["category"] for t in items)))

        # Doanh nghiệp khai thuế theo quý không được nhận nghĩa vụ khai theo tháng.
        codes = {t["rule"]["code"] for t in items}
        assert "VAT_MONTHLY" not in codes, "khai quý mà vẫn sinh nghĩa vụ khai tháng"
        assert "VAT_QUARTERLY" in codes, "thiếu nghĩa vụ khai thuế GTGT theo quý"
        print("  lọc theo vat_period=quarterly -> đúng")

        window = await client.get(
            "/api/v1/compliance/tasks",
            params={
                "from": date.today().isoformat(),
                "to": (date.today() + timedelta(days=60)).isoformat(),
            },
            headers=headers,
        )
        assert window.status_code == 200, window.text
        print("tasks 60 ngày tới ->", window.json()["total"])

        by_category = await client.get(
            "/api/v1/compliance/tasks", params={"category": "Thuế"}, headers=headers
        )
        assert by_category.status_code == 200, by_category.text
        print("tasks category=Thuế ->", by_category.json()["total"])

        task_id = items[0]["id"]
        done = await client.patch(
            f"/api/v1/compliance/tasks/{task_id}",
            json={"status": "done", "notes": "Đã nộp qua eTax"},
            headers=headers,
        )
        assert done.status_code == 200, done.text
        assert done.json()["completed_at"] is not None
        assert done.json()["overdue"] is False, "task đã hoàn thành không được tính quá hạn"
        print("mark done ->", done.json()["status"], done.json()["completed_at"])

        reopened = await client.patch(
            f"/api/v1/compliance/tasks/{task_id}", json={"status": "pending"}, headers=headers
        )
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["completed_at"] is None, "bỏ đánh dấu phải xóa completed_at"
        print("reopen ->", reopened.json()["status"], "completed_at=None")

        # Sinh lại phải idempotent, không nhân bản task.
        before = (await client.get("/api/v1/compliance/summary", headers=headers)).json()["total"]
        again = await client.post("/api/v1/compliance/tasks/generate", headers=headers)
        assert again.status_code == 200, again.text
        assert again.json()["total"] == before, "sinh lại làm phình số task"
        print(f"generate lần 2 -> vẫn {again.json()['total']} task (idempotent)")

        missing = await client.patch(
            f"/api/v1/compliance/tasks/{uuid.uuid4()}", json={"status": "done"}, headers=headers
        )
        assert missing.status_code == 404, missing.status_code
        print("task không tồn tại ->", missing.status_code)

        # Tài khoản chưa gắn doanh nghiệp phải bị chặn với thông báo rõ ràng.
        solo = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"solo-{email}",
                "password": "SmokeTest#2026",
                "full_name": "Chưa Có DN",
            },
        )
        assert solo.status_code == 201, solo.text
        solo_headers = {"Authorization": f"Bearer {solo.json()['tokens']['access_token']}"}
        blocked = await client.get("/api/v1/compliance/summary", headers=solo_headers)
        assert blocked.status_code == 400, blocked.status_code
        print("chưa có doanh nghiệp ->", blocked.status_code)

    await cleanup(email)
    print("\nSMOKE OK")
    return 0


async def cleanup(email: str) -> None:
    from sqlalchemy import delete, select

    from src.core.database import get_session_factory
    from src.models import Organization, User

    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(User.id, User.organization_id).where(User.email.like(f"%{email}"))
            )
        ).all()
        if rows:
            await session.execute(delete(User).where(User.id.in_([r[0] for r in rows])))
        org_ids = [r[1] for r in rows if r[1]]
        if org_ids:
            await session.execute(delete(Organization).where(Organization.id.in_(org_ids)))
        await session.commit()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
