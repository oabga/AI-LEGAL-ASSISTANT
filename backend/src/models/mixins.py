"""Mixin và type dùng lại giữa các ORM model."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator
from sqlalchemy.types import Uuid as SAUuid


class JSONBType(TypeDecorator):
    """JSONB trên PostgreSQL, JSON thường trên SQLite khi chạy test."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


def uuid_pk() -> Mapped[uuid.UUID]:
    """Khóa chính UUID sinh ở phía Python để biết id trước khi insert."""

    return mapped_column(SAUuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Thêm ``created_at``/``updated_at`` do database tự quản lý."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
