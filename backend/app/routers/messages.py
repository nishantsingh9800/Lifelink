from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.schemas.communication import MessageCreate, MessageOut

router = APIRouter(prefix="/api/messages", tags=["Messages"])


def _ensure_participant(repo: Any, conversation_id: str, user_id: str) -> Dict[str, Any]:
    conv = repo.get_conversation_for_participant(conversation_id, user_id)
    if conv == "FORBIDDEN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access messages in this conversation.",
        )
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conv


@router.get("/{conversation_id}", response_model=List[MessageOut])
def get_messages(
    conversation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[MessageOut]:
    repo = get_repository(settings)
    user_id = str(current_user["id"])
    _ensure_participant(repo, conversation_id, user_id)
    rows = repo.list_messages(conversation_id, user_id)
    return [MessageOut(**r) for r in rows]


@router.post("/{conversation_id}", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    conversation_id: str,
    payload: MessageCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> MessageOut:
    repo = get_repository(settings)
    user_id = str(current_user["id"])
    conv = _ensure_participant(repo, conversation_id, user_id)
    if conv["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot send messages because this conversation is {conv['status']}.",
        )
    msg = repo.create_message(
        conversation_id=conversation_id,
        sender_id=user_id,
        counterpart_id=conv["counterpart_user_id"],
        request_id=conv["request_id"],
        message_text=payload.message_text.strip(),
        sender_full_name=current_user["full_name"],
    )
    return MessageOut(**msg)


@router.post("/{conversation_id}/read")
def mark_messages_read(
    conversation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, int]:
    repo = get_repository(settings)
    user_id = str(current_user["id"])
    _ensure_participant(repo, conversation_id, user_id)
    count = repo.mark_messages_read(conversation_id, user_id)
    return {"marked_read": count}
