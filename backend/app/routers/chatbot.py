from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.services.chatbot import generate_assistant_reply

router = APIRouter(prefix="/api/chatbot", tags=["LifeLink Assistant"])


class ChatbotMessageIn(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=1000)


class ChatbotAction(BaseModel):
    label: str
    url: str


class ChatbotMessageOut(BaseModel):
    session_id: str
    intent: str
    reply: str
    suggested_actions: List[ChatbotAction]
    disclaimer: str


@router.post("/message", response_model=ChatbotMessageOut)
def send_chatbot_message(
    payload: ChatbotMessageIn,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ChatbotMessageOut:
    """Process a user prompt using LifeLink's rule-based assistant and persist session history."""
    repo = get_repository(settings)
    user_id = str(current_user["id"])
    session_id = repo.get_or_create_chatbot_session(user_id, payload.session_id)
    repo.append_chatbot_message(session_id, "user", payload.message.strip())

    result = generate_assistant_reply(message=payload.message, user=current_user, repo=repo)
    repo.append_chatbot_message(session_id, "assistant", result["reply"])

    return ChatbotMessageOut(
        session_id=session_id,
        intent=result["intent"],
        reply=result["reply"],
        suggested_actions=[ChatbotAction(**a) for a in result["suggested_actions"]],
        disclaimer=result["disclaimer"],
    )


@router.get("/history")
def get_chatbot_history(
    session_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    return repo.get_chatbot_history(str(current_user["id"]), session_id)
