"""Schema cho API quản trị."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import UserRole


class LawStat(BaseModel):
    law_id: str
    law_name: str
    doc_type: str
    category: str
    article_count: int


class CorpusStats(BaseModel):
    """Số liệu corpus cho trang admin."""

    total_articles: int
    total_laws: int
    by_doc_type: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    largest_laws: list[LawStat] = Field(default_factory=list)
    # Trạng thái vector index tương ứng với corpus hiện tại.
    index_ready: bool = False
    indexed_vectors: int = 0
    embedding_model: str | None = None


class ImportResponse(BaseModel):
    imported: int
    total_articles: int
    total_laws: int
    # Reindex phải chạy sau import, nếu không retrieval vẫn dùng vector cũ.
    reindex_required: bool = True
    message: str


class ReindexResponse(BaseModel):
    status: str
    message: str
    indexed_vectors: int = 0


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    organization_id: uuid.UUID | None = None
    organization_name: str | None = None
    created_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserOut]
    total: int


class UpdateUserRequest(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
