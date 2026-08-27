"""Doanh nghiệp và người dùng."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid as SAUuid

from src.core.database import Base
from src.models.enums import UserRole
from src.models.mixins import TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from src.models.chat import Conversation
    from src.models.compliance import ComplianceTask
    from src.models.document import Document


class Organization(Base, TimestampMixin):
    """Doanh nghiệp SME. Hồ sơ này quyết định nghĩa vụ tuân thủ được sinh ra."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_code: Mapped[str | None] = mapped_column(String(32), unique=True)
    business_type: Mapped[str | None] = mapped_column(String(64))
    # Quyết định doanh nghiệp có thuộc diện DNNVV và các mốc báo cáo lao động.
    employee_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Doanh thu năm trước (tỷ đồng) - tiêu chí xác định DNNVV theo Điều 4
    # Luật Hỗ trợ doanh nghiệp nhỏ và vừa.
    annual_revenue_bn: Mapped[float | None] = mapped_column()
    address: Mapped[str | None] = mapped_column(Text)
    # Khai thuế GTGT theo tháng hay theo quý.
    vat_period: Mapped[str] = mapped_column(String(16), default="quarterly", nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="organization")
    documents: Mapped[list[Document]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    compliance_tasks: Mapped[list[ComplianceTask]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(Base, TimestampMixin):
    """Người dùng thuộc một doanh nghiệp."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(32), default=UserRole.OWNER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )

    organization: Mapped[Organization | None] = relationship(back_populates="users")
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
