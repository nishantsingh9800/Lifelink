from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.routers.requests import CLOSED_STATUSES, _authorize_request_access
from backend.app.schemas.matching import (
    DonorResponseCreate,
    DonorResponseOut,
    IncomingRequestItem,
)
from backend.app.services.face_verification import (
    FaceDetectionError,
    compare_descriptors,
    decode_base64_image,
    extract_face_descriptor,
)

router = APIRouter(prefix="/api/responses", tags=["Donor Responses"])


@router.get("/incoming", response_model=List[IncomingRequestItem])
def get_incoming_alerts(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[IncomingRequestItem]:
    """List blood requests matched to the authenticated donor."""
    repo = get_repository(settings)
    repo.expire_stale_requests()
    rows = repo.list_incoming_requests_for_donor(str(current_user["id"]))
    return [IncomingRequestItem(**row) for row in rows]


@router.post("/{request_id}/respond", response_model=DonorResponseOut)
def respond_to_request(
    request_id: str,
    payload: DonorResponseCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DonorResponseOut:
    """Record a donor's 'I CAN HELP' (accepted) or 'NOT AVAILABLE' (declined) response."""
    repo = get_repository(settings)
    repo.expire_stale_requests()

    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only users with a donor profile can respond to requests.",
        )

    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if req["status"] in CLOSED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This request is already {req['status']} and no longer accepting responses.",
        )
    if not repo.is_donor_matched_to_request(str(current_user["id"]), request_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You were not notified as a candidate for this request.",
        )

    if payload.response == "accepted":
        if settings.require_aadhaar_for_actions and not current_user.get("aadhaar_verified"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Aadhaar verification is required before donating / accepting a blood request.",
            )
        frozen_until = donor.get("donor_frozen_until")
        if frozen_until:
            from datetime import date, datetime

            try:
                if date.fromisoformat(str(frozen_until)[:10]) > datetime.now().date():
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=(
                            f"Your donor profile is frozen until {str(frozen_until)[:10]} "
                            "(3-month cooldown after donation)."
                        ),
                    )
            except ValueError:
                pass
        enrolled = repo.get_face_descriptor(str(donor["id"]))
        if enrolled:
            if payload.face_image_base64:
                try:
                    raw = decode_base64_image(payload.face_image_base64)
                    candidate, _ = extract_face_descriptor(raw)
                except FaceDetectionError as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
                matched, score = compare_descriptors(
                    enrolled, candidate, threshold=settings.face_match_threshold
                )
                repo.log_face_verification(
                    donor_id=str(donor["id"]),
                    request_id=request_id,
                    similarity_score=score,
                    verified=matched,
                    reason="Acceptance live face check" if matched else "Acceptance face mismatch",
                )
                if not matched:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Face verification failed (similarity {score:.2f} < {settings.face_match_threshold:.2f}). Only the registered donor can accept.",
                    )
            elif not repo.has_verified_face_for_request(str(donor["id"]), request_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Live face verification is required before confirming 'I CAN HELP'.",
                )

    res = repo.record_donor_response(
        request_row=req,
        donor_profile=donor,
        donor_user=current_user,
        response_value=payload.response,
    )
    if payload.response == "accepted" and payload.latitude is not None and payload.longitude is not None:
        from backend.app.routers.tracking import obfuscate_to_safety_zone

        z_lat, z_lon, radius = obfuscate_to_safety_zone(payload.latitude, payload.longitude)
        repo.upsert_donor_tracking(
            request_id=request_id,
            donor_id=str(donor["id"]),
            zone_lat=z_lat,
            zone_lon=z_lon,
            radius_meters=radius,
            tracking_status="en_route",
            distance_band="En route (within ~1 km radius zone)",
        )
    return DonorResponseOut(**res)


@router.get("/{request_id}", response_model=List[DonorResponseOut])
def get_request_responses(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[DonorResponseOut]:
    """List recorded donor responses for a request."""
    repo = get_repository(settings)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    _authorize_request_access(repo, req, current_user)
    rows = repo.list_responses_for_request(request_id)
    return [DonorResponseOut(**row) for row in rows]
