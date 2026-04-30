from fastapi import APIRouter, Depends, status

from app.api.deps import get_collection_service, get_current_user, get_document_service
from app.schemas.collection import (
    CollectionCreateRequest,
    CollectionIngestResponse,
    CollectionResponse,
)
from app.services.collection_service import CollectionService
from app.services.document_service import DocumentService

router = APIRouter()


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
def create_collection(
    payload: CollectionCreateRequest,
    service: CollectionService = Depends(get_collection_service),
    current_user: dict = Depends(get_current_user),
) -> CollectionResponse:
    return CollectionResponse.model_validate(service.create_collection(payload, owner_id=current_user["id"]))


@router.get("", response_model=list[CollectionResponse])
def list_collections(
    service: CollectionService = Depends(get_collection_service),
    current_user: dict = Depends(get_current_user),
) -> list[CollectionResponse]:
    collections = service.list_collections(owner_id=current_user["id"])
    return [CollectionResponse.model_validate(item) for item in collections]


@router.post("/{collection_id}/ingest", response_model=CollectionIngestResponse)
def ingest_collection(
    collection_id: str,
    document_service: DocumentService = Depends(get_document_service),
    current_user: dict = Depends(get_current_user),
) -> CollectionIngestResponse:
    return document_service.ingest_collection(collection_id, owner_id=current_user["id"])
