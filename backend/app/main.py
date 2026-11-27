from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.app.config import PROJECT_ROOT, Settings, get_settings
from backend.app.database import DatabaseUnavailableError, get_repository
from backend.app.middleware.rate_limit import SecurityAndRateLimitMiddleware
from backend.app.routers import (
    admin,
    auth,
    blood_banks,
    chatbot,
    contact_sharing,
    conversations,
    coordinators,
    donors,
    family,
    hospitals,
    integrations,
    matching,
    messages,
    notifications,
    public,
    referrals,
    reports,
    requests,
    responses,
    sharing,
    tracking,
    users,
)

FRONTEND_DIR = PROJECT_ROOT / "frontend"


def create_app(custom_settings: Settings | None = None) -> FastAPI:
    settings = custom_settings or get_settings()

    app = FastAPI(
        title="LifeLink API",
        description=(
            "Smart Blood Donor Matching & Emergency Response System — "
            "Coordination platform backend with role-based access and privacy controls."
        ),
        version="0.1.0",
    )

    if custom_settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(
        SecurityAndRateLimitMiddleware,
        max_requests_per_minute=settings.rate_limit_requests_per_minute,
    )

    @app.exception_handler(DatabaseUnavailableError)
    async def db_unavailable_handler(_request: Request, exc: DatabaseUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Database service is temporarily unavailable. Please try again shortly.",
                "error": str(exc),
            },
        )

    @app.get("/api/health", tags=["System"])
    def healthcheck() -> Dict[str, Any]:
        # Touch repository to ensure DB initialization is valid
        get_repository(settings)
        return {
            "status": "ok",
            "app": settings.app_name,
            "storage_mode": settings.storage_mode,
            "auth_mode": settings.auth_mode,
            "phase": "phase-1-foundation",
        }

    @app.get("/api/config/public", tags=["System"])
    def public_config() -> Dict[str, Any]:
        """Expose ONLY public, non-secret configuration to the frontend."""
        return {
            "app_name": settings.app_name,
            "supabase_url": settings.supabase_url if settings.is_supabase_configured else "",
            "supabase_anon_key": settings.supabase_anon_key if settings.is_supabase_configured else "",
            "auth_mode": settings.auth_mode,
            "dev_auth_mode": settings.dev_auth_mode and not settings.is_supabase_configured,
            "phone_otp_enabled": settings.supabase_phone_otp_enabled and settings.is_supabase_configured,
            "aadhaar_kyc_enabled": settings.aadhaar_kyc_enabled,
            "require_aadhaar_for_actions": settings.require_aadhaar_for_actions,
        }

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(donors.router)
    app.include_router(requests.router)
    app.include_router(matching.router)
    app.include_router(responses.router)
    app.include_router(notifications.router)
    app.include_router(conversations.router)
    app.include_router(messages.router)
    app.include_router(contact_sharing.router)
    app.include_router(reports.router)
    app.include_router(chatbot.router)
    app.include_router(blood_banks.router)
    app.include_router(tracking.router)
    app.include_router(hospitals.router)
    app.include_router(coordinators.router)
    app.include_router(family.router)
    app.include_router(sharing.router)
    app.include_router(referrals.router)
    app.include_router(integrations.router)
    app.include_router(public.router)
    app.include_router(admin.router)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        svg_path = FRONTEND_DIR / "assets" / "favicon.svg"
        if svg_path.exists():
            return FileResponse(str(svg_path), media_type="image/svg+xml")
        return Response(status_code=204)

    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

    return app


app = create_app()
