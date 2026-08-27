"""Hội thoại và tin nhắn - thay cho lịch sử chỉ nằm trong RAM ở bản gốc."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Identity, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid as SAUuid

from src.core.database import Base
from src.models.enums import MessageRole
from src.models.mixins import JSONBType, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from src.models.user import User


class Conversation(Base, TimestampMixin):
    """Một đoạn chat của người dùng."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="Cuộc trò chuyện mới", nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.seq",
    )

    __table_args__ = (
        # Sidebar luôn liệt kê theo thời gian cập nhật giảm dần.
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
    )


class Message(Base, TimestampMixin):
    """Một tin nhắn. Với assistant, lưu kèm trích dẫn và trace pipeline."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Không sắp xếp theo created_at: câu hỏi và câu trả lời thường được ghi trong
    # cùng một transaction, mà now() của PostgreSQL trả về thời điểm bắt đầu
    # transaction nên hai message có created_at bằng nhau và thứ tự hội thoại
    # thành ngẫu nhiên. Sequence này cho thứ tự chèn tuyệt đối.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # relevant_articles dạng "law_id|law_name|Điều X" để UI dựng link tra cứu.
    citations: Mapped[list[str]] = mapped_column(JSONBType, default=list, nullable=False)
    relevant_docs: Mapped[list[str]] = mapped_column(JSONBType, default=list, nullable=False)
    # Trace các stage của LangGraph, dùng để hiển thị lại "quá trình suy luận".
    trace: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
