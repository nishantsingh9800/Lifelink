from typing import Any, Dict

from fastapi import APIRouter, Depends

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.routers.auth import _to_profile_response
from backend.app.schemas.auth import ProfileResponse
from backend.app.schemas.phase2 import UserPreferencesUpdate
from backend.app.schemas.user import ProfileUpdateRequest

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("/me", response_model=ProfileResponse)
def get_my_profile(current_user: Dict[str, Any] = Depends(get_current_user)) -> ProfileResponse:
    return _to_profile_response(current_user)


@router.patch("/me", response_model=ProfileResponse)
def update_my_profile(
    payload: ProfileUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ProfileResponse:
    """Update safe profile fields only; role and account_status cannot be modified here."""
    repo = get_repository(settings)
    updated = repo.update_profile(
        str(current_user["id"]),
        payload.model_dump(exclude_none=True),
    )
    return _to_profile_response(updated or current_user)


@router.get("/me/preferences")
def get_my_preferences(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    return repo.get_user_preferences(str(current_user["id"]))


@router.patch("/me/preferences")
def update_my_preferences(
    payload: UserPreferencesUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    return repo.update_user_preferences(
        str(current_user["id"]), payload.model_dump(exclude_none=True)
    )
