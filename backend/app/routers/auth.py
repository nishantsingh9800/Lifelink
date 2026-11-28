from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.database import (
    AuthenticationError,
    ConflictError,
    LocalDevSQLiteRepository,
    SupabaseRepository,
    get_repository,
)
from backend.app.dependencies.auth import get_current_user
from backend.app.schemas.auth import (
    AadhaarVerifyInitRequest,
    AuthResponse,
    LoginRequest,
    PhoneOtpSendRequest,
    PhoneOtpVerifyRequest,
    ProfileResponse,
    RegisterRequest,
)
from backend.app.utils.security import (
    compute_aadhaar_hash,
    create_aadhaar_dev_token,
    create_dev_access_token,
    mask_aadhaar_last4,
    normalize_phone,
    verify_aadhaar_dev_token,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _to_profile_response(profile: Dict[str, Any]) -> ProfileResponse:
    last4 = profile.get("aadhaar_last4") or "0000"
    return ProfileResponse(
        id=str(profile["id"]),
        full_name=profile["full_name"],
        email=profile.get("email"),
        phone_number=profile["phone_number"],
        role=profile["role"],
        city=profile["city"],
        approximate_location=profile["approximate_location"],
        date_of_birth=profile.get("date_of_birth"),
        account_status=profile["account_status"],
        phone_verified=bool(profile.get("phone_verified", False)),
        aadhaar_masked=mask_aadhaar_last4(str(last4)),
        aadhaar_verified=bool(profile.get("aadhaar_verified", False)),
        preferred_language=profile.get("preferred_language", "en"),
        created_at=str(profile["created_at"]),
    )


@router.post("/aadhaar/verify-init")
def initiate_aadhaar_verification(
    payload: AadhaarVerifyInitRequest,
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """
    Validate 12-digit Aadhaar (Verhoeff checksum + duplicate check) during signup.
    Uses configured e-KYC provider when AADHAAR_KYC_ENABLED=true, or clearly labelled
    Local Development Mode verification otherwise. Plaintext Aadhaar is never stored.
    """
    repo = get_repository(settings)
    aadhaar_hash = compute_aadhaar_hash(payload.aadhaar_number, settings)
    if repo.is_aadhaar_registered(aadhaar_hash):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this Aadhaar number is already registered.",
        )

    last4 = payload.aadhaar_number[-4:]
    if settings.aadhaar_kyc_enabled:
        if not settings.aadhaar_kyc_api_url or not settings.aadhaar_kyc_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Aadhaar e-KYC provider credentials are incomplete.",
            )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Configure external e-KYC API adapter for live UIDAI OTP.",
        )

    if not settings.dev_auth_mode or settings.is_supabase_configured:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Live Aadhaar e-KYC provider is required in production mode.",
        )

    dev_token = create_aadhaar_dev_token(aadhaar_hash, settings)
    return {
        "aadhaar_masked": mask_aadhaar_last4(last4),
        "mode": "dev_only",
        "aadhaar_verification_token": dev_token,
        "message": (
            f"Aadhaar {mask_aadhaar_last4(last4)} passed Verhoeff validation and duplicate check "
            "(Development-Only verification active; no live UIDAI API connected)."
        ),
    }


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, settings: Settings = Depends(get_settings)) -> AuthResponse:
    """Register a requester or donor account with mandatory Aadhaar validation (admin role cannot be self-assigned)."""
    if payload.role_preference == "donor" and not payload.blood_group:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Blood group is required when registering as a donor.",
        )

    aadhaar_hash = compute_aadhaar_hash(payload.aadhaar_number, settings) if payload.aadhaar_number else None
    aadhaar_last4 = payload.aadhaar_number[-4:] if payload.aadhaar_number else "0000"
    aadhaar_verified = False
    if (
        aadhaar_hash
        and payload.aadhaar_verification_token
        and settings.dev_auth_mode
        and not settings.is_supabase_configured
        and verify_aadhaar_dev_token(payload.aadhaar_verification_token, aadhaar_hash, settings)
    ):
        aadhaar_verified = True

    repo = get_repository(settings)
    try:
        profile = repo.create_user(
            full_name=payload.full_name,
            email=payload.email,
            phone_number=payload.phone_number,
            password=payload.password,
            city=payload.city,
            approximate_location=payload.approximate_location,
            date_of_birth=payload.date_of_birth.isoformat() if payload.date_of_birth else None,
            role_preference=payload.role_preference,
            blood_group=payload.blood_group,
            aadhaar_last4=aadhaar_last4,
            aadhaar_hash=aadhaar_hash,
            aadhaar_verified=aadhaar_verified,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if payload.referral_code and aadhaar_hash:
        repo.apply_referral_on_registration(
            referral_code=payload.referral_code,
            new_user_id=str(profile["id"]),
            new_aadhaar_hash=aadhaar_hash,
        )
    elif payload.referral_code:
        repo.apply_referral_on_registration(
            referral_code=payload.referral_code,
            new_user_id=str(profile["id"]),
            new_aadhaar_hash=f"no-aadhaar-{profile['id']}",
        )

    if isinstance(repo, LocalDevSQLiteRepository):
        token = create_dev_access_token(profile, settings)
        return AuthResponse(
            access_token=token,
            auth_mode="dev_only",
            user=_to_profile_response(profile),
            message="Registered in Local Development Mode. Complete phone verification to mark account verified.",
        )

    # Supabase mode: attempt immediate sign-in if email confirmation is disabled
    try:
        auth_result = repo.authenticate_supabase(payload.email, payload.password)
        token = auth_result["access_token"]
        msg = "Account registered successfully."
    except AuthenticationError:
        token = ""
        msg = "Account created. Please verify your email/phone via Supabase before logging in."

    return AuthResponse(
        access_token=token,
        auth_mode="supabase",
        user=_to_profile_response(profile),
        message=msg,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, settings: Settings = Depends(get_settings)) -> AuthResponse:
    """Authenticate an existing account and return a bearer session token."""
    repo = get_repository(settings)
    try:
        if isinstance(repo, LocalDevSQLiteRepository):
            profile = repo.authenticate_user(payload.identifier, payload.password)
            token = create_dev_access_token(profile, settings)
            return AuthResponse(
                access_token=token,
                auth_mode="dev_only",
                user=_to_profile_response(profile),
                message="Signed in (Local Development Mode).",
            )

        auth_result = repo.authenticate_supabase(payload.identifier, payload.password)
        return AuthResponse(
            access_token=auth_result["access_token"],
            auth_mode="supabase",
            user=_to_profile_response(auth_result["profile"]),
            message="Signed in successfully.",
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/me", response_model=ProfileResponse)
def get_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> ProfileResponse:
    """Return the authenticated user's profile."""
    return _to_profile_response(current_user)


@router.post("/otp/send")
def send_phone_otp(
    payload: PhoneOtpSendRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Send a phone OTP through Supabase Auth when an SMS provider is configured."""
    if not settings.is_supabase_configured or not settings.supabase_phone_otp_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Live SMS OTP is not configured. Configure a Supabase SMS provider "
                "(SUPABASE_PHONE_OTP_ENABLED=true) or use the clearly labelled "
                "Local Development verification option."
            ),
        )

    repo = get_repository(settings)
    if not isinstance(repo, SupabaseRepository):
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Supabase required for SMS OTP.")

    normalized = normalize_phone(payload.phone_number)
    if normalized != current_user["phone_number"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Phone number does not match account.")

    try:
        repo.anon_client.auth.sign_in_with_otp({"phone": normalized})
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OTP delivery failed: {exc}") from exc

    return {"status": "sent", "message": "OTP requested via configured SMS provider."}


@router.post("/otp/verify")
def verify_phone_otp(
    payload: PhoneOtpVerifyRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Verify phone OTP via Supabase Auth (never stores or logs plaintext OTPs)."""
    if not settings.is_supabase_configured or not settings.supabase_phone_otp_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Live SMS OTP verification is not configured.",
        )

    repo = get_repository(settings)
    if not isinstance(repo, SupabaseRepository):
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Supabase required for SMS OTP.")

    normalized = normalize_phone(payload.phone_number)
    if normalized != current_user["phone_number"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Phone number does not match account.")

    try:
        repo.anon_client.auth.verify_otp({"phone": normalized, "token": payload.otp_code, "type": "sms"})
        repo.client.table("profiles").update({"phone_verified": True}).eq("id", current_user["id"]).execute()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP.") from exc

    return {"phone_verified": True, "message": "Phone number verified."}


@router.post("/dev-verify-phone", response_model=ProfileResponse)
def dev_only_verify_phone(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ProfileResponse:
    """
    DEVELOPMENT-ONLY phone verification helper.
    Active strictly when SUPABASE_URL is unset and DEV_AUTH_MODE=true.
    """
    if settings.is_supabase_configured or not settings.dev_auth_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development-only verification is disabled when Supabase or production mode is active.",
        )

    repo = get_repository(settings)
    assert isinstance(repo, LocalDevSQLiteRepository)
    updated = repo.mark_phone_verified(str(current_user["id"]))
    assert updated is not None
    return _to_profile_response(updated)


@router.post("/aadhaar/verify", response_model=ProfileResponse)
def verify_aadhaar_for_user(
    payload: AadhaarVerifyInitRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ProfileResponse:
    """Verify and bind Aadhaar before donating or receiving blood (when enabled)."""
    if settings.aadhaar_kyc_enabled:
        if not settings.aadhaar_kyc_api_url or not settings.aadhaar_kyc_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Aadhaar e-KYC provider credentials are incomplete.",
            )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Configure external e-KYC API adapter for live UIDAI OTP.",
        )

    aadhaar_hash = compute_aadhaar_hash(payload.aadhaar_number, settings)
    aadhaar_last4 = payload.aadhaar_number[-4:]
    repo = get_repository(settings)
    try:
        updated = repo.save_user_aadhaar_verification(
            profile_id=str(current_user["id"]),
            aadhaar_last4=aadhaar_last4,
            aadhaar_hash=aadhaar_hash,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    assert updated is not None
    return _to_profile_response(updated)


@router.post("/dev-verify-aadhaar", response_model=ProfileResponse)
def dev_only_verify_aadhaar(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ProfileResponse:
    """DEVELOPMENT-ONLY Aadhaar verification helper when no live e-KYC provider is active."""
    if settings.is_supabase_configured or not settings.dev_auth_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development-only Aadhaar verification is disabled in production mode.",
        )
    repo = get_repository(settings)
    assert isinstance(repo, LocalDevSQLiteRepository)
    updated = repo.mark_aadhaar_verified(str(current_user["id"]))
    assert updated is not None
    return _to_profile_response(updated)


@router.post("/logout")
def logout(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, str]:
    """Acknowledge logout so client discards session credentials."""
    return {"message": f"Signed out {current_user['full_name']}."}
