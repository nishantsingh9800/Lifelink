from datetime import date, datetime
from pathlib import Path
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.schemas.donor import (
    DonorAvailabilityUpdateRequest,
    DonorDocumentSubmitRequest,
    DonorHistoryUpdateRequest,
    DonorProfileResponse,
    DonorProfileUpsertRequest,
    FaceEnrollRequest,
    FaceVerifyRequest,
)
from backend.app.services.face_verification import (
    FaceDetectionError,
    compare_descriptors,
    decode_base64_image,
    extract_face_descriptor,
)
from backend.app.schemas.user import PublicDonorSearchItem

router = APIRouter(prefix="/api/donors", tags=["Donors"])


def compute_eligibility_review_note(last_donation_date: Optional[str], review_days: int) -> str:
    """Compute a transparent informational advisory without making a medical eligibility decision."""
    if not last_donation_date:
        return (
            "No previous donation date recorded. Final donation eligibility is determined "
            "by the licensed blood bank or healthcare professional."
        )
    try:
        parsed = date.fromisoformat(str(last_donation_date)[:10])
    except ValueError:
        return "Donation date format requires review by the blood bank."

    days_since = (datetime.now().date() - parsed).days
    if days_since < 0:
        return "Recorded donation date is in the future; please review."
    if days_since < review_days:
        return (
            f"Last recorded donation was {days_since} day(s) ago (configured review threshold: "
            f"{review_days} days). Further eligibility review by the blood bank is required."
        )
    return (
        f"Last recorded donation was {days_since} day(s) ago. Final medical fitness and "
        "eligibility remain determined solely by the blood bank."
    )


def _is_donor_frozen(row: Dict[str, Any]) -> bool:
    frozen_until = row.get("donor_frozen_until")
    if not frozen_until:
        return False
    try:
        return date.fromisoformat(str(frozen_until)[:10]) > datetime.now().date()
    except ValueError:
        return False


def _to_donor_response(row: Dict[str, Any], settings: Settings) -> DonorProfileResponse:
    frozen = _is_donor_frozen(row)
    note = compute_eligibility_review_note(
        row.get("last_donation_date"), settings.donor_review_interval_days
    )
    if frozen:
        note = f"Donor outreach frozen until {row['donor_frozen_until']} (3-month post-donation cooldown). {note}"
    return DonorProfileResponse(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        blood_group=row["blood_group"],
        availability_status=row["availability_status"],
        last_donation_date=row.get("last_donation_date"),
        donor_frozen_until=row.get("donor_frozen_until"),
        is_frozen=frozen,
        donor_freeze_reason=row.get("donor_freeze_reason"),
        preferred_contact_method=row.get("preferred_contact_method", "in_app_chat"),
        verification_status=row["verification_status"],
        emergency_notifications_enabled=bool(row.get("emergency_notifications_enabled", True)),
        profile_completed=bool(row.get("profile_completed", False)),
        eligibility_review_note=note,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


@router.get("/me", response_model=DonorProfileResponse)
def get_my_donor_profile(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DonorProfileResponse:
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor profile not created yet. Complete your donor profile to receive alerts.",
        )
    return _to_donor_response(donor, settings)


@router.put("/me", response_model=DonorProfileResponse)
def upsert_my_donor_profile(
    payload: DonorProfileUpsertRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DonorProfileResponse:
    repo = get_repository(settings)
    existing = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if existing and _is_donor_frozen(existing) and payload.availability_status != "unavailable":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Donor availability is frozen until {existing['donor_frozen_until']} "
                "(3-month cooldown after donation). You can still use requester features."
            ),
        )
    donor = repo.upsert_donor_profile(
        user_id=str(current_user["id"]),
        blood_group=payload.blood_group,
        availability_status=payload.availability_status,
        last_donation_date=payload.last_donation_date.isoformat() if payload.last_donation_date else None,
        preferred_contact_method=payload.preferred_contact_method,
        emergency_notifications_enabled=payload.emergency_notifications_enabled,
        cooldown_days=settings.donor_review_interval_days,
    )
    return _to_donor_response(donor, settings)


@router.patch("/me/availability", response_model=DonorProfileResponse)
def update_my_availability(
    payload: DonorAvailabilityUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DonorProfileResponse:
    repo = get_repository(settings)
    existing = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create your donor profile before updating availability.",
        )
    if _is_donor_frozen(existing) and payload.availability_status != "unavailable":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Donor availability is frozen until {existing['donor_frozen_until']} "
                "(3-month cooldown after donation)."
            ),
        )
    donor = repo.update_donor_availability(
        user_id=str(current_user["id"]),
        availability_status=payload.availability_status,
        emergency_notifications_enabled=payload.emergency_notifications_enabled,
    )
    return _to_donor_response(donor, settings)


@router.get("/me/calendar")
def get_my_donor_calendar(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    existing = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create your donor profile before managing your availability calendar.",
        )
    return repo.get_donor_calendar(str(existing["id"]), str(current_user["id"]))


@router.put("/me/calendar")
def update_my_donor_calendar(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    from backend.app.schemas.phase2 import DonorAvailabilityCalendarUpdate

    parsed = DonorAvailabilityCalendarUpdate(**payload)
    repo = get_repository(settings)
    existing = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create your donor profile before updating your availability calendar.",
        )
    if (
        _is_donor_frozen(existing)
        and parsed.availability_status is not None
        and parsed.availability_status != "unavailable"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Donor availability is frozen until {existing['donor_frozen_until']} "
                "(3-month cooldown after donation)."
            ),
        )
    return repo.upsert_donor_calendar(
        donor_id=str(existing["id"]),
        user_id=str(current_user["id"]),
        payload=parsed.model_dump(exclude_unset=True),
    )


@router.patch("/me/donation-history", response_model=DonorProfileResponse)
def update_my_donation_history(
    payload: DonorHistoryUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DonorProfileResponse:
    repo = get_repository(settings)
    existing = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create your donor profile before recording donation history.",
        )
    donor = repo.update_donor_history(
        user_id=str(current_user["id"]),
        last_donation_date=payload.last_donation_date.isoformat() if payload.last_donation_date else None,
        cooldown_days=settings.donor_review_interval_days,
    )
    return _to_donor_response(donor, settings)


@router.post("/me/record-donation", response_model=DonorProfileResponse)
def record_successful_donation(
    payload: DonorHistoryUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DonorProfileResponse:
    """Record a successful donation and freeze donor availability for 3 months (90 days)."""
    repo = get_repository(settings)
    existing = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create your donor profile before recording a donation.",
        )
    donation_date_str = (payload.last_donation_date or datetime.now().date()).isoformat()
    donor = repo.update_donor_history(
        user_id=str(current_user["id"]),
        last_donation_date=donation_date_str,
        cooldown_days=settings.donor_review_interval_days,
    )
    return _to_donor_response(donor, settings)


@router.get("/search", response_model=List[PublicDonorSearchItem])
def search_donors_authenticated(
    blood_group: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    _current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[PublicDonorSearchItem]:
    """Authenticated potential donor search (still strips phone numbers, emails, and addresses)."""
    repo = get_repository(settings)
    rows = repo.search_public_donors(blood_group=blood_group, city=city)
    return [PublicDonorSearchItem(**row) for row in rows]


@router.get("/me/documents")
def list_my_donor_documents(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        return []
    return repo.list_donor_documents(str(donor["id"]))


@router.post("/me/documents", status_code=status.HTTP_201_CREATED)
def submit_donor_document(
    payload: DonorDocumentSubmitRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Submit a supporting verification document reference for administrator review."""
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create your donor profile before submitting verification documents.",
        )
    return repo.submit_donor_document(
        donor_id=str(donor["id"]),
        document_type=payload.document_type,
        storage_path=payload.storage_path,
    )


ALLOWED_DOC_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


@router.post("/me/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_donor_document(
    document_type: str = Form(..., min_length=2, max_length=80),
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Upload a supporting verification document file (PDF/PNG/JPG/WEBP, max 5 MB) for admin review."""
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create your donor profile before uploading verification documents.",
        )

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Upload a PDF, PNG, JPG, JPEG, or WEBP file.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(content) > settings.max_document_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File exceeds the 5 MB maximum upload size.",
        )

    safe_filename = f"{uuid.uuid4().hex}{ext}"
    storage_path = repo.store_donor_document_bytes(
        donor_id=str(donor["id"]),
        safe_filename=safe_filename,
        content_bytes=content,
        content_type=file.content_type or "application/octet-stream",
        settings=settings,
    )
    return repo.submit_donor_document(
        donor_id=str(donor["id"]),
        document_type=document_type,
        storage_path=storage_path,
    )


@router.get("/me/face")
def get_my_face_status(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        return {"enrolled": False, "enrolled_at": None, "updated_at": None, "recent_verifications": []}
    return repo.get_face_profile_status(str(donor["id"]))


@router.post("/me/face/enroll")
def enroll_my_face(
    payload: FaceEnrollRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Enroll the registered donor's facial descriptor for anti-impersonation verification."""
    if not payload.consent_given:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Explicit biometric consent is required to enroll facial verification.",
        )
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create your donor profile before enrolling face verification.",
        )
    try:
        raw = decode_base64_image(payload.image_base64)
        descriptor, box = extract_face_descriptor(raw)
    except FaceDetectionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    status_info = repo.upsert_face_descriptor(str(donor["id"]), descriptor)
    return {
        **status_info,
        "face_box": box,
        "message": "Face profile enrolled. Live verification will protect your donation check-ins.",
    }


@router.post("/me/face/verify")
def verify_my_face(
    payload: FaceVerifyRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Compare a live selfie against the enrolled donor's facial descriptor."""
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor profile not found.")
    enrolled = repo.get_face_descriptor(str(donor["id"]))
    if not enrolled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Face profile not enrolled yet. Please enroll your face on the Donor Profile page first.",
        )

    try:
        raw = decode_base64_image(payload.image_base64)
        candidate, _ = extract_face_descriptor(raw)
    except FaceDetectionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    matched, score = compare_descriptors(enrolled, candidate, threshold=settings.face_match_threshold)
    reason = (
        "Live face matched enrolled donor profile."
        if matched
        else "Face mismatch: live photo did not match the enrolled donor."
    )
    log = repo.log_face_verification(
        donor_id=str(donor["id"]),
        request_id=payload.request_id,
        similarity_score=score,
        verified=matched,
        reason=reason,
    )
    return {
        "verified": matched,
        "similarity_score": score,
        "threshold": settings.face_match_threshold,
        "log": log,
        "message": reason,
        "disclaimer": "Platform face verification assists identity matching; physical ID check at the blood bank remains mandatory.",
    }


@router.get("/me/trust-profile")
def get_my_trust_profile(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor profile not found.")
    return repo.get_donor_trust_profile(donor_row=donor)


@router.get("/me/donations")
def list_my_donations(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    from backend.app.addons_phase3_db import DONATION_TYPE_ADVISORY_DAYS

    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor profile not found.")
    records = repo.list_donation_records(str(donor["id"]))
    return {
        "records": records,
        "configurable_guidance_days_by_type": DONATION_TYPE_ADVISORY_DAYS,
        "disclaimer": "Self-reported records are distinguished from verified records. Licensed blood banks determine final donation eligibility.",
    }


@router.post("/me/donations", status_code=status.HTTP_201_CREATED)
def add_my_donation_record(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    from backend.app.schemas.phase3 import DonationRecordCreate

    parsed = DonationRecordCreate(**payload)
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor profile not found.")
    return repo.create_donation_record(donor_id=str(donor["id"]), payload=parsed.model_dump())


@router.patch("/me/donations/{record_id}")
def correct_my_donation_record(
    record_id: str,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    from backend.app.schemas.phase3 import DonationRecordCorrect

    parsed = DonationRecordCorrect(**payload)
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor profile not found.")
    res = repo.correct_donation_record(
        donor_id=str(donor["id"]), record_id=record_id, payload=parsed.model_dump(exclude_unset=True)
    )
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donation record not found.")
    if res == "FORBIDDEN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this donation record.")
    return res


@router.post("/me/availability-reminder")
def send_my_availability_reminder(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor profile not found.")
    return repo.send_availability_reminder(user_id=str(current_user["id"]), donor_row=donor)


@router.get("/me/appreciation")
def get_my_appreciation(
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor profile not found.")
    return repo.get_donor_appreciation_summary(user_id=str(current_user["id"]), donor_row=donor)


@router.patch("/me/appreciation")
def update_my_appreciation_visibility(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    from backend.app.schemas.phase3 import RecognitionPreferenceUpdate

    parsed = RecognitionPreferenceUpdate(**payload)
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_user_id(str(current_user["id"]))
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor profile not found.")
    return repo.update_recognition_preference(
        user_id=str(current_user["id"]), recognition_public=parsed.recognition_public
    )


@router.get("/{donor_id}/trust-profile")
def get_authorized_donor_trust_profile(
    donor_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """View transparent donor trust profile strictly for authorized request participants or admin."""
    repo = get_repository(settings)
    donor = repo.get_donor_profile_by_id(donor_id)
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor profile not found.")
    if current_user.get("role") != "admin" and not repo.can_view_donor_trust_profile(
        viewer_user_id=str(current_user["id"]), donor_row=donor
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this donor's private trust details.",
        )
    return repo.get_donor_trust_profile(donor_row=donor)
