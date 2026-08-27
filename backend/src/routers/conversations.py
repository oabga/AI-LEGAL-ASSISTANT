"""CRUD hội thoại cho sidebar lịch sử chat."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from src.core.deps import CurrentUser, SessionDep
from src.models import Conversation, Message
from src.schemas.api.conversation import (
    ConversationDetail,
    ConversationListResponse,
    ConversationOut,
    CreateConversationRequest,
    MessageOut,
    UpdateConversationRequest,
)
from src.services.chat.history import get_owned_conversation

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    user: CurrentUser,
    session: SessionDep,
    archived: bool = Query(default=False, description="Lọc theo trạng thái lưu trữ"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ConversationListResponse:
    """Danh sách hội thoại, mới cập nhật xếp trước."""

    conditions = [Conversation.user_id == user.id, Conversation.archived.is_(archived)]
    total = await session.scalar(
        select(func.count()).select_from(Conversation).where(*conditions)
    )
    rows = (
        await session.execute(
            select(Conversation)
            .where(*conditions)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return ConversationListResponse(
        items=[ConversationOut.model_validate(row) for row in rows],
        total=total or 0,
    )


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: CreateConversationRequest, user: CurrentUser, session: SessionDep
) -> ConversationOut:
    """Tạo hội thoại rỗng.

    Thường không cần gọi: endpoint chat tự tạo hội thoại khi ``conversation_id``
    để trống. Hữu ích khi UI muốn mở sẵn một đoạn chat mới.
    """

    conversation = Conversation(
        user_id=user.id,
        title=(payload.title or "Cuộc trò chuyện mới").strip(),
    )
    session.add(conversation)
    await session.flush()
    return ConversationOut.model_validate(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ConversationDetail:
    """Chi tiết hội thoại kèm toàn bộ tin nhắn."""

    await get_owned_conversation(session, conversation_id, user)
    result = await session.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one()
    return ConversationDetail.model_validate(conversation)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[MessageOut]:
    """Tin nhắn của một hội thoại theo thứ tự thời gian."""

    await get_owned_conversation(session, conversation_id, user)
    rows = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.seq)
        )
    ).scalars().all()
    return [MessageOut.model_validate(row) for row in rows]


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: UpdateConversationRequest,
    user: CurrentUser,
    session: SessionDep,
) -> ConversationOut:
    """Đổi tên hoặc lưu trữ/bỏ lưu trữ hội thoại."""

    conversation = await get_owned_conversation(session, conversation_id, user)
    if payload.title is not None:
        conversation.title = payload.title.strip()
    if payload.archived is not None:
        conversation.archived = payload.archived
    await session.flush()
    # UPDATE làm updated_at (onupdate=now()) bị expire, phải nạp lại trước khi
    # serialize nếu không sẽ lazy-load ngoài greenlet của SQLAlchemy async.
    await session.refresh(conversation)
    return ConversationOut.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    """Xóa hội thoại và toàn bộ tin nhắn của nó."""

    await get_owned_conversation(session, conversation_id, user)
    await session.execute(delete(Conversation).where(Conversation.id == conversation_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
