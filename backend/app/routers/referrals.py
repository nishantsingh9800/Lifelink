from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/referrals", tags=["Referrals & Community"])


@router.get("/me")
def get_my_referral_dashboard(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    summary = repo.get_or_create_referral_summary(str(current_user["id"]))
    base_url = str(request.base_url).rstrip("/")
    summary["referral_url"] = f"{base_url}/pages/register.html?ref={summary['referral_code']}"
    return summary
