from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.deps import get_current_user, get_document_service
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentRetryResponse,
    DocumentUploadResponse,
)
from app.services.document_service import DocumentService

router = APIRouter()


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    collection_id: str = Form(...),
    file: UploadFile = File(...),
    service: DocumentService = Depends(get_document_service),
    current_user: dict = Depends(get_current_user),
) -> DocumentUploadResponse:
    record = await service.upload_document(
        upload=file,
        collection_id=collection_id,
        owner_id=current_user["id"],
    )
    return DocumentUploadResponse.model_validate(record)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    collection_id: str | None = None,
    service: DocumentService = Depends(get_document_service),
    current_user: dict = Depends(get_current_user),
) -> list[DocumentResponse]:
    documents = service.list_documents(owner_id=current_user["id"], collection_id=collection_id)
    return [DocumentResponse.model_validate(item) for item in documents]


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
    current_user: dict = Depends(get_current_user),
) -> DocumentDetailResponse:
    return DocumentDetailResponse.model_validate(
        service.get_document_detail(document_id, owner_id=current_user["id"])
    )


@router.post("/{document_id}/retry", response_model=DocumentRetryResponse)
def retry_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
    current_user: dict = Depends(get_current_user),
) -> DocumentRetryResponse:
    return DocumentRetryResponse.model_validate(
        service.retry_document(document_id, owner_id=current_user["id"])
    )


@router.delete("/{document_id}", response_model=DocumentResponse)
def delete_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
    current_user: dict = Depends(get_current_user),
) -> DocumentResponse:
    return DocumentResponse.model_validate(service.delete_document(document_id, owner_id=current_user["id"]))
