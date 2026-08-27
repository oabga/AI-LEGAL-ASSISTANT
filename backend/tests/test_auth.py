"""Test xác thực: đăng ký, đăng nhập, refresh, phân quyền."""
from __future__ import annotations

import pytest

from tests.factories import PASSWORD, register, unique_email, unique_tax_code


async def test_register_returns_user_and_tokens(client):
    email = unique_email("owner")
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": "Trần Thị Chủ",
            "role": "owner",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["user"]["email"] == email
    assert payload["tokens"]["access_token"]
    assert payload["tokens"]["refresh_token"]
    # Không bao giờ được trả hash mật khẩu ra ngoài.
    assert "password_hash" not in payload["user"]


async def test_register_normalizes_email_case(client):
    email = unique_email("mixed")
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email.upper(),
            "password": PASSWORD,
            "full_name": "Người Dùng",
            "role": "accountant",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["user"]["email"] == email.lower()

    # Đăng nhập bằng chữ hoa vẫn phải vào được cùng tài khoản đó.
    login = await client.post(
        "/api/v1/auth/login", json={"email": email.upper(), "password": PASSWORD}
    )
    assert login.status_code == 200, login.text


async def test_duplicate_email_returns_409(client):
    account = await register(client)
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": account["email"],
            "password": PASSWORD,
            "full_name": "Trùng Email",
            "role": "hr",
        },
    )
    assert response.status_code == 409


async def test_duplicate_tax_code_returns_409_not_500(client):
    """Mã số thuế trùng phải là lỗi nghiệp vụ, không phải IntegrityError 500."""

    tax_code = unique_tax_code()
    organization = {
        "name": "Công ty TNHH Trùng MST",
        "tax_code": tax_code,
        "business_type": "Công ty TNHH một thành viên",
        "employee_count": 5,
    }

    first = await client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email("first"),
            "password": PASSWORD,
            "full_name": "Đăng Ký Trước",
            "role": "owner",
            "organization": organization,
        },
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email("second"),
            "password": PASSWORD,
            "full_name": "Đăng Ký Sau",
            "role": "owner",
            "organization": organization,
        },
    )
    assert second.status_code == 409
    assert tax_code in second.json()["detail"]


@pytest.mark.parametrize("password", ["short", "1234567"])
async def test_password_shorter_than_minimum_is_rejected(client, password):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email("weak"),
            "password": password,
            "full_name": "Mật Khẩu Ngắn",
            "role": "owner",
        },
    )
    assert response.status_code == 422


async def test_login_with_wrong_password_returns_401(client):
    account = await register(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": "SaiMatKhau#2026"},
    )
    assert response.status_code == 401


async def test_login_with_unknown_email_returns_401(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email("ghost"), "password": PASSWORD},
    )
    assert response.status_code == 401


async def test_me_requires_token(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_rejects_garbage_token(client):
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401


async def test_me_returns_profile(client):
    account = await register(client, with_organization=True)
    response = await client.get("/api/v1/auth/me", headers=account["headers"])

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["email"] == account["email"]
    assert payload["organization"]["name"] == "Công ty TNHH Kiểm Thử"


async def test_refresh_issues_new_access_token(client):
    account = await register(client)
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": account["tokens"]["refresh_token"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


async def test_access_token_cannot_be_used_as_refresh_token(client):
    """Trộn hai loại token là lỗ hổng kinh điển; ``typ`` trong payload phải chặn."""

    account = await register(client)
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": account["tokens"]["access_token"]},
    )
    assert response.status_code == 401


async def test_change_password_requires_current_password(client):
    account = await register(client)

    wrong = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "SaiHoanToan#2026", "new_password": "MatKhauMoi#2026"},
        headers=account["headers"],
    )
    assert wrong.status_code == 400

    ok = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "MatKhauMoi#2026"},
        headers=account["headers"],
    )
    assert ok.status_code == 204

    # Mật khẩu cũ hết hiệu lực, mật khẩu mới dùng được.
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": account["email"], "password": PASSWORD}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": account["email"], "password": "MatKhauMoi#2026"},
        )
    ).status_code == 200


async def test_update_profile_creates_organization(client):
    account = await register(client)
    response = await client.patch(
        "/api/v1/auth/me",
        json={
            "full_name": "Tên Đã Đổi",
            "organization": {
                "name": "Công ty CP Mới Thêm",
                "tax_code": unique_tax_code(),
                "business_type": "Công ty cổ phần",
                "employee_count": 30,
                "vat_period": "monthly",
            },
        },
        headers=account["headers"],
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["full_name"] == "Tên Đã Đổi"
    assert payload["organization"]["employee_count"] == 30


async def test_non_admin_cannot_reach_admin_route(client):
    account = await register(client, role="accountant")
    response = await client.get("/api/v1/admin/users", headers=account["headers"])
    assert response.status_code == 403
