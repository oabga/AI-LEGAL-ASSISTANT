"""Entry point FastAPI của backend trợ lý pháp lý.

Đăng ký toàn bộ router (auth, chat, tra cứu văn bản, hợp đồng, tuân thủ, admin)
và lifecycle startup. Pipeline dựng index retrieval nằm trong module
``vector_store``; main chỉ gọi nó một lần trước khi nhận request.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.core.database import dispose_engine, get_session_factory, verify_connection
from src.core.rate_limit import install_rate_limiter
from src.routers import (
    admin_router,
    auth_router,
    compliance_router,
    conversations_router,
    documents_router,
    health_router,
    lab_router,
    laws_router,
    legal_router,
)
from src.services.compliance.generator import ensure_rules_seeded
from src.services.legal.catalog import sync_law_catalog
from src.services.vector_store.index_builder import initialize_legal_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Kiểm tra DB, dựng retrieval index, rồi mới nhận request."""

    settings = app.state.settings

    if settings.auth.is_insecure_default:
        logger.warning(
            "JWT_SECRET_KEY đang dùng giá trị mặc định. Set biến môi trường thật trước khi deploy."
        )
    if not settings.llm.api_key:
        logger.warning("LLM_API_KEY chưa được set; các endpoint cần LLM sẽ lỗi khi gọi.")

    await verify_connection()
    settings.uploads.directory.mkdir(parents=True, exist_ok=True)

    async with get_session_factory()() as session:
        # Danh mục văn bản dẫn xuất từ corpus, nên đồng bộ lại mỗi lần khởi động
        # để trang tra cứu khớp với dữ liệu vừa import.
        await sync_law_catalog(session)
        await ensure_rules_seeded(session)

    # Dựng index không được là điều kiện sống của cả backend: thiếu API key hay
    # provider embedding lỗi thì tra cứu văn bản, đăng nhập và lịch tuân thủ vẫn
    # phải dùng được. Chỉ chat/RAG là chịu ảnh hưởng, và endpoint đó sẽ tự báo
    # lỗi rõ ràng khi được gọi.
    app.state.index_ready = False
    try:
        await initialize_legal_index(settings)
        app.state.index_ready = True
    except Exception as exc:
        logger.error(
            "Không dựng được vector index nên chức năng hỏi đáp sẽ không hoạt động. "
            "Các phần khác (đăng nhập, tra cứu văn bản, lịch tuân thủ) vẫn chạy bình thường. "
            "Sau khi khắc phục, gọi POST /api/v1/admin/corpus/reindex để dựng lại. Chi tiết: %s",
            exc,
        )

    try:
        yield
    finally:
        await dispose_engine()


def create_app() -> FastAPI:
    """Tạo FastAPI app cho backend trợ lý pháp lý."""

    settings = get_settings()
    app = FastAPI(
        title="Trợ lý Pháp lý AI cho Doanh nghiệp",
        description=(
            "API tra cứu và hỏi đáp pháp luật doanh nghiệp Việt Nam: Luật Doanh nghiệp, "
            "thuế, lao động, hợp đồng, sở hữu trí tuệ."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    # Frontend là SPA chạy ở origin khác trong dev, và cần cookie/Authorization
    # header, nên allow_credentials=True buộc allow_origins phải là danh sách
    # tường minh (không được dùng "*").
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allow_origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count"],
    )
    # Lưu settings vào app.state để middleware/tooling đọc lại không cần parse YAML.
    app.state.settings = settings
    install_rate_limiter(app, settings)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(legal_router)
    app.include_router(laws_router)
    app.include_router(documents_router)
    app.include_router(compliance_router)
    app.include_router(admin_router)
    app.include_router(lab_router)
    return app


app = create_app()
