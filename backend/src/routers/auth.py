"""Router xác thực: đăng ký, đăng nhập, refresh, hồ sơ."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.config import get_settings
from src.core.deps import CurrentUser, SessionDep
from src.core.security import (
    TokenError,
    access_token_expires_in,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from src.models import AuditLog, Organization, User, UserRole
from src.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UpdateProfileRequest,
    UserOut,
)
from src.services.compliance.generator import generate_tasks_for_organization

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Email hoặc mật khẩu không đúng",
)


def _token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        expires_in=access_token_expires_in(),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep) -> AuthResponse:
    """Tạo tài khoản mới, kèm hồ sơ doanh nghiệp nếu có."""

    email = payload.email.lower().strip()
    existing = await session.scalar(select(User.id).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email này đã được đăng ký",
        )

    role = payload.role
    settings = get_settings()
    if settings.auth.bootstrap_first_admin:
        # Tài khoản đầu tiên của hệ thống thành admin để có người quản trị corpus.
        user_count = await session.scalar(select(func.count()).select_from(User))
        if not user_count:
            role = UserRole.ADMIN

    organization: Organization | None = None
    if payload.organization is not None:
        tax_code = payload.organization.tax_code
        if tax_code:
            # Kiểm tra trước để trả 409 kèm thông báo rõ ràng, thay vì để
            # UniqueViolation của organizations.tax_code nổ thành 500.
            taken = await session.scalar(
                select(Organization.id).where(Organization.tax_code == tax_code)
            )
            if taken is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Mã số thuế {tax_code} đã được một tài khoản khác đăng ký",
                )
        organization = Organization(**payload.organization.model_dump())
        session.add(organization)

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=role,
        # Gán qua relationship để SQLAlchemy tự sắp thứ tự INSERT và điền FK,
        # không cần flush organization riêng để lấy id.
        organization=organization,
    )
    session.add(user)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email hoặc mã số thuế đã tồn tại",
        ) from exc

    # Ghi audit sau flush để user.id đã có giá trị thật.
    session.add(
        AuditLog(
            user_id=user.id,
            actor_email=email,
            action="register",
            resource="user",
            resource_id=str(user.id),
            detail={"role": role.value},
        )
    )

    # Doanh nghiệp mới có ngay lịch tuân thủ để dashboard không rỗng.
    if organization is not None:
        await generate_tasks_for_organization(session, organization)

    await session.commit()
    await session.refresh(user, attribute_names=["organization"])
    return AuthResponse(user=UserOut.model_validate(user), tokens=_token_pair(user))


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, session: SessionDep) -> AuthResponse:
    """Đăng nhập bằng email + mật khẩu."""

    email = payload.email.lower().strip()
    result = await session.execute(
        select(User).options(selectinload(User.organization)).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    # Vẫn chạy verify khi không tìm thấy user để thời gian phản hồi không tiết lộ
    # email nào đã tồn tại.
    password_ok = verify_password(payload.password, user.password_hash) if user else False
    if user is None or not password_ok:
        raise INVALID_CREDENTIALS
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị vô hiệu hóa",
        )

    return AuthResponse(user=UserOut.model_validate(user), tokens=_token_pair(user))


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, session: SessionDep) -> TokenPair:
    """Cấp access token mới từ refresh token."""

    try:
        user_id = decode_token(payload.refresh_token, "refresh")
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không còn hiệu lực",
        )
    return _token_pair(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: CurrentUser, session: SessionDep) -> None:
    """Ghi nhận đăng xuất.

    JWT là stateless nên client phải tự xóa token. Endpoint này chỉ để lại dấu
    trong audit log; muốn vô hiệu hóa token ngay thì cần thêm denylist.
    """

    session.add(
        AuditLog(
            user_id=user.id,
            actor_email=user.email,
            action="logout",
            resource="user",
            resource_id=str(user.id),
        )
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    """Hồ sơ của người dùng đang đăng nhập."""

    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UpdateProfileRequest, user: CurrentUser, session: SessionDep
) -> UserOut:
    """Cập nhật tên và hồ sơ doanh nghiệp."""

    if payload.full_name:
        user.full_name = payload.full_name.strip()

    if payload.organization is not None:
        data = payload.organization.model_dump()
        if user.organization is None:
            organization = Organization(**data)
            session.add(organization)
            await session.flush()
            user.organization_id = organization.id
            user.organization = organization
        else:
            for field, value in data.items():
                setattr(user.organization, field, value)
        # Hồ sơ đổi (số lao động, kỳ khai thuế) thì lịch tuân thủ phải sinh lại.
        await session.flush()
        await generate_tasks_for_organization(session, user.organization)

    await session.commit()
    await session.refresh(user, attribute_names=["organization"])
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, session: SessionDep
) -> None:
    """Đổi mật khẩu; yêu cầu nhập đúng mật khẩu hiện tại."""

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu hiện tại không đúng",
        )
    user.password_hash = hash_password(payload.new_password)
    session.add(
        AuditLog(
            user_id=user.id,
            actor_email=user.email,
            action="change_password",
            resource="user",
            resource_id=str(user.id),
        )
    )
