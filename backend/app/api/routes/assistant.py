from fastapi import APIRouter
from app.schemas.assistant import AssistantRequest, AssistantResponse
from app.services.assistant_service import process_assistant_request

router = APIRouter()


@router.post("/assistant", response_model=AssistantResponse)
def assistant(request: AssistantRequest) -> AssistantResponse:
    return process_assistant_request(request)
