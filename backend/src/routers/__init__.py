"""Export router được dùng trong FastAPI app factory."""
from src.routers.admin import router as admin_router
from src.routers.auth import router as auth_router
from src.routers.compliance import router as compliance_router
from src.routers.conversations import router as conversations_router
from src.routers.documents import router as documents_router
from src.routers.health import router as health_router
from src.routers.lab import router as lab_router
from src.routers.laws import router as laws_router
from src.routers.legal import router as legal_router

__all__ = [
    "admin_router",
    "auth_router",
    "compliance_router",
    "conversations_router",
    "documents_router",
    "health_router",
    "lab_router",
    "laws_router",
    "legal_router",
]
