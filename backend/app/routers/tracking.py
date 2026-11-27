from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.routers.requests import CLOSED_STATUSES

router = APIRouter(prefix="/api/tracking", tags=["Live Radius Tracking"])

SAFETY_RADIUS_METERS = 1000


def obfuscate_to_safety_zone(lat: float, lon: float) -> tuple[float, float, int]:
    """
    Quantize exact coordinates to a coarse ~1.1 km grid center so exact GPS
    locations are never stored or exposed, while preserving a Swiggy/Zomato-style radius zone.
    """
    zone_lat = round(float(lat), 2)
    zone_lon = round(float(lon), 2)
    return zone_lat, zone_lon, SAFETY_RADIUS_METERS


class LocationUpdateIn(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    tracking_status: Literal["en_route", "nearby", "arrived_at_hospital"] = "en_route"


class TrackingZoneOut(BaseModel):
    request_id: str
    donor_id: str
    donor_display_name: str
    zone_lat: float
    zone_lon: float
    radius_meters: int
    tracking_status: str
    distance_band: str
    is_active: bool
    updated_at: str
    privacy_notice: str = (
        "Exact coordinates are never stored or shared. Only an approximate ~1 km safety radius is displayed."
    )


def _ensure_accepted_donor(repo: Any, user_id: str, request_id: str) -> Dict[str, Any]:
    donor = repo.get_donor_profile_by_user_id(user_id)
    if not donor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Donor profile required.")
    responses = repo.list_responses_for_request(request_id)
    if not any(r["donor_id"] == str(donor["id"]) and r["response"] == "accepted" for r in responses):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an accepted donor for this request can share live arrival radius.",
        )
    return donor


@router.post("/{request_id}/update", response_model=TrackingZoneOut)
def update_donor_location_zone(
    request_id: str,
    payload: LocationUpdateIn,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> TrackingZoneOut:
    repo = get_repository(settings)
    repo.expire_stale_requests()
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if req["status"] in CLOSED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Location sharing is disabled because this request is {req['status']}.",
        )

    donor = _ensure_accepted_donor(repo, str(current_user["id"]), request_id)
    zone_lat, zone_lon, radius = obfuscate_to_safety_zone(payload.latitude, payload.longitude)
    band_map = {
        "en_route": "En route (within ~1 km radius zone)",
        "nearby": "Nearby (~1 km radius)",
        "arrived_at_hospital": "Arrived near hospital area (~1 km zone)",
    }
    row = repo.upsert_donor_tracking(
        request_id=request_id,
        donor_id=str(donor["id"]),
        zone_lat=zone_lat,
        zone_lon=zone_lon,
        radius_meters=radius,
        tracking_status=payload.tracking_status,
        distance_band=band_map[payload.tracking_status],
    )
    return TrackingZoneOut(**row)


@router.post("/{request_id}/stop")
def stop_donor_location_zone(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, str]:
    repo = get_repository(settings)
    donor = _ensure_accepted_donor(repo, str(current_user["id"]), request_id)
    repo.stop_donor_tracking(request_id=request_id, donor_id=str(donor["id"]))
    return {"status": "stopped", "message": "Live radius sharing stopped."}


@router.get("/{request_id}", response_model=List[TrackingZoneOut])
def get_request_tracking_zones(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[TrackingZoneOut]:
    repo = get_repository(settings)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")

    user_id = str(current_user["id"])
    is_admin = current_user.get("role") == "admin"
    is_requester = str(req["requester_id"]) == user_id
    if not is_admin and not is_requester:
        # Must be an accepted donor on this request
        _ensure_accepted_donor(repo, user_id, request_id)

    rows = repo.list_tracking_for_request(request_id)
    return [TrackingZoneOut(**r) for r in rows]
