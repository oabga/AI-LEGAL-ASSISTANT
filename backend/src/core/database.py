"""SQLAlchemy async engine + session factory cho dữ liệu ứng dụng.

Corpus pháp luật (``legal_knowledge_records``) vẫn được index_builder đọc bằng
asyncpg thuần vì đó là đường đọc hàng loạt lúc startup. Mọi bảng nghiệp vụ khác
(users, conversations, documents, compliance...) đi qua ORM ở đây.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from src.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class cho toàn bộ ORM model."""


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Engine dùng chung cho cả process."""

    config = get_settings().legal_assistant.postgres
    url = config.async_database_url
    # SQLite (dùng trong test) không hỗ trợ tham số pool của PostgreSQL.
    if url.startswith("sqlite"):
        return create_async_engine(url, echo=config.echo_sql, poolclass=NullPool)
    return create_async_engine(
        url,
        echo=config.echo_sql,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Session factory; ``expire_on_commit=False`` để đọc field sau commit."""

    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: mở session, commit khi thành công, rollback khi lỗi."""

    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def verify_connection() -> None:
    """Kiểm tra kết nối DB lúc startup để lỗi cấu hình lộ ra sớm."""

    from sqlalchemy import text

    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Kết nối PostgreSQL thành công")
    except Exception as exc:
        raise RuntimeError(
            "Không kết nối được PostgreSQL. Kiểm tra LEGAL_DATABASE_URL trong backend/.env "
            "và chắc chắn container postgres đang chạy. Chi tiết: " + str(exc)
        ) from exc


async def dispose_engine() -> None:
    """Đóng connection pool khi app shutdown."""

    await get_engine().dispose()
