"""Nghĩa vụ tuân thủ định kỳ và lịch nhắc theo từng doanh nghiệp."""
from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid as SAUuid

from src.core.database import Base
from src.models.enums import ComplianceFrequency, ComplianceStatus
from src.models.mixins import JSONBType, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from src.models.user import Organization


class ComplianceRule(Base, TimestampMixin):
    """Định nghĩa một nghĩa vụ tuân thủ, dùng chung cho mọi doanh nghiệp.

    Bảng này được seed từ ``src/services/compliance/seed.py`` và có thể chỉnh
    qua trang admin. ``applies_to`` là điều kiện lọc theo hồ sơ doanh nghiệp.
    """

    __tablename__ = "compliance_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[ComplianceFrequency] = mapped_column(String(16), nullable=False)
    # Ngày/tháng đến hạn tính từ mốc kỳ. Ví dụ khai thuế GTGT quý: day=30,
    # month_offset=1 nghĩa là ngày 30 của tháng đầu quý sau.
    due_day: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    due_month_offset: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Cố định tháng đến hạn với nghĩa vụ theo năm (ví dụ quyết toán TNDN: tháng 3).
    due_fixed_month: Mapped[int | None] = mapped_column(Integer)
    # Căn cứ pháp lý dạng "law_id|law_name|Điều X".
    legal_refs: Mapped[list[str]] = mapped_column(JSONBType, default=list, nullable=False)
    # Điều kiện áp dụng, ví dụ {"vat_period": "quarterly"} hoặc {"min_employees": 10}.
    applies_to: Mapped[dict] = mapped_column(JSONBType, default=dict, nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="Khác", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tasks: Mapped[list[ComplianceTask]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )


class ComplianceTask(Base, TimestampMixin):
    """Một lần đến hạn cụ thể của nghĩa vụ, gắn với một doanh nghiệp."""

    __tablename__ = "compliance_tasks"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compliance_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nhãn kỳ: "2026-Q1", "2026-03", "2026".
    period_label: Mapped[str] = mapped_column(String(16), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[ComplianceStatus] = mapped_column(
        String(16), default=ComplianceStatus.PENDING, nullable=False
    )
    completed_at: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    organization: Mapped[Organization] = relationship(back_populates="compliance_tasks")
    rule: Mapped[ComplianceRule] = relationship(back_populates="tasks")

    __table_args__ = (
        # Sinh lịch là thao tác idempotent: một nghĩa vụ chỉ có một task mỗi kỳ.
        UniqueConstraint("organization_id", "rule_id", "period_label", name="uq_compliance_task_period"),
        Index("ix_compliance_tasks_org_due", "organization_id", "due_date"),
    )
