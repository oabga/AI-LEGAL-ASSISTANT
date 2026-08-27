"""Schema cho API tài liệu và soát xét hợp đồng."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import DocumentStatus, ReviewStatus, RiskLevel


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: DocumentStatus
    error_message: str | None = None
    created_at: datetime
    # Số ký tự đã trích được, để UI cảnh báo khi file gần như rỗng.
    text_length: int = 0
    latest_review_id: uuid.UUID | None = None


class DocumentListResponse(BaseModel):
    items: list[DocumentOut]
    total: int


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    clause_title: str | None = None
    clause_text: str
    risk_level: RiskLevel
    issue: str
    recommendation: str | None = None
    legal_refs: list[str] = Field(default_factory=list)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    status: ReviewStatus
    risk_score: int
    clause_count: int
    summary: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ReviewDetail(ReviewOut):
    filename: str | None = None
    findings: list[FindingOut] = Field(default_factory=list)
    # Đếm theo mức rủi ro để UI vẽ badge tổng quan.
    risk_counts: dict[str, int] = Field(default_factory=dict)
