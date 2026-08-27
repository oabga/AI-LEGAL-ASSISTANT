"""Full-text search trên corpus pháp luật bằng PostgreSQL.

Khác với semantic search của chat: ở đây người dùng đang *tra cứu*, họ muốn tìm
đúng từ khóa trong văn bản chứ không muốn model diễn giải lại. Vì PostgreSQL
không có dictionary tiếng Việt, cột ``search_vector`` dùng ``to_tsvector('simple',
immutable_unaccent(...))`` nên truy vấn cũng phải bỏ dấu tương ứng.
"""
from __future__ import annotations

import re

from sqlalchemy import Float, and_, cast, desc, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from src.models import LegalKnowledgeRecord

# Ngưỡng similarity của pg_trgm khi full-text không khớp token nào.
TRIGRAM_THRESHOLD = 0.3

# Tách token: giữ chữ (kể cả có dấu) và số, bỏ dấu câu.
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# "Điều 5 Luật Doanh nghiệp" -> tra thẳng theo số điều thay vì full-text.
ARTICLE_QUERY_RE = re.compile(r"\bđiều\s+(\d+[a-zA-Z]?)\b", re.IGNORECASE)


def _unaccent(column):
    """Bỏ dấu bằng đúng hàm immutable dùng cho index, để index được sử dụng."""

    return func.immutable_unaccent(column)


def build_tsquery(query: str):
    """Dựng ``tsquery`` prefix-match từ câu truy vấn của người dùng.

    Dùng prefix (``:*``) để "doanh ngh" vẫn khớp "doanh nghiệp" khi gõ dở, và
    nối bằng AND để càng nhiều từ khớp thì kết quả càng đúng.
    """

    tokens = TOKEN_RE.findall(query)
    if not tokens:
        return None
    pattern = " & ".join(f"{token}:*" for token in tokens)
    return func.to_tsquery("simple", func.immutable_unaccent(literal(pattern)))


def _rank(tsquery):
    return func.ts_rank_cd(LegalKnowledgeRecord.search_vector, tsquery)


def _similarity(query: str):
    """Điểm giống nhau cao nhất giữa truy vấn và tiêu đề Điều / tên văn bản."""

    normalized = func.immutable_unaccent(literal(query))
    return func.greatest(
        func.similarity(_unaccent(LegalKnowledgeRecord.article_title), normalized),
        func.similarity(_unaccent(LegalKnowledgeRecord.law_name), normalized),
    )


def _apply_filters(
    statement: Select,
    *,
    law_id: str | None,
    doc_type: str | None,
) -> Select:
    if law_id:
        statement = statement.where(LegalKnowledgeRecord.law_id == law_id)
    if doc_type:
        statement = statement.where(LegalKnowledgeRecord.doc_type == doc_type)
    return statement


async def search_articles(
    session: AsyncSession,
    query: str,
    *,
    law_id: str | None = None,
    doc_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int, str]:
    """Tìm Điều luật theo từ khóa.

    Trả về ``(kết quả, tổng số, chiến lược đã dùng)``. Chiến lược đi từ chính
    xác nhất tới rộng nhất: số Điều -> full-text -> trigram.
    """

    query = query.strip()
    if not query:
        return [], 0, "empty"

    article_match = ARTICLE_QUERY_RE.search(query)
    if article_match:
        results, total = await _search_by_article_number(
            session,
            article_match.group(1),
            residual=ARTICLE_QUERY_RE.sub(" ", query).strip(),
            law_id=law_id,
            doc_type=doc_type,
            limit=limit,
            offset=offset,
        )
        if results:
            return results, total, "article_number"

    tsquery = build_tsquery(query)
    if tsquery is not None:
        results, total = await _search_full_text(
            session, tsquery, law_id=law_id, doc_type=doc_type, limit=limit, offset=offset
        )
        if results:
            return results, total, "full_text"

    results, total = await _search_trigram(
        session, query, law_id=law_id, doc_type=doc_type, limit=limit, offset=offset
    )
    return results, total, "trigram"


async def _search_by_article_number(
    session: AsyncSession,
    article_number: str,
    *,
    residual: str,
    law_id: str | None,
    doc_type: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """Tra theo "Điều N", ưu tiên văn bản khớp phần chữ còn lại của truy vấn."""

    condition = LegalKnowledgeRecord.article.op("~*")(rf"^Điều\s+{article_number}$")
    statement = _apply_filters(
        select(LegalKnowledgeRecord).where(condition), law_id=law_id, doc_type=doc_type
    )

    if residual:
        # "Điều 5 Luật Doanh nghiệp": phần "Luật Doanh nghiệp" thu hẹp văn bản.
        normalized = func.immutable_unaccent(literal(residual))
        statement = statement.where(
            _unaccent(LegalKnowledgeRecord.law_name).op("%")(normalized)
        ).order_by(desc(func.similarity(_unaccent(LegalKnowledgeRecord.law_name), normalized)))
    else:
        statement = statement.order_by(LegalKnowledgeRecord.law_id)

    total = await session.scalar(
        _apply_filters(
            select(func.count()).select_from(LegalKnowledgeRecord).where(condition),
            law_id=law_id,
            doc_type=doc_type,
        )
    )
    rows = (await session.execute(statement.limit(limit).offset(offset))).scalars().all()
    return [_to_hit(row, score=1.0) for row in rows], total or 0


async def _search_full_text(
    session: AsyncSession,
    tsquery,
    *,
    law_id: str | None,
    doc_type: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    condition = LegalKnowledgeRecord.search_vector.op("@@")(tsquery)
    rank = _rank(tsquery)
    statement = _apply_filters(
        select(LegalKnowledgeRecord, rank.label("score")).where(condition),
        law_id=law_id,
        doc_type=doc_type,
    ).order_by(desc("score"), LegalKnowledgeRecord.law_id, LegalKnowledgeRecord.article_number)

    total = await session.scalar(
        _apply_filters(
            select(func.count()).select_from(LegalKnowledgeRecord).where(condition),
            law_id=law_id,
            doc_type=doc_type,
        )
    )
    rows = (await session.execute(statement.limit(limit).offset(offset))).all()
    return [_to_hit(row[0], score=float(row[1] or 0.0)) for row in rows], total or 0


async def _search_trigram(
    session: AsyncSession,
    query: str,
    *,
    law_id: str | None,
    doc_type: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """Cứu truy vấn gõ sai chính tả hoặc thiếu dấu mà full-text bỏ qua."""

    score = _similarity(query)
    condition = cast(score, Float) >= TRIGRAM_THRESHOLD
    statement = _apply_filters(
        select(LegalKnowledgeRecord, score.label("score")).where(condition),
        law_id=law_id,
        doc_type=doc_type,
    ).order_by(desc("score"), LegalKnowledgeRecord.law_id, LegalKnowledgeRecord.article_number)

    total = await session.scalar(
        _apply_filters(
            select(func.count()).select_from(LegalKnowledgeRecord).where(condition),
            law_id=law_id,
            doc_type=doc_type,
        )
    )
    rows = (await session.execute(statement.limit(limit).offset(offset))).all()
    return [_to_hit(row[0], score=float(row[1] or 0.0)) for row in rows], total or 0


def _to_hit(record: LegalKnowledgeRecord, *, score: float) -> dict:
    return {
        "id": record.id,
        "law_id": record.law_id,
        "law_name": record.law_name,
        "doc_type": record.doc_type,
        "chapter": record.chapter,
        "article": record.article,
        "article_title": record.article_title,
        "content": record.content,
        "score": round(score, 6),
    }


def matched_terms(query: str) -> list[str]:
    """Các từ khóa để client tự bôi đậm trên nội dung gốc.

    Không dùng ``ts_headline`` của PostgreSQL: nó chỉ chạy được trên cột đã bỏ
    dấu (vì ``search_vector`` được build từ ``immutable_unaccent``), nên đoạn
    trích trả về sẽ mất hết dấu tiếng Việt. Client bôi đậm theo kiểu bỏ qua dấu
    trên nội dung gốc thì vừa đúng chính tả vừa vẫn khớp truy vấn không dấu.
    """

    return [token for token in TOKEN_RE.findall(query) if len(token) > 1]


ARTICLE_PREFIX_RE = re.compile(r"^Điều\s+\d", re.IGNORECASE)


def parse_reference(reference: str) -> tuple[list[str], str] | None:
    """Tách một chuỗi viện dẫn thành (các ứng viên law_id, số Điều).

    Trong hệ thống có hai định dạng viện dẫn cùng tồn tại:

    - ``extra`` của corpus: ``doc_type|law_id|Điều X`` (ví dụ
      ``Luật|43/2013/QH13|Điều 14``)
    - citation do agent và ``compliance_rules`` sinh ra:
      ``law_id|law_name|Điều X``

    Thay vì đoán xem law_id nằm ở vị trí nào, trả về tất cả segment không phải
    số Điều làm ứng viên rồi để truy vấn tự chọn: một chuỗi chỉ khớp khi vừa
    trùng law_id vừa trùng số Điều, nên nhận sai gần như không thể xảy ra.
    """

    parts = [part.strip() for part in reference.split("|") if part.strip()]
    if len(parts) < 2:
        return None
    article = parts[-1]
    # Viện dẫn chỉ tới cả văn bản ("Luật|43/2013/QH13") thì không có Điều để mở.
    if not ARTICLE_PREFIX_RE.match(article):
        return None
    candidates = parts[:-1]
    return (candidates, article) if candidates else None


async def list_related_articles(
    session: AsyncSession, references: list[str]
) -> list[dict]:
    """Phân giải danh sách viện dẫn chéo thành các Điều thật trong corpus.

    Viện dẫn không tìm được sẽ bị bỏ để UI không render link chết.
    """

    parsed = [item for item in map(parse_reference, references) if item is not None]
    if not parsed:
        return []

    conditions = [
        and_(
            LegalKnowledgeRecord.law_id.in_(candidates),
            LegalKnowledgeRecord.article == article,
        )
        for candidates, article in parsed
    ]
    rows = (
        await session.execute(
            select(LegalKnowledgeRecord)
            .where(or_(*conditions))
            .order_by(LegalKnowledgeRecord.law_id, LegalKnowledgeRecord.article_number)
        )
    ).scalars().all()
    return [
        {
            "law_id": row.law_id,
            "law_name": row.law_name,
            "article": row.article,
            "article_title": row.article_title,
        }
        for row in rows
    ]
