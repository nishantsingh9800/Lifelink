from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.schemas.communication import ContactSharingStatusOut

router = APIRouter(prefix="/api/contact-sharing", tags=["Contact Sharing Consent"])


@router.get("/{request_id}", response_model=ContactSharingStatusOut)
def get_contact_sharing_status(
    request_id: str,
    donor_user_id: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ContactSharingStatusOut:
    repo = get_repository(settings)
    res = repo.get_contact_sharing_status(
        request_id=request_id,
        current_user_id=str(current_user["id"]),
        donor_user_id=donor_user_id,
    )
    if res == "FORBIDDEN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this contact-sharing pair.")
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact sharing record not found.")
    return ContactSharingStatusOut(**res)


@router.post("/{request_id}/consent", response_model=ContactSharingStatusOut)
def give_contact_sharing_consent(
    request_id: str,
    donor_user_id: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ContactSharingStatusOut:
    repo = get_repository(settings)
    res = repo.update_contact_sharing_consent(
        request_id=request_id,
        current_user_id=str(current_user["id"]),
        donor_user_id=donor_user_id,
        grant=True,
    )
    if res == "FORBIDDEN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this contact-sharing pair.")
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact sharing record not found.")
    return ContactSharingStatusOut(**res)


@router.post("/{request_id}/withdraw", response_model=ContactSharingStatusOut)
def withdraw_contact_sharing_consent(
    request_id: str,
    donor_user_id: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ContactSharingStatusOut:
    repo = get_repository(settings)
    res = repo.update_contact_sharing_consent(
        request_id=request_id,
        current_user_id=str(current_user["id"]),
        donor_user_id=donor_user_id,
        grant=False,
    )
    if res == "FORBIDDEN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this contact-sharing pair.")
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact sharing record not found.")
    return ContactSharingStatusOut(**res)
