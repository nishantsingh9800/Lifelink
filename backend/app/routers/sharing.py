from typing import Any, Dict, Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.routers.requests import CLOSED_STATUSES
from backend.app.schemas.phase2 import SharedRequestReportCreate

router = APIRouter(tags=["Public Request Sharing"])


@router.post("/api/share/{request_id}", status_code=status.HTTP_201_CREATED)
def generate_request_share_link(
    request_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to share this request.")
    if req["status"] in CLOSED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create share link for a closed request ({req['status']}).",
        )
    link = repo.create_or_get_share_link(request_id=request_id, actor_id=uid)
    base_url = str(request.base_url).rstrip("/")
    share_url = f"{base_url}/pages/shared-request.html?token={link['share_token']}"
    wa_text = quote_plus(
        f"Emergency Blood Coordination (LifeLink): {req['blood_group']} ({req['units_requested']} unit(s)) "
        f"needed at {req['hospital_name']}, {req['city']}. Live status: {share_url}"
    )
    return {
        **link,
        "share_url": share_url,
        "whatsapp_url": f"https://wa.me/?text={wa_text}",
    }


@router.post("/api/share/{request_id}/disable")
def disable_request_share_link(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if current_user.get("role") != "admin" and str(req["requester_id"]) != str(current_user["id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to disable this link.")
    res = repo.disable_share_link(request_id=request_id, actor_id=str(current_user["id"]))
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No share link found for this request.")
    return res


@router.get("/api/public/shared/{token}")
def view_public_shared_request(
    token: str,
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Return ONLY safe non-PII status fields; expire cleanly when closed or disabled."""
    repo = get_repository(settings)
    repo.expire_stale_requests()
    data = repo.get_public_shared_request_by_token(token)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared request link not found.")
    if data.get("expired_or_disabled"):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"This shared request link has expired or been disabled (request status: {data['status']}).",
        )
    return data


@router.post("/api/public/shared/{token}/report", status_code=status.HTTP_201_CREATED)
def report_suspicious_shared_request(
    token: str,
    payload: SharedRequestReportCreate,
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    rep = repo.report_shared_request_by_token(
        token=token,
        reporter_id=None,
        reason=payload.reason,
        description=payload.description,
    )
    if not rep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared request link not found.")
    return {"status": "reported", "report_id": rep["id"]}
