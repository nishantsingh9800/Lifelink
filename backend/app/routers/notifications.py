from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.schemas.matching import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("", response_model=List[NotificationOut])
def list_my_notifications(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[NotificationOut]:
    repo = get_repository(settings)
    rows = repo.list_notifications(str(current_user["id"]))
    return [NotificationOut(**row) for row in rows]


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> NotificationOut:
    repo = get_repository(settings)
    updated = repo.mark_notification_read(notification_id, str(current_user["id"]))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    return NotificationOut(**updated)


@router.post("/read-all")
def mark_all_notifications_read(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, int]:
    repo = get_repository(settings)
    count = repo.mark_all_notifications_read(str(current_user["id"]))
    return {"marked_read": count}
