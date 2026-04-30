import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_service, get_current_user
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter()


def _encode_sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/completions",
    response_model=ChatResponse,
    responses={
        200: {
            "content": {
                "application/json": {},
                "text/event-stream": {},
            }
        }
    },
)
def create_chat_completion(
    payload: ChatRequest,
    service: ChatService = Depends(get_chat_service),
    current_user: dict = Depends(get_current_user),
) -> ChatResponse | StreamingResponse:
    if payload.stream:
        return StreamingResponse(
            (_encode_sse_event(item["event"], item["data"]) for item in service.stream_chat(payload, owner_id=current_user["id"])),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    return service.chat(payload, owner_id=current_user["id"])
