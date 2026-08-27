"""Schema request/response cho đăng ký, đăng nhập và hồ sơ người dùng."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.config import get_settings
from src.models.enums import UserRole


class OrganizationInput(BaseModel):
    """Hồ sơ doanh nghiệp khai lúc đăng ký (tùy chọn)."""

    name: str = Field(min_length=2, max_length=255)
    tax_code: str | None = Field(default=None, max_length=32)
    business_type: str | None = Field(default=None, max_length=64)
    employee_count: int = Field(default=0, ge=0, le=1_000_000)
    annual_revenue_bn: float | None = Field(default=None, ge=0)
    address: str | None = None
    vat_period: str = Field(default="quarterly", pattern="^(monthly|quarterly)$")


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    tax_code: str | None
    business_type: str | None
    employee_count: int
    annual_revenue_bn: float | None
    address: str | None
    vat_period: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(min_length=2, max_length=160)
    role: UserRole = UserRole.OWNER
    organization: OrganizationInput | None = None

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, value: str) -> str:
        minimum = get_settings().auth.min_password_length
        if len(value) < minimum:
            raise ValueError(f"Mật khẩu phải có ít nhất {minimum} ký tự")
        if value.isdigit() or value.isalpha():
            raise ValueError("Mật khẩu nên gồm cả chữ và số")
        return value

    @field_validator("role")
    @classmethod
    def block_self_admin(cls, value: UserRole) -> UserRole:
        # Không cho tự đăng ký làm admin; admin đầu tiên do cơ chế bootstrap tạo.
        if value == UserRole.ADMIN:
            raise ValueError("Không thể tự đăng ký vai trò admin")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    organization_id: uuid.UUID | None
    organization: OrganizationOut | None = None
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthResponse(BaseModel):
    """Trả về sau register/login: token kèm hồ sơ để UI khỏi gọi thêm /me."""

    user: UserOut
    tokens: TokenPair


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    organization: OrganizationInput | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password_strength(cls, value: str) -> str:
        minimum = get_settings().auth.min_password_length
        if len(value) < minimum:
            raise ValueError(f"Mật khẩu phải có ít nhất {minimum} ký tự")
        return value
