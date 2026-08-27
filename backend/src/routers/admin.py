"""Quản trị corpus và người dùng. Toàn bộ router yêu cầu role admin."""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.config import get_settings
from src.core.deps import AdminUser, SessionDep, require_role
from src.models import AuditLog, Law, LegalKnowledgeRecord, User, UserRole
from src.schemas.api.admin import (
    AdminUserListResponse,
    AdminUserOut,
    CorpusStats,
    ImportResponse,
    LawStat,
    ReindexResponse,
    UpdateUserRequest,
)
from src.services.legal.catalog import sync_law_catalog
from src.services.legal.importer import (
    CorpusValidationError,
    import_records,
    validate_records,
)
from src.services.vector_store import vector_store_registry
from src.services.vector_store.index_builder import initialize_legal_index

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


def _to_admin_user(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        organization_id=user.organization_id,
        organization_name=user.organization.name if user.organization else None,
        created_at=user.created_at,
    )


def _index_state() -> tuple[bool, int]:
    """Đếm vector đang có trong Chroma để biết index đã sẵn sàng chưa."""

    settings = get_settings().legal_assistant.vector_store
    try:
        import chromadb

        from src.services.vector_store.chroma import safe_collection_name

        client = chromadb.PersistentClient(path=str(settings.persist_directory))
        prefix = safe_collection_name(settings.default_collection)
        total = 0
        for collection in client.list_collections():
            name = collection if isinstance(collection, str) else collection.name
            if name == prefix or name.startswith(f"{prefix}_"):
                total += client.get_collection(name).count()
        return total > 0, total
    except Exception:
        return False, 0


@router.get("/corpus/stats", response_model=CorpusStats)
async def corpus_stats(_admin: AdminUser, session: SessionDep) -> CorpusStats:
    """Thống kê corpus và trạng thái vector index."""

    total_articles = await session.scalar(
        select(func.count()).select_from(LegalKnowledgeRecord)
    )
    total_laws = await session.scalar(select(func.count()).select_from(Law))

    by_doc_type = {
        row[0]: row[1]
        for row in (
            await session.execute(
                select(Law.doc_type, func.sum(Law.article_count))
                .group_by(Law.doc_type)
                .order_by(func.sum(Law.article_count).desc())
            )
        ).all()
    }
    by_category = {
        row[0]: row[1]
        for row in (
            await session.execute(
                select(Law.category, func.sum(Law.article_count))
                .group_by(Law.category)
                .order_by(func.sum(Law.article_count).desc())
            )
        ).all()
    }
    largest = (
        await session.execute(select(Law).order_by(Law.article_count.desc()).limit(10))
    ).scalars().all()

    index_ready, indexed_vectors = _index_state()
    return CorpusStats(
        total_articles=total_articles or 0,
        total_laws=total_laws or 0,
        by_doc_type=by_doc_type,
        by_category=by_category,
        largest_laws=[
            LawStat(
                law_id=law.law_id,
                law_name=law.law_name,
                doc_type=law.doc_type,
                category=law.category,
                article_count=law.article_count,
            )
            for law in largest
        ],
        index_ready=index_ready,
        indexed_vectors=indexed_vectors,
        embedding_model=get_settings().embeddings.model,
    )


@router.post("/corpus/import", response_model=ImportResponse)
async def import_corpus(
    admin: AdminUser,
    session: SessionDep,
    file: UploadFile = File(..., description="File JSON corpus"),
    truncate: bool = Query(default=False, description="Xóa corpus cũ trước khi nạp"),
) -> ImportResponse:
    """Nạp corpus từ file JSON, dùng đúng logic của ``load_postgres.py``."""

    payload = await file.read()
    try:
        records = validate_records(json.loads(payload.decode("utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File không phải JSON hợp lệ: {exc}",
        ) from exc
    except CorpusValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    settings = get_settings().legal_assistant.postgres
    try:
        result = await import_records(
            records,
            database_url=settings.database_url,
            batch_size=settings.batch_size,
            truncate=truncate,
        )
    except CorpusValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    await sync_law_catalog(session)
    session.add(
        AuditLog(
            user_id=admin.id,
            actor_email=admin.email,
            action="import_corpus",
            resource="corpus",
            detail={
                "filename": file.filename,
                "imported": result.imported,
                "truncate": truncate,
            },
        )
    )
    return ImportResponse(
        imported=result.imported,
        total_articles=result.total_in_table,
        total_laws=result.laws,
        reindex_required=True,
        message=(
            f"Đã nạp {result.imported} record. Corpus hiện có {result.total_in_table} "
            f"record thuộc {result.laws} văn bản. Chạy reindex để retrieval dùng "
            "dữ liệu mới."
        ),
    )


@router.post("/corpus/reindex", response_model=ReindexResponse)
async def reindex_corpus(
    request: Request, admin: AdminUser, session: SessionDep
) -> ReindexResponse:
    """Dựng lại vector index mà không cần restart backend.

    Chạy đồng bộ (không dùng BackgroundTasks) để admin thấy được lỗi rate limit
    hoặc thiếu API key ngay trong response.
    """

    try:
        await initialize_legal_index(get_settings(), registry=vector_store_registry)
    except Exception as exc:
        logger.exception("Reindex thất bại")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Reindex thất bại: {exc}",
        ) from exc

    # Mở lại các endpoint hỏi đáp: startup có thể đã tắt chúng vì index lỗi.
    request.app.state.index_ready = True
    _, indexed = _index_state()
    session.add(
        AuditLog(
            user_id=admin.id,
            actor_email=admin.email,
            action="reindex_corpus",
            resource="corpus",
            detail={"indexed_vectors": indexed},
        )
    )
    return ReindexResponse(
        status="done",
        message=f"Đã dựng lại index với {indexed} vector.",
        indexed_vectors=indexed,
    )


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    _admin: AdminUser,
    session: SessionDep,
    q: str | None = Query(default=None, description="Tìm theo email hoặc tên"),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdminUserListResponse:
    """Danh sách người dùng của hệ thống."""

    conditions = []
    if q:
        pattern = f"%{q.strip().lower()}%"
        conditions.append(
            User.email.ilike(pattern) | func.lower(User.full_name).like(pattern)
        )
    if role:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))

    total = await session.scalar(select(func.count()).select_from(User).where(*conditions))
    users = (
        await session.execute(
            select(User)
            .options(selectinload(User.organization))
            .where(*conditions)
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return AdminUserListResponse(
        items=[_to_admin_user(user) for user in users], total=total or 0
    )


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    admin: AdminUser,
    session: SessionDep,
) -> AdminUserOut:
    """Đổi vai trò hoặc kích hoạt/vô hiệu hóa một tài khoản."""

    user = (
        await session.execute(
            select(User).options(selectinload(User.organization)).where(User.id == user_id)
        )
    ).scalars().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng"
        )
    if user.id == admin.id:
        # Tránh admin tự khóa mình hoặc tự hạ quyền rồi mất đường vào trang admin.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể tự đổi vai trò hoặc tự vô hiệu hóa tài khoản của mình",
        )

    changes: dict[str, str | bool] = {}
    if payload.role is not None and payload.role != user.role:
        changes["role"] = payload.role.value
        user.role = payload.role
    if payload.is_active is not None and payload.is_active != user.is_active:
        changes["is_active"] = payload.is_active
        user.is_active = payload.is_active

    if changes:
        session.add(
            AuditLog(
                user_id=admin.id,
                actor_email=admin.email,
                action="update_user",
                resource="user",
                resource_id=str(user.id),
                detail=changes,
            )
        )
    await session.flush()
    return _to_admin_user(user)
