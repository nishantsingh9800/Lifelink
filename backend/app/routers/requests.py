from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import ConflictError, get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.schemas.phase1 import LiveRequestTrackingSummary
from backend.app.schemas.request import (
    BloodRequestCancel,
    BloodRequestCreate,
    BloodRequestOutcome,
    BloodRequestResponse,
    BloodRequestUpdate,
    RequestStatusHistoryItem,
)

router = APIRouter(prefix="/api/requests", tags=["Blood Requests"])

CLOSED_STATUSES = {"fulfilled", "unresolved", "cancelled", "expired"}


def _to_request_response(row: Dict[str, Any]) -> BloodRequestResponse:
    return BloodRequestResponse(
        id=str(row["id"]),
        requester_id=str(row["requester_id"]),
        created_by_user_id=str(row["created_by_user_id"]) if row.get("created_by_user_id") else str(row["requester_id"]),
        patient_reference_name=row["patient_reference_name"],
        blood_group=row["blood_group"],
        units_requested=int(row["units_requested"]),
        hospital_name=row["hospital_name"],
        hospital_location=row["hospital_location"],
        city=row["city"],
        approximate_location=row["approximate_location"],
        urgency=row["urgency"],
        additional_information=row.get("additional_information"),
        requester_contact_preference=row.get("requester_contact_preference", "in_app_chat"),
        status=row["status"],
        escalation_stage=int(row.get("escalation_stage", 1)),
        is_emergency_quick=bool(row.get("is_emergency_quick", False)),
        coordinator_contact_name=row.get("coordinator_contact_name"),
        coordinator_contact_relation=row.get("coordinator_contact_relation"),
        hospital_id=str(row["hospital_id"]) if row.get("hospital_id") else None,
        hospital_verification_status=row.get("hospital_verification_status") or "unconfirmed",
        hospital_confirmed_at=str(row["hospital_confirmed_at"]) if row.get("hospital_confirmed_at") else None,
        cancellation_reason=row.get("cancellation_reason"),
        requested_for=str(row["requested_for"]),
        expires_at=str(row["expires_at"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _authorize_request_access(repo: Any, request_row: Dict[str, Any], current_user: Dict[str, Any]) -> None:
    user_id = str(current_user["id"])
    if current_user.get("role") == "admin" or str(request_row["requester_id"]) == user_id:
        return
    if (
        str(request_row.get("created_by_user_id")) == user_id
        and repo.has_active_family_permission(
            owner_user_id=str(request_row["requester_id"]),
            member_user_id=user_id,
            permission="can_manage_requests",
        )
    ):
        return
    if repo.is_donor_matched_to_request(user_id, str(request_row["id"])):
        return
    if repo.is_active_coordinator_for_request(user_id, str(request_row["id"])):
        return
    if current_user.get("role") == "hospital":
        hosp = repo.get_hospital_by_user_id(user_id)
        if hosp and hosp.get("verification_status") == "verified" and repo.hospital_can_manage_request(hosp, request_row):
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You are not authorized to view this blood request.",
    )


@router.post("", response_model=BloodRequestResponse, status_code=status.HTTP_201_CREATED)
def create_blood_request(
    payload: BloodRequestCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> BloodRequestResponse:
    repo = get_repository(settings)
    repo.expire_stale_requests()

    if settings.require_aadhaar_for_actions and not current_user.get("aadhaar_verified"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aadhaar verification is required before receiving/requesting blood.",
        )

    target_requester_id = str(current_user["id"])
    created_by_id = str(current_user["id"])
    if payload.on_behalf_of_user_id and payload.on_behalf_of_user_id != created_by_id:
        if not repo.has_active_family_permission(
            owner_user_id=payload.on_behalf_of_user_id,
            member_user_id=created_by_id,
            permission="can_create_requests",
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have active family authorization to create a request for that account.",
            )
        target_requester_id = payload.on_behalf_of_user_id

    now = datetime.now(timezone.utc)
    default_hours = {
        "emergency": settings.expiry_hours_emergency,
        "urgent": settings.expiry_hours_urgent,
        "normal": settings.expiry_hours_normal,
    }[payload.urgency]
    expiry_hours = payload.expiry_hours or default_hours
    requested_for = payload.requested_for.isoformat() if payload.requested_for else now.isoformat()
    expires_at = (now + timedelta(hours=expiry_hours)).isoformat()

    try:
        created = repo.create_blood_request(
            requester_id=target_requester_id,
            created_by_user_id=created_by_id,
            patient_reference_name=payload.patient_reference_name,
            blood_group=payload.blood_group,
            units_requested=payload.units_requested,
            hospital_name=payload.hospital_name,
            hospital_location=payload.hospital_location,
            city=payload.city,
            approximate_location=payload.approximate_location,
            urgency=payload.urgency,
            additional_information=payload.additional_information,
            requester_contact_preference=payload.requester_contact_preference,
            requested_for=requested_for,
            expires_at=expires_at,
            is_emergency_quick=payload.is_emergency_quick,
            coordinator_contact_name=payload.coordinator_contact_name,
            coordinator_contact_relation=payload.coordinator_contact_relation,
            hospital_id=payload.hospital_id,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _to_request_response(created)


@router.get("", response_model=List[BloodRequestResponse])
def get_my_blood_requests(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[BloodRequestResponse]:
    repo = get_repository(settings)
    repo.expire_stale_requests()
    rows = repo.list_requests_for_user(str(current_user["id"]))
    return [_to_request_response(row) for row in rows]


@router.get("/{request_id}", response_model=BloodRequestResponse)
def get_blood_request_details(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> BloodRequestResponse:
    repo = get_repository(settings)
    repo.expire_stale_requests()
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    _authorize_request_access(repo, req, current_user)
    return _to_request_response(req)


@router.patch("/{request_id}", response_model=BloodRequestResponse)
def update_blood_request(
    request_id: str,
    payload: BloodRequestUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> BloodRequestResponse:
    repo = get_repository(settings)
    repo.expire_stale_requests()
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if str(req["requester_id"]) != str(current_user["id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the requester can modify this request.")
    if req["status"] in CLOSED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot modify a request that is already {req['status']}.",
        )

    updated = repo.update_blood_request(
        request_id=request_id,
        changed_by=str(current_user["id"]),
        updates=payload.model_dump(exclude_none=True),
    )
    return _to_request_response(updated)


@router.post("/{request_id}/cancel", response_model=BloodRequestResponse)
def cancel_blood_request(
    request_id: str,
    payload: BloodRequestCancel,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> BloodRequestResponse:
    repo = get_repository(settings)
    repo.expire_stale_requests()
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if str(req["requester_id"]) != str(current_user["id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the requester can cancel this request.")
    if req["status"] in CLOSED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request is already {req['status']}.",
        )

    cancelled = repo.cancel_blood_request(
        request_id=request_id,
        changed_by=str(current_user["id"]),
        reason=payload.reason or "Cancelled by requester",
    )
    return _to_request_response(cancelled)


@router.post("/{request_id}/outcome", response_model=BloodRequestResponse)
def record_request_outcome(
    request_id: str,
    payload: BloodRequestOutcome,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> BloodRequestResponse:
    """Record genuine request completion ('fulfilled') or keep/close as 'unresolved'."""
    repo = get_repository(settings)
    repo.expire_stale_requests()
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if current_user.get("role") != "admin" and str(req["requester_id"]) != str(current_user["id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the requester or admin can record outcome.")
    if req["status"] in ("fulfilled", "cancelled", "expired"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot record outcome on a {req['status']} request.",
        )

    updated = repo.record_request_outcome(
        request_row=req,
        changed_by=str(current_user["id"]),
        outcome=payload.outcome,
        donated_by_donor_id=payload.donated_by_donor_id,
        notes=payload.notes,
        cooldown_days=settings.donor_review_interval_days,
    )
    return _to_request_response(updated)


@router.get("/{request_id}/tracking-summary", response_model=LiveRequestTrackingSummary)
def get_live_tracking_summary(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> LiveRequestTrackingSummary:
    """Live 8-step request lifecycle tracking summary without exposing donor PII or phone numbers."""
    repo = get_repository(settings)
    repo.expire_stale_requests()
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    _authorize_request_access(repo, req, current_user)
    summary = repo.get_request_tracking_summary(request_id)
    assert summary is not None
    return LiveRequestTrackingSummary(**summary)


@router.get("/{request_id}/history", response_model=List[RequestStatusHistoryItem])
def get_request_history(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[RequestStatusHistoryItem]:
    repo = get_repository(settings)
    repo.expire_stale_requests()
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    _authorize_request_access(repo, req, current_user)
    rows = repo.get_request_status_history(request_id)
    return [RequestStatusHistoryItem(**row) for row in rows]
