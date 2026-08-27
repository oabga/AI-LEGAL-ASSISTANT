"""Fixture dùng chung cho pytest.

Test chạy trên **PostgreSQL thật** (database riêng ``*_test``) chứ không phải
SQLite, vì phần tra cứu văn bản dựa hẳn vào ``tsvector``, ``unaccent`` và
``pg_trgm`` — SQLite không có những thứ đó nên test trên SQLite sẽ xanh mà
production vẫn vỡ.

Database test được tạo lại từ đầu mỗi lần chạy và migrate bằng chính Alembic
đang dùng cho production, nên schema trong test luôn khớp schema thật.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TEST_DB_SUFFIX = "_test"


def _base_database_url() -> str:
    """DSN của PostgreSQL dev, đọc theo đúng thứ tự ưu tiên của app.

    Tạo ``Settings()`` mới thay vì dùng ``get_settings()`` để không phụ thuộc vào
    trạng thái cache tại thời điểm gọi.
    """

    from src.config import Settings

    return Settings().legal_assistant.postgres.database_url


def _swap_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{name}"))


def _database_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/") or "postgres"


def pytest_configure(config: pytest.Config) -> None:
    """Trỏ toàn bộ app sang database test trước khi có test nào chạy.

    Chỉ set biến môi trường là chưa đủ: ``src/config.py`` gọi ``get_settings()``
    ngay ở cấp module, nên chỉ cần import ``src.config`` để đọc DSN hiện tại là
    Settings đã bị cache với database dev. Phải xóa cache của cả settings, engine
    và session factory sau khi đổi env, nếu không test sẽ chạy thẳng trên dữ liệu
    thật mà vẫn xanh.
    """

    from src.config import get_settings
    from src.core.database import get_engine, get_session_factory

    base = _base_database_url()
    test_name = _database_name(base) + TEST_DB_SUFFIX
    os.environ["LEGAL_DATABASE_URL"] = _swap_database(base, test_name)
    os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-used-in-production")
    # Dummy key để ChatOpenAI khởi tạo được; test hỏi đáp không gọi LLM vì
    # index_ready=False và endpoint trả 503 trước.
    os.environ.setdefault("LLM_API_KEY", "test-dummy-key-not-used")

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    # Vài client (LLM, embeddings) giữ tham chiếu tới object settings cũ ở cấp
    # module; cập nhật luôn để chúng không trỏ về database dev.
    import src.config

    src.config.settings = get_settings()

    resolved = get_settings().legal_assistant.postgres.database_url
    assert _database_name(resolved) == test_name, (
        f"Test đang trỏ vào database {_database_name(resolved)!r} thay vì {test_name!r}"
    )

    config.stash["legal_base_url"] = base
    config.stash["legal_test_db"] = test_name


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def database(pytestconfig: pytest.Config):
    """Dựng database test sạch, migrate, rồi xóa khi cả session kết thúc."""

    import asyncpg
    from alembic import command
    from alembic.config import Config

    base_url = pytestconfig.stash["legal_base_url"]
    test_name = pytestconfig.stash["legal_test_db"]
    # CREATE DATABASE không chạy được trong transaction nên phải nối vào
    # database quản trị mặc định.
    admin_dsn = _swap_database(base_url, "postgres")

    connection = await asyncpg.connect(admin_dsn)
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS "{test_name}" WITH (FORCE)')
        await connection.execute(f'CREATE DATABASE "{test_name}"')
    finally:
        await connection.close()

    # init.sql chỉ chạy tự động cho database mặc định của container, nên database
    # test phải tự cài unaccent/pg_trgm và immutable_unaccent — thiếu chúng thì
    # migration tạo generated column tsvector sẽ fail.
    bootstrap = (BACKEND_ROOT / "docker" / "postgres" / "init.sql").read_text(encoding="utf-8")
    connection = await asyncpg.connect(_swap_database(base_url, test_name))
    try:
        await connection.execute(bootstrap)
    finally:
        await connection.close()

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    # alembic/env.py gọi asyncio.run(), không chạy được bên trong loop của
    # pytest-asyncio; đẩy sang thread riêng để nó có loop của chính nó.
    await asyncio.to_thread(command.upgrade, alembic_config, "head")

    yield

    from src.core.database import dispose_engine

    await dispose_engine()

    connection = await asyncpg.connect(admin_dsn)
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS "{test_name}" WITH (FORCE)')
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def app():
    """FastAPI app chỉ gắn router cần test, không chạy lifespan.

    Bỏ lifespan để test không cần Chroma index hay API key của Gemini.
    """

    from fastapi import FastAPI

    from src.core.rate_limit import install_rate_limiter
    from src.routers import (
        admin_router,
        auth_router,
        compliance_router,
        conversations_router,
        documents_router,
        laws_router,
        legal_router,
    )
    from src.config import get_settings

    settings = get_settings()
    # Tắt rate limit trong test: các case gọi cùng endpoint nhiều lần liên tiếp.
    settings.rate_limit.enabled = False

    instance = FastAPI(title="test")
    # Không dựng Chroma trong test; endpoint hỏi đáp phải trả 503 thay vì gọi LLM.
    instance.state.index_ready = False
    install_rate_limiter(instance, settings)
    for router in (
        auth_router,
        conversations_router,
        laws_router,
        compliance_router,
        documents_router,
        admin_router,
        legal_router,
    ):
        instance.include_router(router)
    return instance


@pytest_asyncio.fixture
async def client(app):
    """AsyncClient gọi app qua ASGI transport, không mở socket thật."""

    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30
    ) as instance:
        yield instance


@pytest_asyncio.fixture
async def session():
    """Session ORM để test tự chuẩn bị / kiểm chứng dữ liệu."""

    from src.core.database import get_session_factory

    async with get_session_factory()() as instance:
        yield instance
