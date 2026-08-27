"""Tra cứu văn bản pháp luật: danh mục, cây Chương-Điều, chi tiết, tìm kiếm."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from src.core.deps import CurrentUser, SessionDep
from src.models import Law, LegalKnowledgeRecord
from src.schemas.api.law import (
    ArticleDetail,
    ArticleRef,
    ArticleSummary,
    ChapterNode,
    LawListResponse,
    LawOut,
    LawTreeResponse,
    SearchHit,
    SearchResponse,
)
from src.services.legal.search import (
    list_related_articles,
    matched_terms,
    search_articles,
)

router = APIRouter(prefix="/api/v1/laws", tags=["laws"])

# Số hiệu văn bản có dấu "/" (ví dụ 59/2020/QH14) nên law_id phải khai báo là
# ``:path``. Kéo theo hai ràng buộc: route tĩnh (/search) phải khai báo trước, và
# route con (/articles) phải khai báo trước route ``/{law_id:path}`` trần.
LAW_ID_PATH = "/{law_id:path}"


async def _get_law(session: SessionDep, law_id: str) -> Law:
    law = await session.get(Law, law_id)
    if law is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy văn bản {law_id}",
        )
    return law


@router.get("", response_model=LawListResponse)
async def list_laws(
    _user: CurrentUser,
    session: SessionDep,
    category: str | None = Query(default=None, description="Lọc theo lĩnh vực"),
    doc_type: str | None = Query(default=None, description="Luật, Nghị định, Thông tư..."),
    q: str | None = Query(default=None, description="Tìm theo tên hoặc số hiệu văn bản"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> LawListResponse:
    """Danh mục văn bản trong corpus, kèm bộ giá trị lọc sẵn có."""

    conditions = []
    if category:
        conditions.append(Law.category == category)
    if doc_type:
        conditions.append(Law.doc_type == doc_type)
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            func.immutable_unaccent(Law.law_name).ilike(func.immutable_unaccent(pattern))
            | Law.law_id.ilike(pattern)
        )

    total = await session.scalar(select(func.count()).select_from(Law).where(*conditions))
    rows = (
        await session.execute(
            select(Law)
            .where(*conditions)
            .order_by(Law.category, Law.doc_type, Law.law_name)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    # Giá trị lọc lấy trên toàn bảng, không theo điều kiện hiện tại, để người
    # dùng còn đổi được lựa chọn sau khi đã lọc.
    categories = (await session.execute(select(Law.category).distinct().order_by(Law.category))).scalars().all()
    doc_types = (await session.execute(select(Law.doc_type).distinct().order_by(Law.doc_type))).scalars().all()

    return LawListResponse(
        items=[LawOut.model_validate(row) for row in rows],
        total=total or 0,
        categories=list(categories),
        doc_types=list(doc_types),
    )


@router.get("/search", response_model=SearchResponse)
async def search_laws(
    _user: CurrentUser,
    session: SessionDep,
    q: str = Query(min_length=2, description="Từ khóa tra cứu"),
    law_id: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SearchResponse:
    """Full-text search trên corpus, khác với semantic search của chat."""

    hits, total, strategy = await search_articles(
        session, q, law_id=law_id, doc_type=doc_type, limit=limit, offset=offset
    )
    return SearchResponse(
        items=[SearchHit(**hit) for hit in hits],
        total=total,
        query=q,
        strategy=strategy,
        terms=matched_terms(q),
    )


@router.get(LAW_ID_PATH + "/articles/{article}", response_model=ArticleDetail)
async def get_article(
    law_id: str, article: str, _user: CurrentUser, session: SessionDep
) -> ArticleDetail:
    """Chi tiết một Điều, kèm viện dẫn chéo đã phân giải và Điều trước/sau."""

    record = (
        await session.execute(
            select(LegalKnowledgeRecord).where(
                LegalKnowledgeRecord.law_id == law_id,
                LegalKnowledgeRecord.article == article,
            )
        )
    ).scalars().first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy {article} trong văn bản {law_id}",
        )

    related = await list_related_articles(session, record.extra or [])
    previous_article = await session.scalar(
        select(LegalKnowledgeRecord.article)
        .where(
            LegalKnowledgeRecord.law_id == law_id,
            LegalKnowledgeRecord.article_number < record.article_number,
        )
        .order_by(LegalKnowledgeRecord.article_number.desc())
        .limit(1)
    )
    next_article = await session.scalar(
        select(LegalKnowledgeRecord.article)
        .where(
            LegalKnowledgeRecord.law_id == law_id,
            LegalKnowledgeRecord.article_number > record.article_number,
        )
        .order_by(LegalKnowledgeRecord.article_number)
        .limit(1)
    )

    return ArticleDetail(
        id=record.id,
        law_id=record.law_id,
        law_name=record.law_name,
        doc_type=record.doc_type,
        chapter=record.chapter,
        article=record.article,
        article_title=record.article_title,
        content=record.content,
        author=record.author,
        related=[ArticleRef(**item) for item in related],
        previous_article=previous_article,
        next_article=next_article,
    )


@router.get(LAW_ID_PATH + "/articles", response_model=LawTreeResponse)
async def get_law_tree(law_id: str, _user: CurrentUser, session: SessionDep) -> LawTreeResponse:
    """Cây Chương → Điều của văn bản, dùng cho sidebar tra cứu."""

    law = await _get_law(session, law_id)
    rows = (
        await session.execute(
            select(
                LegalKnowledgeRecord.id,
                LegalKnowledgeRecord.chapter,
                LegalKnowledgeRecord.article,
                LegalKnowledgeRecord.article_title,
            )
            .where(LegalKnowledgeRecord.law_id == law_id)
            .order_by(LegalKnowledgeRecord.article_number, LegalKnowledgeRecord.article)
        )
    ).all()

    # Giữ thứ tự Chương theo lần xuất hiện đầu tiên thay vì sort chuỗi, vì
    # "Chương X" phải nằm sau "Chương IX".
    chapters: dict[str | None, list[ArticleSummary]] = {}
    for record_id, chapter, article, article_title in rows:
        chapters.setdefault(chapter, []).append(
            ArticleSummary(id=record_id, article=article, article_title=article_title)
        )

    return LawTreeResponse(
        law=LawOut.model_validate(law),
        chapters=[
            ChapterNode(chapter=chapter, articles=articles)
            for chapter, articles in chapters.items()
        ],
    )


@router.get(LAW_ID_PATH, response_model=LawOut)
async def get_law(law_id: str, _user: CurrentUser, session: SessionDep) -> LawOut:
    """Metadata của một văn bản."""

    return LawOut.model_validate(await _get_law(session, law_id))
