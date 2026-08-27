"""Sinh lịch tuân thủ cho từng doanh nghiệp từ danh mục ``compliance_rules``.

Thao tác sinh lịch là idempotent: ``uq_compliance_task_period`` đảm bảo mỗi
(doanh nghiệp, nghĩa vụ, kỳ) chỉ có một task, nên gọi lại nhiều lần không tạo
bản ghi trùng và không mất trạng thái đã hoàn thành.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ComplianceFrequency, ComplianceRule, ComplianceTask, Organization
from src.services.compliance.seed import COMPLIANCE_RULES

logger = logging.getLogger(__name__)

# Sinh lịch cho khoảng thời gian này quanh hiện tại.
MONTHS_BACK = 3
MONTHS_AHEAD = 12


async def ensure_rules_seeded(session: AsyncSession) -> int:
    """Nạp danh mục nghĩa vụ nếu chưa có. Trả về số rule được thêm mới."""

    existing = set(
        (await session.execute(select(ComplianceRule.code))).scalars().all()
    )
    added = 0
    for spec in COMPLIANCE_RULES:
        if spec["code"] in existing:
            continue
        session.add(ComplianceRule(**spec))
        added += 1
    if added:
        await session.flush()
        logger.info("Đã seed %d nghĩa vụ tuân thủ", added)
    return added


def _applies(rule: ComplianceRule, organization: Organization) -> bool:
    """Kiểm tra nghĩa vụ có áp dụng cho hồ sơ doanh nghiệp này không."""

    conditions = rule.applies_to or {}
    vat_period = conditions.get("vat_period")
    if vat_period and organization.vat_period != vat_period:
        return False
    min_employees = conditions.get("min_employees")
    if min_employees is not None and (organization.employee_count or 0) < min_employees:
        return False
    max_employees = conditions.get("max_employees")
    if max_employees is not None and (organization.employee_count or 0) > max_employees:
        return False
    return True


def _clamp_day(year: int, month: int, day: int) -> date:
    """Ngày 31 trong tháng chỉ có 30 ngày phải lùi về ngày cuối tháng."""

    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    index = (year * 12 + (month - 1)) + offset
    return index // 12, index % 12 + 1


def _periods(rule: ComplianceRule, today: date) -> list[tuple[str, date]]:
    """Liệt kê (nhãn kỳ, ngày đến hạn) trong cửa sổ thời gian đang xét."""

    start_year, start_month = _shift_month(today.year, today.month, -MONTHS_BACK)
    end_year, end_month = _shift_month(today.year, today.month, MONTHS_AHEAD)
    window_start = date(start_year, start_month, 1)
    window_end = _clamp_day(end_year, end_month, 28)

    results: list[tuple[str, date]] = []

    if rule.frequency == ComplianceFrequency.MONTHLY:
        year, month = start_year, start_month
        while (year, month) <= (end_year, end_month):
            due_year, due_month = _shift_month(year, month, rule.due_month_offset)
            results.append((f"{year:04d}-{month:02d}", _clamp_day(due_year, due_month, rule.due_day)))
            year, month = _shift_month(year, month, 1)

    elif rule.frequency == ComplianceFrequency.QUARTERLY:
        for year in range(start_year, end_year + 1):
            for quarter in range(1, 5):
                # Kỳ tính thuế kết thúc ở tháng cuối quý.
                last_month = quarter * 3
                due_year, due_month = _shift_month(year, last_month, rule.due_month_offset)
                due = _clamp_day(due_year, due_month, rule.due_day)
                if window_start <= due <= window_end:
                    results.append((f"{year:04d}-Q{quarter}", due))

    elif rule.frequency == ComplianceFrequency.ANNUAL:
        for year in range(start_year - 1, end_year + 1):
            month = rule.due_fixed_month or 12
            due_year, due_month = _shift_month(year, month, rule.due_month_offset)
            due = _clamp_day(due_year, due_month, rule.due_day)
            if window_start <= due <= window_end:
                # Nghĩa vụ quyết toán thuộc về năm tài chính trước kỳ nộp.
                label = f"{year:04d}"
                results.append((label, due))

    else:  # ONE_TIME
        month = rule.due_fixed_month or today.month
        due = _clamp_day(today.year, month, rule.due_day)
        results.append((f"{today.year:04d}", due))

    return results


async def generate_tasks_for_organization(
    session: AsyncSession, organization: Organization, *, today: date | None = None
) -> int:
    """Sinh/đồng bộ lịch tuân thủ cho một doanh nghiệp. Trả về số task được thêm."""

    if organization is None:
        return 0

    today = today or date.today()
    await ensure_rules_seeded(session)

    rules = (
        (await session.execute(select(ComplianceRule).where(ComplianceRule.is_active.is_(True))))
        .scalars()
        .all()
    )

    rows = []
    for rule in rules:
        if not _applies(rule, organization):
            continue
        for label, due_date in _periods(rule, today):
            rows.append(
                {
                    "organization_id": organization.id,
                    "rule_id": rule.id,
                    "period_label": label,
                    "due_date": due_date,
                }
            )

    if not rows:
        return 0

    dialect = session.bind.dialect.name if session.bind else "postgresql"
    if dialect == "postgresql":
        # ON CONFLICT DO NOTHING giữ nguyên task người dùng đã đánh dấu hoàn thành.
        statement = pg_insert(ComplianceTask).values(rows).on_conflict_do_nothing(
            constraint="uq_compliance_task_period"
        )
        result = await session.execute(statement)
        await session.flush()
        return result.rowcount or 0

    # Đường dự phòng cho SQLite trong test: tự lọc trùng trước khi insert.
    existing = set(
        (
            await session.execute(
                select(ComplianceTask.rule_id, ComplianceTask.period_label).where(
                    ComplianceTask.organization_id == organization.id
                )
            )
        ).all()
    )
    added = 0
    for row in rows:
        if (row["rule_id"], row["period_label"]) in existing:
            continue
        session.add(ComplianceTask(**row))
        added += 1
    await session.flush()
    return added
