"""Tài liệu tải lên và kết quả soát xét rủi ro hợp đồng."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid as SAUuid

from src.core.database import Base
from src.models.enums import DocumentStatus, ReviewStatus, RiskLevel
from src.models.mixins import JSONBType, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from src.models.user import Organization


class Document(Base, TimestampMixin):
    """File hợp đồng do người dùng tải lên."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        String(16), default=DocumentStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text)

    organization: Mapped[Organization | None] = relationship(back_populates="documents")
    reviews: Mapped[list[ContractReview]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="ContractReview.created_at"
    )


class ContractReview(Base, TimestampMixin):
    """Một lần soát xét hợp đồng."""

    __tablename__ = "contract_reviews"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ReviewStatus] = mapped_column(
        String(16), default=ReviewStatus.PENDING, nullable=False
    )
    # 0-100, tổng hợp từ trọng số mức rủi ro của các finding.
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    clause_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    document: Mapped[Document] = relationship(back_populates="reviews")
    findings: Mapped[list[ContractFinding]] = relationship(
        back_populates="review", cascade="all, delete-orphan", order_by="ContractFinding.position"
    )


class ContractFinding(Base):
    """Một phát hiện rủi ro trên một điều khoản, kèm căn cứ pháp lý."""

    __tablename__ = "contract_findings"

    id: Mapped[uuid.UUID] = uuid_pk()
    review_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("contract_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clause_title: Mapped[str | None] = mapped_column(String(255))
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(String(16), nullable=False)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str | None] = mapped_column(Text)
    # Danh sách "law_id|law_name|Điều X" lấy từ retrieval để người dùng kiểm chứng.
    legal_refs: Mapped[list[str]] = mapped_column(JSONBType, default=list, nullable=False)

    review: Mapped[ContractReview] = relationship(back_populates="findings")
