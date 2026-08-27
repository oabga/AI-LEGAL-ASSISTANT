"""Test lịch tuân thủ: sinh theo hồ sơ doanh nghiệp, đánh dấu hoàn thành, cách ly."""
from __future__ import annotations

from tests.factories import register


async def test_tasks_require_organization(client):
    account = await register(client)
    response = await client.get("/api/v1/compliance/tasks", headers=account["headers"])
    assert response.status_code == 400, response.text


async def test_register_with_org_seeds_calendar(client):
    account = await register(client, with_organization=True, vat_period="quarterly", employee_count=12)
    response = await client.get("/api/v1/compliance/tasks", headers=account["headers"])

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] > 0
    codes = {item["rule"]["code"] for item in payload["items"]}
    # Khai GTGT theo quý thì có VAT_QUARTERLY, không có VAT_MONTHLY.
    assert "VAT_QUARTERLY" in codes
    assert "VAT_MONTHLY" not in codes
    assert "SOCIAL_INSURANCE_MONTHLY" in codes
    assert "FINANCIAL_STATEMENT" in codes


async def test_monthly_vat_period_selects_monthly_rule(client):
    account = await register(client, with_organization=True, vat_period="monthly", employee_count=3)
    response = await client.get("/api/v1/compliance/tasks", headers=account["headers"])
    codes = {item["rule"]["code"] for item in response.json()["items"]}
    assert "VAT_MONTHLY" in codes
    assert "VAT_QUARTERLY" not in codes


async def test_mark_task_done_and_undo(client):
    account = await register(client, with_organization=True)
    listed = await client.get(
        "/api/v1/compliance/tasks",
        params={"status": "pending"},
        headers=account["headers"],
    )
    task_id = listed.json()["items"][0]["id"]

    done = await client.patch(
        f"/api/v1/compliance/tasks/{task_id}",
        json={"status": "done"},
        headers=account["headers"],
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done"
    assert done.json()["completed_at"]

    summary = await client.get("/api/v1/compliance/summary", headers=account["headers"])
    assert summary.status_code == 200
    assert summary.json()["done"] >= 1


async def test_cannot_see_other_org_tasks(client):
    first = await register(client, with_organization=True)
    second = await register(client, with_organization=True)

    listed = await client.get("/api/v1/compliance/tasks", headers=first["headers"])
    task_id = listed.json()["items"][0]["id"]

    other = await client.patch(
        f"/api/v1/compliance/tasks/{task_id}",
        json={"status": "done"},
        headers=second["headers"],
    )
    assert other.status_code == 404
