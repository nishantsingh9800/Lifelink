from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user, require_roles

router = APIRouter(prefix="/api/integrations", tags=["Future External Integrations"])


@router.get("/status")
def get_integrations_readiness(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    """
    Report honest configuration status for optional Phase 4 external integrations.
    Never claims an unconfigured external API is live.
    """
    return {
        "supported_languages": [
            {"code": "en", "name": "English"},
            {"code": "hi", "name": "Hindi (हिन्दी)"},
            {"code": "mr", "name": "Marathi (मराठी)"},
            {"code": "bn", "name": "Bengali (বাংলা)"},
            {"code": "ta", "name": "Tamil (தமிழ்)"},
        ],
        "integrations": {
            "eraktkosh_live_sync": {
                "configured": bool(settings.eraktkosh_api_url.strip() and settings.eraktkosh_api_key.strip()),
                "status": "configured" if (settings.eraktkosh_api_url.strip() and settings.eraktkosh_api_key.strip()) else "not_configured",
                "fallback": "Official e-RaktKosh portal link and verified hospital/admin stock updates.",
            },
            "sms_otp": {
                "configured": bool(settings.is_supabase_configured and settings.supabase_phone_otp_enabled),
                "status": "configured" if (settings.is_supabase_configured and settings.supabase_phone_otp_enabled) else "not_configured",
                "fallback": "Local development verification helper when DEV_AUTH_MODE=true.",
            },
            "push_notifications": {
                "configured": bool(settings.push_notification_api_url.strip() and settings.push_notification_api_key.strip()),
                "status": "configured" if (settings.push_notification_api_url.strip() and settings.push_notification_api_key.strip()) else "not_configured",
                "fallback": "Real-time database-backed in-app notifications.",
            },
            "masked_calling": {
                "configured": bool(settings.masked_calling_api_url.strip() and settings.masked_calling_api_key.strip()),
                "status": "configured" if (settings.masked_calling_api_url.strip() and settings.masked_calling_api_key.strip()) else "not_configured",
                "fallback": "Private in-app chat and mutual-consent phone exchange.",
            },
            "hospital_sso_federation": {
                "configured": bool(settings.hospital_sso_metadata_url.strip()),
                "status": "configured" if settings.hospital_sso_metadata_url.strip() else "not_configured",
                "fallback": "Admin-reviewed hospital document verification.",
            },
        },
    }


@router.post("/eraktkosh/sync")
def trigger_eraktkosh_sync(
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    if not settings.eraktkosh_api_url.strip() or not settings.eraktkosh_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Live e-RaktKosh inventory sync is not configured. Supply ERATKOSH_API_URL and "
                "ERATKOSH_API_KEY in .env to enable automated blood-stock integration."
            ),
        )
    return {"status": "ready", "endpoint": settings.eraktkosh_api_url.strip()}


@router.post("/masked-call/{request_id}/initiate")
def initiate_masked_call(
    request_id: str,
    donor_user_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    consent = repo.get_contact_sharing_status(
        request_id=request_id,
        current_user_id=str(current_user["id"]),
        donor_user_id=donor_user_id,
    )
    if consent == "FORBIDDEN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this conversation.")
    if not consent or consent.get("status") != "both_consented":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Both requester and donor must consent before initiating direct phone or masked calling.",
        )
    if not settings.masked_calling_api_url.strip() or not settings.masked_calling_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Masked telephony relay is not configured yet. Configure MASKED_CALLING_API_URL "
                "and MASKED_CALLING_API_KEY, or continue using private in-app chat."
            ),
        )
    return {"status": "bridge_configured", "request_id": request_id}


@router.post("/push/dispatch")
def dispatch_push_notification(
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    if not settings.push_notification_api_url.strip() or not settings.push_notification_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "External push notification gateway is not configured. Set PUSH_NOTIFICATION_API_URL "
                "and PUSH_NOTIFICATION_API_KEY in .env; in-app notifications remain active."
            ),
        )
    return {"status": "push_gateway_configured"}
