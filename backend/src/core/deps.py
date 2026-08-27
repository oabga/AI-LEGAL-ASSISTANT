"""FastAPI dependency dùng chung: session DB, user hiện tại, kiểm tra quyền."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database import get_session
from src.core.security import TokenError, decode_token
from src.models import User, UserRole

# auto_error=False để tự trả lỗi 401 với thông báo tiếng Việt.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

SessionDep = Annotated[AsyncSession, Depends(get_session)]

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Chưa đăng nhập hoặc phiên đã hết hạn",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    request: Request,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    """Giải mã access token và trả về user còn hoạt động."""

    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_EXCEPTION

    try:
        user_id = decode_token(credentials.credentials, "access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    result = await session.execute(
        select(User).options(selectinload(User.organization)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise CREDENTIALS_EXCEPTION
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị vô hiệu hóa",
        )

    # Rate limiter đọc lại từ request.state để đếm quota theo user.
    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole):
    """Dependency factory chặn user không thuộc các role cho phép."""

    allowed = set(roles)

    async def checker(user: CurrentUser) -> User:
        # Admin luôn đi qua được mọi route có phân quyền.
        if user.role in allowed or user.role == UserRole.ADMIN:
            return user
        readable = ", ".join(sorted(role.value for role in allowed))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Chức năng này yêu cầu vai trò: {readable}",
        )

    return checker


require_admin = require_role(UserRole.ADMIN)
AdminUser = Annotated[User, Depends(require_admin)]


async def get_current_organization_id(user: CurrentUser):
    """Nhiều tính năng (hợp đồng, tuân thủ) cần user đã gắn doanh nghiệp."""

    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Tài khoản chưa gắn với doanh nghiệp nào. "
                "Cập nhật hồ sơ doanh nghiệp trước khi dùng chức năng này."
            ),
        )
    return user.organization_id
