from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.routers.requests import CLOSED_STATUSES, _authorize_request_access
from backend.app.schemas.matching import DonorMatchOut, MatchingRunResponse

router = APIRouter(prefix="/api/matching", tags=["Matching & Escalation"])


def _require_open_requester_or_admin(repo: Any, request_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
    repo.expire_stale_requests()
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if current_user.get("role") != "admin" and str(req["requester_id"]) != str(current_user["id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to coordinate matching.")
    if req["status"] in CLOSED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot run matching or escalation on a {req['status']} request.",
        )
    return req


@router.post("/{request_id}/run", response_model=MatchingRunResponse)
def run_matching(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> MatchingRunResponse:
    """Identify, prioritize, and notify Stage 1 potential candidate donors."""
    repo = get_repository(settings)
    req = _require_open_requester_or_admin(repo, request_id, current_user)
    result = repo.run_matching_for_request(
        request_row=req,
        actor_id=str(current_user["id"]),
        stage=max(1, int(req.get("escalation_stage", 1))),
        max_new_notifications=settings.stage1_max_donors,
        review_interval_days=settings.donor_review_interval_days,
    )
    return MatchingRunResponse(**result)


@router.post("/{request_id}/escalate", response_model=MatchingRunResponse)
def escalate_request(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> MatchingRunResponse:
    """Advance progressive 5-stage emergency escalation."""
    repo = get_repository(settings)
    req = _require_open_requester_or_admin(repo, request_id, current_user)
    current_stage = int(req.get("escalation_stage", 1))
    next_stage = min(5, current_stage + 1)

    if next_stage in (2, 3):
        limit = settings.stage2_max_donors if next_stage == 2 else 25
        result = repo.run_matching_for_request(
            request_row=req,
            actor_id=str(current_user["id"]),
            stage=next_stage,
            max_new_notifications=limit,
            review_interval_days=settings.donor_review_interval_days,
        )
        return MatchingRunResponse(**result)

    # Stage 4: Blood-Bank Assistance | Stage 5: Hospital-Coordinated Wider Search
    result = repo.escalate_to_fallback_stage(
        request_row=req,
        actor_id=str(current_user["id"]),
        target_stage=next_stage,
    )
    return MatchingRunResponse(**result)


@router.get("/{request_id}/candidates", response_model=List[DonorMatchOut])
def get_request_candidates(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[DonorMatchOut]:
    """List prioritized potential candidates for a request (phone numbers and emails stripped)."""
    repo = get_repository(settings)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    _authorize_request_access(repo, req, current_user)
    rows = repo.list_matches_for_request(request_id)
    return [DonorMatchOut(**row) for row in rows]
