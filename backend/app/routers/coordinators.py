from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.routers.requests import CLOSED_STATUSES
from backend.app.schemas.phase1 import (
    CoordinatorAssignmentOut,
    CoordinatorInviteRequest,
    CoordinatorProgressUpdate,
    CoordinatorRespondRequest,
)

router = APIRouter(prefix="/api/coordinators", tags=["Emergency Coordinators"])


@router.get("/my-assignments", response_model=List[CoordinatorAssignmentOut])
def get_my_coordinator_assignments(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[CoordinatorAssignmentOut]:
    repo = get_repository(settings)
    rows = repo.list_my_coordinator_assignments(str(current_user["id"]))
    return [CoordinatorAssignmentOut(**r) for r in rows]


@router.get("/{request_id}", response_model=List[CoordinatorAssignmentOut])
def list_request_coordinators(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[CoordinatorAssignmentOut]:
    repo = get_repository(settings)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    uid = str(current_user["id"])
    if (
        current_user.get("role") != "admin"
        and str(req["requester_id"]) != uid
        and not repo.is_active_coordinator_for_request(uid, request_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view coordinators.")
    rows = repo.list_coordinators_for_request(request_id)
    return [CoordinatorAssignmentOut(**r) for r in rows]


@router.post("/{request_id}/invite", response_model=CoordinatorAssignmentOut, status_code=status.HTTP_201_CREATED)
def invite_emergency_coordinator(
    request_id: str,
    payload: CoordinatorInviteRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> CoordinatorAssignmentOut:
    repo = get_repository(settings)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if current_user.get("role") != "admin" and str(req["requester_id"]) != str(current_user["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requester can authorize an emergency coordinator.",
        )
    if req["status"] in CLOSED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot assign a coordinator to a closed request ({req['status']}).",
        )
    try:
        res = repo.invite_coordinator(
            request_row=req,
            requester_id=str(req["requester_id"]),
            coordinator_identifier=payload.coordinator_identifier,
            can_chat=payload.can_chat,
            can_contact_blood_banks=payload.can_contact_blood_banks,
            can_update_progress=payload.can_update_progress,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active LifeLink user matched that email or phone number.",
        )
    return CoordinatorAssignmentOut(**res)


@router.post("/{assignment_id}/respond", response_model=CoordinatorAssignmentOut)
def respond_to_coordinator_invite(
    assignment_id: str,
    payload: CoordinatorRespondRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> CoordinatorAssignmentOut:
    repo = get_repository(settings)
    res = repo.respond_to_coordinator_invite(
        assign_id=assignment_id,
        coordinator_user_id=str(current_user["id"]),
        accept=payload.accept,
    )
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coordinator invitation not found.")
    if res == "FORBIDDEN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this invitation.")
    if res == "REVOKED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This coordinator assignment was revoked by the requester.",
        )
    return CoordinatorAssignmentOut(**res)


@router.post("/{assignment_id}/revoke", response_model=CoordinatorAssignmentOut)
def revoke_emergency_coordinator(
    assignment_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> CoordinatorAssignmentOut:
    repo = get_repository(settings)
    res = repo.revoke_coordinator(
        assign_id=assignment_id,
        actor_id=str(current_user["id"]),
        is_admin=current_user.get("role") == "admin",
    )
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coordinator assignment not found.")
    if res == "FORBIDDEN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requester or administrator can revoke coordinator access.",
        )
    return CoordinatorAssignmentOut(**res)


@router.post("/{request_id}/progress")
def post_coordinator_progress_update(
    request_id: str,
    payload: CoordinatorProgressUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if req["status"] in CLOSED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot post updates to a {req['status']} request.",
        )
    uid = str(current_user["id"])
    if str(req["requester_id"]) != uid and not repo.is_active_coordinator_for_request(uid, request_id, "can_update_progress"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active emergency coordinator permission is required.",
        )
    return repo.add_coordinator_progress_update(request_row=req, actor_id=uid, notes=payload.notes)
