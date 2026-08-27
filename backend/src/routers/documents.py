"""Upload hợp đồng và chạy soát xét rủi ro."""
from __future__ import annotations

import logging
import uuid
from collections import Counter

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import selectinload

from src.config import get_settings
from src.core.database import get_session_factory
from src.core.deps import CurrentUser, SessionDep, get_current_organization_id
from src.core.rate_limit import upload_rate_limit
from src.dependencies import get_llm_client
from src.models import (
    AuditLog,
    ContractFinding,
    ContractReview,
    Document,
    DocumentStatus,
    ReviewStatus,
)
from src.schemas.api.document import (
    DocumentListResponse,
    DocumentOut,
    FindingOut,
    ReviewDetail,
    ReviewOut,
)
from src.services.contracts.extract import (
    ExtractionError,
    detect_mime,
    extract_text,
    split_clauses,
)
from src.services.contracts.reviewer import compute_risk_score, review_clauses, summarize
from src.services.vector_store import vector_store_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["contracts"])

OrganizationId = Depends(get_current_organization_id)


def _to_document_out(document: Document) -> DocumentOut:
    # Tài liệu vừa được tạo chưa load relationship; chạm vào sẽ kích hoạt lazy
    # load đồng bộ và nổ MissingGreenlet trên engine async.
    loaded = "reviews" not in inspect(document).unloaded
    reviews = document.reviews if loaded else []
    return DocumentOut(
        id=document.id,
        filename=document.filename,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        status=document.status,
        error_message=document.error_message,
        created_at=document.created_at,
        text_length=len(document.extracted_text or ""),
        latest_review_id=reviews[-1].id if reviews else None,
    )


@router.post(
    "/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
@upload_rate_limit
async def upload_document(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(..., description="Hợp đồng PDF, DOCX hoặc TXT"),
    organization_id: uuid.UUID = OrganizationId,
) -> DocumentOut:
    """Tải hợp đồng lên, trích text ngay để lỗi định dạng lộ ra lập tức."""

    settings = get_settings()
    payload = await file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng"
        )
    if len(payload) > settings.uploads.max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File vượt giới hạn {settings.uploads.max_size_mb} MB "
                f"(file này {len(payload) / 1024 / 1024:.1f} MB)"
            ),
        )

    filename = (file.filename or "hop-dong").strip()
    try:
        mime_type = detect_mime(filename, file.content_type)
        text = extract_text(payload, mime_type)
    except ExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Tên file trên đĩa dùng UUID để tránh path traversal và trùng tên.
    document_id = uuid.uuid4()
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    storage_path = settings.uploads.directory / f"{document_id}{suffix}"
    settings.uploads.directory.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(payload)

    document = Document(
        id=document_id,
        organization_id=organization_id,
        uploaded_by=user.id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(payload),
        storage_path=str(storage_path),
        status=DocumentStatus.READY,
        extracted_text=text,
    )
    session.add(document)
    session.add(
        AuditLog(
            user_id=user.id,
            actor_email=user.email,
            action="upload_document",
            resource="document",
            resource_id=str(document_id),
            detail={"filename": filename, "size_bytes": len(payload)},
        )
    )
    await session.flush()
    return _to_document_out(document)


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    _user: CurrentUser,
    session: SessionDep,
    organization_id: uuid.UUID = OrganizationId,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    """Hợp đồng đã tải lên của doanh nghiệp, mới nhất trước."""

    condition = Document.organization_id == organization_id
    total = await session.scalar(select(func.count()).select_from(Document).where(condition))
    documents = (
        await session.execute(
            select(Document)
            .options(selectinload(Document.reviews))
            .where(condition)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return DocumentListResponse(
        items=[_to_document_out(document) for document in documents],
        total=total or 0,
    )


async def _get_document(session: SessionDep, document_id: uuid.UUID, organization_id) -> Document:
    document = (
        await session.execute(
            select(Document)
            .options(selectinload(Document.reviews))
            .where(Document.id == document_id, Document.organization_id == organization_id)
        )
    ).scalars().first()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài liệu"
        )
    return document


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    _user: CurrentUser,
    session: SessionDep,
    organization_id: uuid.UUID = OrganizationId,
) -> DocumentOut:
    """Metadata của một hợp đồng đã tải lên."""

    return _to_document_out(await _get_document(session, document_id, organization_id))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    _user: CurrentUser,
    session: SessionDep,
    organization_id: uuid.UUID = OrganizationId,
) -> Response:
    """Xóa hợp đồng khỏi cả database và volume lưu file."""

    from pathlib import Path

    document = await _get_document(session, document_id, organization_id)
    path = Path(document.storage_path)
    await session.delete(document)
    # Xóa file sau khi DB đã đồng ý, và bỏ qua lỗi để bản ghi không bị treo lại.
    path.unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/documents/{document_id}/review",
    response_model=ReviewOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_review(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    session: SessionDep,
    organization_id: uuid.UUID = OrganizationId,
) -> ReviewOut:
    """Xếp hàng chạy soát xét; trả về ngay để client poll trạng thái."""

    settings = get_settings().legal_assistant.contract_review
    if not settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chức năng soát xét hợp đồng đang tắt",
        )

    document = await _get_document(session, document_id, organization_id)
    if not (document.extracted_text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tài liệu chưa có nội dung để soát xét",
        )
    # Chặn chạy trùng: một tài liệu chỉ có một review đang xử lý.
    running = next(
        (
            review
            for review in document.reviews
            if review.status in {ReviewStatus.PENDING, ReviewStatus.PROCESSING}
        ),
        None,
    )
    if running is not None:
        return ReviewOut.model_validate(running)

    review = ContractReview(document_id=document.id, status=ReviewStatus.PENDING)
    session.add(review)
    session.add(
        AuditLog(
            user_id=user.id,
            actor_email=user.email,
            action="start_contract_review",
            resource="contract_review",
            resource_id=str(review.id),
        )
    )
    await session.flush()
    # Commit trước khi giao background task, nếu không task sẽ không thấy review.
    await session.commit()

    background_tasks.add_task(run_review, review.id)
    return ReviewOut.model_validate(review)


async def run_review(review_id: uuid.UUID) -> None:
    """Chạy soát xét ở background với session riêng của chính nó."""

    factory = get_session_factory()
    async with factory() as session:
        review = await session.get(ContractReview, review_id)
        if review is None:  # pragma: no cover - review vừa bị xóa
            return
        document = await session.get(Document, review.document_id)
        review.status = ReviewStatus.PROCESSING
        await session.commit()

        try:
            settings = get_settings().legal_assistant.contract_review
            clauses = split_clauses(
                document.extracted_text or "", max_clauses=settings.max_clauses
            )
            if not clauses:
                raise ExtractionError("Không tách được điều khoản nào từ tài liệu")

            findings = await review_clauses(
                clauses, registry=vector_store_registry, llm=get_llm_client()
            )
            summary = await summarize(findings, len(clauses), llm=get_llm_client())

            for finding in findings:
                session.add(ContractFinding(review_id=review.id, **finding))
            review.clause_count = len(clauses)
            review.risk_score = compute_risk_score(findings)
            review.summary = summary
            review.status = ReviewStatus.DONE
            review.error_message = None
            document.status = DocumentStatus.DONE
        except Exception as exc:
            logger.exception("Soát xét hợp đồng %s thất bại", review_id)
            await session.rollback()
            # Nạp lại sau rollback rồi mới ghi trạng thái lỗi.
            review = await session.get(ContractReview, review_id)
            if review is not None:
                review.status = ReviewStatus.FAILED
                review.error_message = str(exc)[:2000]
        await session.commit()


@router.get("/reviews/{review_id}", response_model=ReviewDetail)
async def get_review(
    review_id: uuid.UUID,
    _user: CurrentUser,
    session: SessionDep,
    organization_id: uuid.UUID = OrganizationId,
) -> ReviewDetail:
    """Kết quả soát xét kèm danh sách findings có trích dẫn Điều luật."""

    review = (
        await session.execute(
            select(ContractReview)
            .join(ContractReview.document)
            .options(
                selectinload(ContractReview.findings),
                selectinload(ContractReview.document),
            )
            .where(
                ContractReview.id == review_id,
                Document.organization_id == organization_id,
            )
        )
    ).scalars().first()
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiên soát xét"
        )

    counts = Counter(str(finding.risk_level) for finding in review.findings)
    return ReviewDetail(
        **ReviewOut.model_validate(review).model_dump(),
        filename=review.document.filename if review.document else None,
        findings=[FindingOut.model_validate(finding) for finding in review.findings],
        risk_counts=dict(counts),
    )
