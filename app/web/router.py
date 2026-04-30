from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@router.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@router.get("/register", include_in_schema=False)
def register_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "register.html")
