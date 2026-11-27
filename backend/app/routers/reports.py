from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.schemas.communication import BlockUserRequest, ReportCreate

router = APIRouter(prefix="/api/reports", tags=["Reports & Blocking"])


@router.post("", status_code=status.HTTP_201_CREATED)
def submit_report(
    payload: ReportCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    if not payload.reported_user_id and not payload.request_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Please specify a user or request to report.",
        )
    repo = get_repository(settings)
    return repo.create_report(
        reporter_id=str(current_user["id"]),
        reported_user_id=payload.reported_user_id,
        request_id=payload.request_id,
        reason=payload.reason,
        description=payload.description,
    )


@router.post("/block", status_code=status.HTTP_201_CREATED)
def block_user(
    payload: BlockUserRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, str]:
    if payload.blocked_user_id == str(current_user["id"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot block yourself.")
    repo = get_repository(settings)
    repo.block_user(
        blocker_id=str(current_user["id"]),
        blocked_user_id=payload.blocked_user_id,
        conversation_id=payload.conversation_id,
        reason=payload.reason or "Blocked by user",
    )
    return {"status": "blocked", "message": "User blocked and conversation closed."}
