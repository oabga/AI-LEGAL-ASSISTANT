"""Mapping ORM cho corpus pháp luật.

Bảng ``legal_knowledge_records`` giữ đúng schema cũ để pipeline index (asyncpg
thuần) không phải thay đổi. Mapping này chỉ phục vụ tra cứu qua API: liệt kê
văn bản, dựng cây Chương/Điều và full-text search.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Computed, Date, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.models.mixins import JSONBType, TimestampMixin

# Giữ đồng bộ với alembic/versions/b8b045705028_baseline_schema.py.
ARTICLE_NUMBER_EXPR = "NULLIF(substring(article from '[0-9]+'), '')::bigint"
DOC_REF_EXPR = "law_id || '|' || law_name"
SEARCH_VECTOR_EXPR = (
    "setweight(to_tsvector('simple', immutable_unaccent(coalesce(article_title, ''))), 'A') || "
    "setweight(to_tsvector('simple', immutable_unaccent(coalesce(law_name, ''))), 'B') || "
    "setweight(to_tsvector('simple', immutable_unaccent(coalesce(article, ''))), 'B') || "
    "setweight(to_tsvector('simple', immutable_unaccent(coalesce(content, ''))), 'C')"
)


class LegalKnowledgeRecord(Base):
    """Một Điều luật đã chuẩn hóa."""

    __tablename__ = "legal_knowledge_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    law_id: Mapped[str] = mapped_column(Text, nullable=False)
    law_name: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    chapter: Mapped[str | None] = mapped_column(Text)
    article: Mapped[str] = mapped_column(Text, nullable=False)
    article_title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    extra: Mapped[list[str]] = mapped_column(JSONBType, default=list, nullable=False)

    # Ba cột dưới đây là generated column: PostgreSQL tự tính, không insert được,
    # nên không bao giờ lệch so với dữ liệu gốc.
    #
    # Thứ tự Điều trong văn bản; "Điều 10" phải đứng sau "Điều 9" chứ không
    # sort theo chuỗi.
    article_number: Mapped[int | None] = mapped_column(
        BigInteger, Computed(ARTICLE_NUMBER_EXPR, persisted=True)
    )
    doc_ref: Mapped[str | None] = mapped_column(
        String(512), Computed(DOC_REF_EXPR, persisted=True)
    )
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR_EXPR, persisted=True)
    )

    __table_args__ = (
        Index("idx_legal_knowledge_reference", "law_id", "article"),
        Index("idx_legal_knowledge_law_order", "law_id", "article_number"),
        Index("idx_legal_search_vector", "search_vector", postgresql_using="gin"),
        # Trigram để cứu truy vấn gõ sai/thiếu dấu mà full-text không khớp token.
        Index(
            "idx_legal_title_trgm",
            text("immutable_unaccent(article_title) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        Index(
            "idx_legal_law_name_trgm",
            text("immutable_unaccent(law_name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    @property
    def article_ref(self) -> str:
        """Reference đầy đủ: ``law_id|law_name|Điều X``."""

        return f"{self.law_id}|{self.law_name}|{self.article}"


class Law(Base, TimestampMixin):
    """Danh mục văn bản, dẫn xuất từ ``legal_knowledge_records``.

    Bảng riêng vì ``legal_knowledge_records`` là dữ liệu ở mức Điều, không chứa
    được metadata mức văn bản (lĩnh vực, ngày hiệu lực). Được đồng bộ lại mỗi
    lần import corpus nên vẫn coi corpus là nguồn sự thật duy nhất.
    """

    __tablename__ = "laws"

    law_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    law_name: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    issuer: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(64), default="Khác", nullable=False, index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    article_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
