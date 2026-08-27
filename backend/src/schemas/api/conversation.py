"""Schema cho API quản lý hội thoại."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import MessageRole


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    citations: list[str] = Field(default_factory=list)
    relevant_docs: list[str] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    archived: bool
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    items: list[ConversationOut]
    total: int


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    archived: bool | None = None
