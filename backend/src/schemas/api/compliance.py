"""Schema cho API lịch tuân thủ."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import ComplianceFrequency, ComplianceStatus
from src.schemas.api.law import ArticleRef


class ComplianceRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    title: str
    description: str | None = None
    frequency: ComplianceFrequency
    category: str
    legal_refs: list[str] = Field(default_factory=list)


class ComplianceTaskOut(BaseModel):
    id: uuid.UUID
    period_label: str
    due_date: date
    status: ComplianceStatus
    completed_at: date | None = None
    notes: str | None = None
    rule: ComplianceRuleOut
    # Số ngày còn lại; âm nghĩa là đã quá hạn.
    days_remaining: int
    overdue: bool


class ComplianceTaskListResponse(BaseModel):
    items: list[ComplianceTaskOut]
    total: int


class ComplianceSummary(BaseModel):
    """Số liệu cho dashboard."""

    total: int
    pending: int
    done: int
    skipped: int
    overdue: int
    # Đến hạn trong 30 ngày tới và chưa hoàn thành.
    due_soon: int
    next_due: ComplianceTaskOut | None = None


class UpdateTaskRequest(BaseModel):
    status: ComplianceStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


class RuleDetail(ComplianceRuleOut):
    """Nghĩa vụ kèm căn cứ pháp lý đã phân giải thành Điều luật thật."""

    references: list[ArticleRef] = Field(default_factory=list)
