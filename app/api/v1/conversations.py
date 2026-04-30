from fastapi import APIRouter, Depends

from app.api.deps import get_conversation_service, get_current_user
from app.schemas.chat import ConversationDetailResponse, ConversationSummaryResponse
from app.services.conversation_service import ConversationService

router = APIRouter()


@router.get("", response_model=list[ConversationSummaryResponse])
def list_conversations(
    collection_id: str | None = None,
    service: ConversationService = Depends(get_conversation_service),
    current_user: dict = Depends(get_current_user),
) -> list[ConversationSummaryResponse]:
    conversations = service.list_conversations(owner_id=current_user["id"], collection_id=collection_id)
    return [ConversationSummaryResponse.model_validate(item) for item in conversations]


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation_detail(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
    current_user: dict = Depends(get_current_user),
) -> ConversationDetailResponse:
    return ConversationDetailResponse.model_validate(
        service.get_conversation_detail(conversation_id, owner_id=current_user["id"])
    )
