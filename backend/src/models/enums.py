"""Enum dùng chung cho ORM model và API schema.

Lưu vào PostgreSQL dưới dạng TEXT (không dùng native ENUM) để thêm giá trị mới
không cần migration ALTER TYPE.
"""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """Thay cho ``enum.StrEnum`` (chỉ có từ Python 3.11).

    Backend pin Python 3.10 vì ``underthesea``, nên tự định nghĩa lại để giá trị
    enum vẫn so sánh và serialize được như string.
    """

    def __str__(self) -> str:  # pragma: no cover - hành vi hiển thị
        return str(self.value)


class UserRole(StrEnum):
    """Vai trò quyết định quyền truy cập trong doanh nghiệp."""

    OWNER = "owner"  # Chủ doanh nghiệp
    ACCOUNTANT = "accountant"  # Kế toán
    HR = "hr"  # Nhân sự
    ADMIN = "admin"  # Quản trị hệ thống

    @property
    def is_admin(self) -> bool:
        return self is UserRole.ADMIN


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class DocumentStatus(StrEnum):
    """Trạng thái của file tải lên.

    Trích text xong là ``READY``: file đọc được và đang chờ soát xét. ``DONE``
    chỉ đạt được sau khi có ít nhất một lần soát xét thành công.
    """

    PENDING = "pending"
    READY = "ready"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class RiskLevel(StrEnum):
    """Mức rủi ro của một điều khoản hợp đồng."""

    HIGH = "cao"
    MEDIUM = "trung bình"
    LOW = "thấp"
    INFO = "thông tin"

    @property
    def weight(self) -> int:
        return {"cao": 3, "trung bình": 2, "thấp": 1, "thông tin": 0}[self.value]


class ComplianceFrequency(StrEnum):
    """Chu kỳ lặp của một nghĩa vụ tuân thủ."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    ONE_TIME = "one_time"


class ComplianceStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
