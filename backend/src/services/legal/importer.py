"""Nạp corpus pháp luật vào PostgreSQL.

Dùng chung cho CLI (``scripts/load_postgres.py``) và API admin để hai đường không
lệch nhau. Schema do Alembic quản lý; hàm ở đây chỉ ghi dữ liệu, không tạo bảng —
nếu tự tạo bảng thì sẽ mất các generated column (``search_vector``...) và
full-text search im lặng ngừng hoạt động.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {
    "id",
    "law_id",
    "law_name",
    "doc_type",
    "article",
    "article_title",
    "content",
    "author",
}

UPSERT_SQL = """
    INSERT INTO legal_knowledge_records (
        id, law_id, law_name, doc_type, chapter, article,
        article_title, content, author, extra
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
    ON CONFLICT (id) DO UPDATE SET
        law_id = EXCLUDED.law_id,
        law_name = EXCLUDED.law_name,
        doc_type = EXCLUDED.doc_type,
        chapter = EXCLUDED.chapter,
        article = EXCLUDED.article,
        article_title = EXCLUDED.article_title,
        content = EXCLUDED.content,
        author = EXCLUDED.author,
        extra = EXCLUDED.extra
"""


class CorpusValidationError(ValueError):
    """Dataset sai cấu trúc; báo lỗi trước khi ghi bất kỳ dòng nào."""


@dataclass(slots=True)
class ImportResult:
    imported: int = 0
    total_in_table: int = 0
    laws: int = 0
    warnings: list[str] = field(default_factory=list)


def validate_records(payload: Any) -> list[dict]:
    """Kiểm tra cấu trúc dataset và trả về danh sách record đã validate."""

    if not isinstance(payload, list):
        raise CorpusValidationError("Dataset phải là một JSON array")
    if not payload:
        raise CorpusValidationError("Dataset rỗng")

    seen_ids: set[int] = set()
    for index, record in enumerate(payload):
        if not isinstance(record, dict):
            raise CorpusValidationError(f"Record {index} không phải JSON object")
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            raise CorpusValidationError(
                f"Record {index} thiếu field bắt buộc: {sorted(missing)}"
            )
        try:
            record_id = int(record["id"])
        except (TypeError, ValueError) as exc:
            raise CorpusValidationError(f"Record {index} có id không phải số") from exc
        if record_id in seen_ids:
            raise CorpusValidationError(f"ID bị trùng trong dataset: {record_id}")
        seen_ids.add(record_id)
    return payload


def to_row(record: dict) -> tuple:
    """Chuẩn hóa một record thành bộ tham số SQL."""

    return (
        int(record["id"]),
        str(record["law_id"]),
        str(record["law_name"]),
        str(record["doc_type"]),
        record.get("chapter"),
        str(record["article"]),
        str(record["article_title"]),
        str(record["content"]),
        str(record["author"]),
        json.dumps(record.get("extra") or [], ensure_ascii=False),
    )


async def import_records(
    records: Iterable[dict],
    *,
    database_url: str,
    batch_size: int = 256,
    truncate: bool = False,
    progress=None,
) -> ImportResult:
    """Upsert corpus vào PostgreSQL theo batch."""

    import asyncpg

    records = list(records)
    if batch_size < 1:
        raise ValueError("batch_size phải lớn hơn 0")

    conn = await asyncpg.connect(database_url)
    try:
        exists = await conn.fetchval("SELECT to_regclass('legal_knowledge_records')")
        if exists is None:
            raise CorpusValidationError(
                "Bảng legal_knowledge_records chưa tồn tại. "
                "Chạy `alembic upgrade head` trước khi nạp corpus."
            )

        async with conn.transaction():
            if truncate:
                await conn.execute("TRUNCATE TABLE legal_knowledge_records")
            for start in range(0, len(records), batch_size):
                batch = [to_row(record) for record in records[start : start + batch_size]]
                await conn.executemany(UPSERT_SQL, batch)
                done = min(start + batch_size, len(records))
                if progress:
                    progress(done, len(records))

        total = await conn.fetchval("SELECT COUNT(*) FROM legal_knowledge_records")
        laws = await conn.fetchval(
            "SELECT COUNT(DISTINCT law_id) FROM legal_knowledge_records"
        )
    finally:
        await conn.close()

    return ImportResult(imported=len(records), total_in_table=total or 0, laws=laws or 0)
