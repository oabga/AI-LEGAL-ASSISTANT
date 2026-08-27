"""Audit log cho các hành động thay đổi dữ liệu."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid as SAUuid

from src.core.database import Base
from src.models.mixins import JSONBType, TimestampMixin, uuid_pk


class AuditLog(Base, TimestampMixin):
    """Ghi lại ai làm gì, trên tài nguyên nào."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Giữ log lại kể cả khi user bị xóa.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict, nullable=False)

    __table_args__ = (Index("ix_audit_logs_action_created", "action", "created_at"),)
