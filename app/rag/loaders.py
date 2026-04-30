from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document

from app.core.exceptions import BadRequestError


def load_documents_from_path(file_path: Path) -> list[Document]:
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        loader = PyPDFLoader(str(file_path))
    elif suffix in {".doc", ".docx"}:
        loader = Docx2txtLoader(str(file_path))
    elif suffix == ".txt":
        loader = TextLoader(str(file_path), autodetect_encoding=True)
    else:
        raise BadRequestError(
            code="UNSUPPORTED_FILE_TYPE",
            message=f"Unsupported file type: {suffix}",
        )

    return loader.load()
