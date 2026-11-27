from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.schemas.phase2 import FamilyContactInviteRequest, FamilyContactRespondRequest

router = APIRouter(prefix="/api/family", tags=["Family Emergency Account"])


@router.get("/contacts")
def list_family_contacts(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, List[Dict[str, Any]]]:
    repo = get_repository(settings)
    return repo.list_family_contacts_for_user(str(current_user["id"]))


@router.post("/contacts", status_code=status.HTTP_201_CREATED)
def invite_family_contact(
    payload: FamilyContactInviteRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    try:
        res = repo.invite_family_contact(
            owner_user_id=str(current_user["id"]),
            member_identifier=payload.member_identifier,
            relationship=payload.relationship,
            can_create_requests=payload.can_create_requests,
            can_manage_requests=payload.can_manage_requests,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active LifeLink user found matching that email or phone number.",
        )
    return res


@router.post("/contacts/{contact_id}/respond")
def respond_family_contact(
    contact_id: str,
    payload: FamilyContactRespondRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    res = repo.respond_family_contact(
        contact_id=contact_id,
        member_user_id=str(current_user["id"]),
        accept=payload.accept,
    )
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family authorization not found.")
    if res == "FORBIDDEN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to respond.")
    if res == "REVOKED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Family authorization was revoked.")
    return res


@router.post("/contacts/{contact_id}/revoke")
def revoke_family_contact(
    contact_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    res = repo.revoke_family_contact(
        contact_id=contact_id,
        actor_id=str(current_user["id"]),
        is_admin=current_user.get("role") == "admin",
    )
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family authorization not found.")
    if res == "FORBIDDEN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family account owner or admin can revoke authorization.",
        )
    return res
