"""Smoke test đường hỏi đáp khi vector index chưa sẵn sàng."""
from __future__ import annotations

from tests.factories import register


async def test_answer_requires_auth(client):
    response = await client.post("/api/v1/legal/answer", json={"question": "Thời gian thử việc?"})
    assert response.status_code == 401


async def test_answer_unavailable_without_index(client):
    account = await register(client)
    response = await client.post(
        "/api/v1/legal/answer",
        json={"question": "Thời gian thử việc tối đa với nhân viên chính thức?"},
        headers=account["headers"],
    )
    assert response.status_code == 503, response.text
    detail = response.json()["detail"].lower()
    assert "chỉ mục" in detail or "hỏi đáp" in detail


async def test_chat_unavailable_without_index(client):
    account = await register(client)
    response = await client.post(
        "/api/v1/legal/chat",
        json={"message": "Mức phạt chậm đóng BHXH?"},
        headers=account["headers"],
    )
    assert response.status_code == 503, response.text
