"""Test API hội thoại, bao gồm cách ly dữ liệu giữa các tài khoản."""
from __future__ import annotations

import uuid

import pytest_asyncio

from tests.factories import register


@pytest_asyncio.fixture
async def account(client):
    return await register(client)


@pytest_asyncio.fixture
async def conversation(client, account):
    response = await client.post(
        "/api/v1/conversations",
        json={"title": "Hỏi về thử việc"},
        headers=account["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_list_conversations_requires_auth(client):
    assert (await client.get("/api/v1/conversations")).status_code == 401


async def test_new_account_has_empty_history(client, account):
    response = await client.get("/api/v1/conversations", headers=account["headers"])

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 0
    assert payload["items"] == []


async def test_create_and_fetch_conversation(client, account, conversation):
    response = await client.get(
        f"/api/v1/conversations/{conversation['id']}", headers=account["headers"]
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["title"] == "Hỏi về thử việc"
    assert payload["messages"] == []
    assert payload["archived"] is False


async def test_rename_conversation(client, account, conversation):
    response = await client.patch(
        f"/api/v1/conversations/{conversation['id']}",
        json={"title": "Tên mới"},
        headers=account["headers"],
    )

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Tên mới"


async def test_archive_hides_from_default_list(client, account, conversation):
    archived = await client.patch(
        f"/api/v1/conversations/{conversation['id']}",
        json={"archived": True},
        headers=account["headers"],
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived"] is True

    default_list = await client.get("/api/v1/conversations", headers=account["headers"])
    assert default_list.json()["total"] == 0

    with_archived = await client.get(
        "/api/v1/conversations",
        params={"archived": "true"},
        headers=account["headers"],
    )
    assert with_archived.json()["total"] == 1


async def test_delete_conversation(client, account, conversation):
    deleted = await client.delete(
        f"/api/v1/conversations/{conversation['id']}", headers=account["headers"]
    )
    assert deleted.status_code == 204

    missing = await client.get(
        f"/api/v1/conversations/{conversation['id']}", headers=account["headers"]
    )
    assert missing.status_code == 404


async def test_unknown_conversation_returns_404(client, account):
    response = await client.get(
        f"/api/v1/conversations/{uuid.uuid4()}", headers=account["headers"]
    )
    assert response.status_code == 404


async def test_other_user_cannot_read_conversation(client, account, conversation):
    """Hội thoại chứa câu hỏi pháp lý riêng tư; rò rỉ chéo user là lỗi nặng."""

    intruder = await register(client)

    assert (
        await client.get(
            f"/api/v1/conversations/{conversation['id']}", headers=intruder["headers"]
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            headers=intruder["headers"],
        )
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"title": "Chiếm quyền"},
            headers=intruder["headers"],
        )
    ).status_code == 404
    assert (
        await client.delete(
            f"/api/v1/conversations/{conversation['id']}", headers=intruder["headers"]
        )
    ).status_code == 404


async def test_history_persists_messages_and_orders_them(client, account, conversation, session):
    """Ghi trực tiếp qua service để test lịch sử không phụ thuộc vào LLM."""

    from src.models import Conversation
    from src.services.chat.history import (
        append_assistant_message,
        append_user_message,
        load_history,
    )

    stored = await session.get(Conversation, uuid.UUID(conversation["id"]))
    await append_user_message(session, stored, "Thời gian thử việc tối đa là bao lâu?")
    await append_assistant_message(
        session,
        stored,
        content="Tối đa 180 ngày với người quản lý doanh nghiệp.",
        citations=["test-02/2019/QH14|Bộ luật Lao động Kiểm Thử|Điều 25"],
    )
    await session.commit()

    messages = await client.get(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=account["headers"],
    )
    assert messages.status_code == 200, messages.text
    payload = messages.json()
    assert [item["role"] for item in payload] == ["user", "assistant"]
    assert payload[1]["citations"] == [
        "test-02/2019/QH14|Bộ luật Lao động Kiểm Thử|Điều 25"
    ]

    # Lịch sử nạp cho agent phải giữ đúng thứ tự lượt hỏi - đáp.
    history = await load_history(session, stored)
    assert len(history) == 2
    assert history[0].role == "user"


async def test_message_count_reflects_appended_messages(client, account, conversation, session):
    from src.models import Conversation
    from src.services.chat.history import append_assistant_message, append_user_message

    stored = await session.get(Conversation, uuid.UUID(conversation["id"]))
    await append_user_message(session, stored, "Câu hỏi 1")
    await append_assistant_message(session, stored, content="Trả lời 1")
    await session.commit()

    listed = await client.get("/api/v1/conversations", headers=account["headers"])
    item = listed.json()["items"][0]
    assert item["message_count"] == 2
