from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
        vector_backend=settings.vector_backend,
        documents_dir=str(settings.raw_data_dir),
        indexes_dir=str(settings.faiss_index_dir),
    )
