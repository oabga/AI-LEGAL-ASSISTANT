"""Lịch tuân thủ: nghĩa vụ định kỳ theo hồ sơ doanh nghiệp."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.core.deps import CurrentUser, SessionDep, get_current_organization_id
from src.models import (
    ComplianceRule,
    ComplianceStatus,
    ComplianceTask,
    Organization,
)
from src.schemas.api.compliance import (
    ComplianceRuleOut,
    ComplianceSummary,
    ComplianceTaskListResponse,
    ComplianceTaskOut,
    RuleDetail,
    UpdateTaskRequest,
)
from src.schemas.api.law import ArticleRef
from src.services.compliance.generator import generate_tasks_for_organization
from src.services.legal.search import list_related_articles

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])

OrganizationId = Depends(get_current_organization_id)

# Ngưỡng "sắp đến hạn" dùng chung cho dashboard và bộ lọc.
DUE_SOON_DAYS = 30


def _to_task_out(task: ComplianceTask, today: date) -> ComplianceTaskOut:
    days_remaining = (task.due_date - today).days
    return ComplianceTaskOut(
        id=task.id,
        period_label=task.period_label,
        due_date=task.due_date,
        status=task.status,
        completed_at=task.completed_at,
        notes=task.notes,
        rule=ComplianceRuleOut.model_validate(task.rule),
        days_remaining=days_remaining,
        # Chỉ tính quá hạn khi còn dở; task đã hoàn thành thì không nhắc nữa.
        overdue=days_remaining < 0 and task.status == ComplianceStatus.PENDING,
    )


@router.get("/tasks", response_model=ComplianceTaskListResponse)
async def list_tasks(
    _user: CurrentUser,
    session: SessionDep,
    organization_id: uuid.UUID = OrganizationId,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    task_status: ComplianceStatus | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ComplianceTaskListResponse:
    """Danh sách nghĩa vụ theo khoảng thời gian, phục vụ cả list và calendar."""

    conditions = [ComplianceTask.organization_id == organization_id]
    if date_from:
        conditions.append(ComplianceTask.due_date >= date_from)
    if date_to:
        conditions.append(ComplianceTask.due_date <= date_to)
    if task_status:
        conditions.append(ComplianceTask.status == task_status)

    statement = (
        select(ComplianceTask)
        .join(ComplianceTask.rule)
        .options(selectinload(ComplianceTask.rule))
        .where(*conditions)
    )
    count_statement = (
        select(func.count()).select_from(ComplianceTask).join(ComplianceTask.rule).where(*conditions)
    )
    if category:
        statement = statement.where(ComplianceRule.category == category)
        count_statement = count_statement.where(ComplianceRule.category == category)

    total = await session.scalar(count_statement)
    tasks = (
        await session.execute(
            statement.order_by(ComplianceTask.due_date, ComplianceRule.title)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    today = date.today()
    return ComplianceTaskListResponse(
        items=[_to_task_out(task, today) for task in tasks],
        total=total or 0,
    )


@router.get("/summary", response_model=ComplianceSummary)
async def get_summary(
    _user: CurrentUser,
    session: SessionDep,
    organization_id: uuid.UUID = OrganizationId,
) -> ComplianceSummary:
    """Số liệu tổng hợp cho dashboard."""

    today = date.today()
    rows = (
        await session.execute(
            select(ComplianceTask.status, func.count())
            .where(ComplianceTask.organization_id == organization_id)
            .group_by(ComplianceTask.status)
        )
    ).all()
    counts = {str(row[0]): row[1] for row in rows}

    pending_condition = [
        ComplianceTask.organization_id == organization_id,
        ComplianceTask.status == ComplianceStatus.PENDING,
    ]
    overdue = await session.scalar(
        select(func.count())
        .select_from(ComplianceTask)
        .where(*pending_condition, ComplianceTask.due_date < today)
    )
    due_soon = await session.scalar(
        select(func.count())
        .select_from(ComplianceTask)
        .where(
            *pending_condition,
            ComplianceTask.due_date >= today,
            ComplianceTask.due_date <= today + timedelta(days=DUE_SOON_DAYS),
        )
    )
    next_task = (
        await session.execute(
            select(ComplianceTask)
            .options(selectinload(ComplianceTask.rule))
            .where(*pending_condition, ComplianceTask.due_date >= today)
            .order_by(ComplianceTask.due_date)
            .limit(1)
        )
    ).scalars().first()

    return ComplianceSummary(
        total=sum(counts.values()),
        pending=counts.get(ComplianceStatus.PENDING, 0),
        done=counts.get(ComplianceStatus.DONE, 0),
        skipped=counts.get(ComplianceStatus.SKIPPED, 0),
        overdue=overdue or 0,
        due_soon=due_soon or 0,
        next_due=_to_task_out(next_task, today) if next_task else None,
    )


@router.get("/rules", response_model=list[RuleDetail])
async def list_rules(_user: CurrentUser, session: SessionDep) -> list[RuleDetail]:
    """Danh mục nghĩa vụ kèm căn cứ pháp lý đã phân giải thành Điều luật."""

    rules = (
        await session.execute(
            select(ComplianceRule)
            .where(ComplianceRule.is_active.is_(True))
            .order_by(ComplianceRule.category, ComplianceRule.title)
        )
    ).scalars().all()

    results: list[RuleDetail] = []
    for rule in rules:
        references = await list_related_articles(session, rule.legal_refs or [])
        results.append(
            RuleDetail(
                **ComplianceRuleOut.model_validate(rule).model_dump(),
                references=[ArticleRef(**item) for item in references],
            )
        )
    return results


@router.post("/tasks/generate", response_model=ComplianceSummary)
async def regenerate_tasks(
    user: CurrentUser,
    session: SessionDep,
    organization_id: uuid.UUID = OrganizationId,
) -> ComplianceSummary:
    """Sinh lại lịch cho cửa sổ thời gian hiện tại.

    Idempotent: task đã tồn tại được giữ nguyên trạng thái, chỉ thêm kỳ mới.
    """

    organization = await session.get(Organization, organization_id)
    await generate_tasks_for_organization(session, organization)
    await session.commit()
    return await get_summary(user, session, organization_id)


@router.patch("/tasks/{task_id}", response_model=ComplianceTaskOut)
async def update_task(
    task_id: uuid.UUID,
    payload: UpdateTaskRequest,
    _user: CurrentUser,
    session: SessionDep,
    organization_id: uuid.UUID = OrganizationId,
) -> ComplianceTaskOut:
    """Đánh dấu hoàn thành / bỏ qua, hoặc ghi chú cho một nghĩa vụ."""

    task = (
        await session.execute(
            select(ComplianceTask)
            .options(selectinload(ComplianceTask.rule))
            .where(
                ComplianceTask.id == task_id,
                ComplianceTask.organization_id == organization_id,
            )
        )
    ).scalars().first()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy nghĩa vụ này",
        )

    if payload.status is not None:
        task.status = payload.status
        # completed_at phải khớp trạng thái, kể cả khi người dùng bỏ đánh dấu.
        task.completed_at = date.today() if payload.status == ComplianceStatus.DONE else None
    if payload.notes is not None:
        task.notes = payload.notes.strip() or None

    await session.flush()
    await session.refresh(task)
    return _to_task_out(task, date.today())
