from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.schemas.communication import ConversationOut

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


@router.get("", response_model=List[ConversationOut])
def list_my_conversations(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[ConversationOut]:
    repo = get_repository(settings)
    rows = repo.list_conversations_for_user(str(current_user["id"]))
    return [ConversationOut(**r) for r in rows]


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation_details(
    conversation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ConversationOut:
    repo = get_repository(settings)
    conv = repo.get_conversation_for_participant(conversation_id, str(current_user["id"]))
    if conv == "FORBIDDEN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this conversation.",
        )
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return ConversationOut(**conv)
