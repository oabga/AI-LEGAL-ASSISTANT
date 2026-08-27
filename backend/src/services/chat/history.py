"""Đọc/ghi hội thoại trong PostgreSQL.

Tách khỏi router để cả đường chat thường và đường SSE dùng chung một logic
persist, tránh tình trạng chỉ một trong hai đường lưu được lịch sử.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models import Conversation, Message, MessageRole, User
from src.schemas.legal import ConversationTurn

logger = logging.getLogger(__name__)

TITLE_MAX_LENGTH = 80


def derive_title(question: str) -> str:
    """Sinh tiêu đề hội thoại từ câu hỏi đầu tiên."""

    cleaned = " ".join(question.split())
    if not cleaned:
        return "Cuộc trò chuyện mới"
    if len(cleaned) <= TITLE_MAX_LENGTH:
        return cleaned
    # Cắt ở khoảng trắng gần nhất để không đứt giữa từ.
    truncated = cleaned[:TITLE_MAX_LENGTH]
    pivot = truncated.rfind(" ")
    if pivot > TITLE_MAX_LENGTH // 2:
        truncated = truncated[:pivot]
    return truncated + "…"


async def get_owned_conversation(
    session: AsyncSession, conversation_id: uuid.UUID, user: User
) -> Conversation:
    """Lấy hội thoại và chặn truy cập chéo giữa các người dùng."""

    conversation = await session.get(Conversation, conversation_id)
    # Trả 404 (không phải 403) để không tiết lộ hội thoại của người khác có tồn tại.
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy cuộc trò chuyện",
        )
    return conversation


async def resolve_conversation(
    session: AsyncSession,
    user: User,
    conversation_id: uuid.UUID | None,
    first_question: str,
) -> Conversation:
    """Lấy hội thoại đang có, hoặc tạo mới với tiêu đề suy ra từ câu hỏi."""

    if conversation_id is not None:
        return await get_owned_conversation(session, conversation_id, user)

    conversation = Conversation(user_id=user.id, title=derive_title(first_question))
    session.add(conversation)
    await session.flush()
    return conversation


async def load_history(
    session: AsyncSession, conversation: Conversation, *, exclude_message_id: uuid.UUID | None = None
) -> list[ConversationTurn]:
    """Nạp N lượt gần nhất của hội thoại để làm short-memory."""

    settings = get_settings().short_memory
    if not settings.enabled:
        return []

    limit = settings.max_turns * 2
    statement = (
        select(Message.role, Message.content)
        .where(Message.conversation_id == conversation.id)
        # seq (không phải created_at) mới cho đúng thứ tự lượt hỏi - đáp.
        .order_by(desc(Message.seq))
        .limit(limit + 1)
    )
    if exclude_message_id is not None:
        statement = statement.where(Message.id != exclude_message_id)

    rows = (await session.execute(statement)).all()
    turns = [
        ConversationTurn(role=str(role), content=content)
        for role, content in reversed(rows)
        if content
    ]
    return turns[-limit:]


async def append_user_message(
    session: AsyncSession, conversation: Conversation, content: str
) -> Message:
    """Lưu câu hỏi của người dùng trước khi chạy agent.

    Ghi trước để câu hỏi không bị mất nếu agent lỗi hoặc client ngắt kết nối.
    """

    message = Message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=content,
    )
    session.add(message)
    conversation.message_count = (conversation.message_count or 0) + 1
    await session.flush()
    return message


async def append_assistant_message(
    session: AsyncSession,
    conversation: Conversation,
    *,
    content: str,
    citations: list[str] | None = None,
    relevant_docs: list[str] | None = None,
    trace: dict[str, Any] | None = None,
) -> Message:
    """Lưu câu trả lời kèm trích dẫn và trace."""

    message = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=content,
        citations=citations or [],
        relevant_docs=relevant_docs or [],
        trace=trace or {},
    )
    session.add(message)
    # Bản thân việc tăng message_count sinh ra một UPDATE, nên onupdate của
    # updated_at tự chạy và hội thoại nhảy lên đầu sidebar.
    conversation.message_count = (conversation.message_count or 0) + 1
    await session.flush()
    return message
