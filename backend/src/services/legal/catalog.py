"""Đồng bộ bảng danh mục ``laws`` từ corpus đã nạp vào PostgreSQL.

``legal_knowledge_records`` chỉ có dữ liệu ở mức Điều nên không mang được
metadata mức văn bản. Hàm ở đây tổng hợp lại danh sách văn bản từ corpus và
làm giàu thêm lĩnh vực (category) lấy từ ``corpus/law_manifest.json``.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models import Law, LegalKnowledgeRecord

logger = logging.getLogger(__name__)

DEFAULT_CATEGORY = "Khác"

# Suy ra lĩnh vực khi văn bản không có trong manifest (ví dụ corpus được import
# thêm qua trang admin). Kiểm tra theo thứ tự, khớp trên tên văn bản.
CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Thuế", ("thuế", "hóa đơn", "hoá đơn")),
    ("Bảo hiểm xã hội", ("bảo hiểm xã hội", "bảo hiểm y tế", "bảo hiểm thất nghiệp")),
    ("An toàn lao động", ("an toàn, vệ sinh lao động", "an toàn lao động")),
    ("Lao động", ("lao động", "việc làm", "công đoàn")),
    ("Kế toán - Tài chính", ("kế toán", "kiểm toán", "tài chính")),
    ("Doanh nghiệp", ("doanh nghiệp", "đầu tư", "phá sản", "cạnh tranh")),
    ("Dân sự - Hợp đồng", ("dân sự", "thương mại", "trọng tài")),
    ("Sở hữu trí tuệ", ("sở hữu trí tuệ",)),
    ("Đất đai", ("đất đai", "xây dựng", "nhà ở")),
    ("Bảo vệ người tiêu dùng", ("người tiêu dùng", "quảng cáo")),
)


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, dict]:
    """Đọc manifest văn bản, khóa theo ``law_id``.

    Thiếu file không phải lỗi chặn: danh mục vẫn dựng được từ corpus, chỉ là
    lĩnh vực phải suy ra từ tên văn bản.
    """

    path = Path(get_settings().legal_assistant.corpus.manifest_path)
    if not path.is_absolute():
        # Đường dẫn trong config là tương đối với thư mục backend/.
        path = (Path(__file__).resolve().parents[3] / path).resolve()
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("Không đọc được law manifest tại %s (%s); suy ra category từ tên", path, exc)
        return {}
    return {entry["law_id"]: entry for entry in entries if entry.get("law_id")}


def infer_category(law_name: str) -> str:
    """Đoán lĩnh vực từ tên văn bản khi manifest không có."""

    lowered = law_name.lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return DEFAULT_CATEGORY


def _effective_date(entry: dict) -> date | None:
    raw = entry.get("effective_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


async def sync_law_catalog(session: AsyncSession) -> int:
    """Dựng lại bảng ``laws`` từ corpus hiện có. Trả về số văn bản đã ghi.

    Chạy được nhiều lần: upsert theo ``law_id`` và xóa văn bản không còn trong
    corpus, nên gọi lại sau mỗi lần import là an toàn.
    """

    rows = (
        await session.execute(
            select(
                LegalKnowledgeRecord.law_id,
                # Một law_id chỉ có một tên; max() chỉ để thỏa GROUP BY.
                func.max(LegalKnowledgeRecord.law_name).label("law_name"),
                func.max(LegalKnowledgeRecord.doc_type).label("doc_type"),
                func.max(LegalKnowledgeRecord.author).label("author"),
                func.count().label("article_count"),
            ).group_by(LegalKnowledgeRecord.law_id)
        )
    ).all()

    if not rows:
        logger.warning("Corpus rỗng, bỏ qua đồng bộ danh mục văn bản")
        return 0

    manifest = load_manifest()
    payload = []
    for law_id, law_name, doc_type, author, article_count in rows:
        entry = manifest.get(law_id, {})
        payload.append(
            {
                "law_id": law_id,
                "law_name": entry.get("law_name") or law_name,
                "doc_type": entry.get("doc_type") or doc_type,
                "issuer": entry.get("author") or author,
                "category": entry.get("category") or infer_category(law_name),
                "effective_date": _effective_date(entry),
                "status": entry.get("status") or "active",
                "article_count": article_count,
            }
        )

    statement = insert(Law).values(payload)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[Law.law_id],
            set_={
                "law_name": statement.excluded.law_name,
                "doc_type": statement.excluded.doc_type,
                "issuer": statement.excluded.issuer,
                "category": statement.excluded.category,
                "effective_date": statement.excluded.effective_date,
                "status": statement.excluded.status,
                "article_count": statement.excluded.article_count,
                "updated_at": func.now(),
            },
        )
    )
    # Văn bản đã bị loại khỏi corpus thì không nên còn trong danh mục.
    await session.execute(
        delete(Law).where(Law.law_id.notin_([item["law_id"] for item in payload]))
    )
    await session.commit()
    logger.info("Đã đồng bộ danh mục: %s văn bản", len(payload))
    return len(payload)
