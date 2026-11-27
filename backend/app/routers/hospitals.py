from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user, require_roles
from backend.app.routers.requests import CLOSED_STATUSES
from backend.app.schemas.phase1 import (
    HospitalProfileOut,
    HospitalRegisterRequest,
    HospitalRequestClose,
    HospitalRequestConfirmUpdate,
    HospitalVerificationHistoryOut,
)

router = APIRouter(prefix="/api/hospitals", tags=["Hospital Verification & Operations"])

ALLOWED_HOSPITAL_DOC_MIME = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _to_hospital_out(row: Dict[str, Any]) -> HospitalProfileOut:
    return HospitalProfileOut(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        hospital_name=row["hospital_name"],
        registration_number=row["registration_number"],
        address=row["address"],
        city=row["city"],
        state=row.get("state") or "",
        official_phone=row["official_phone"],
        official_email=row.get("official_email"),
        authorized_rep_name=row["authorized_rep_name"],
        authorized_rep_role=row["authorized_rep_role"],
        verification_status=row["verification_status"],
        admin_notes=row.get("admin_notes"),
        verified_at=str(row["verified_at"]) if row.get("verified_at") else None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _require_verified_hospital(repo: Any, current_user: Dict[str, Any]) -> Dict[str, Any]:
    hosp = repo.get_hospital_by_user_id(str(current_user["id"]))
    if not hosp:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Submit your hospital registration before accessing hospital operations.",
        )
    if hosp["verification_status"] != "verified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Verified hospital approval is required (current status: {hosp['verification_status']}).",
        )
    return hosp


@router.get("/verified", response_model=List[HospitalProfileOut])
def list_verified_hospitals(
    city: Optional[str] = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> List[HospitalProfileOut]:
    """List platform-verified hospitals (indicates document verification, not blood-stock guarantees)."""
    repo = get_repository(settings)
    rows = repo.list_verified_hospitals(city=city)
    return [_to_hospital_out(r) for r in rows]


@router.post("/me", response_model=HospitalProfileOut)
def register_or_update_hospital(
    payload: HospitalRegisterRequest,
    current_user: Dict[str, Any] = Depends(require_roles("hospital", "admin")),
    settings: Settings = Depends(get_settings),
) -> HospitalProfileOut:
    if (
        settings.require_aadhaar_for_actions
        and current_user.get("role") != "admin"
        and not current_user.get("aadhaar_verified")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aadhaar verification is required for hospital registering staff before submitting facility registration.",
        )
    repo = get_repository(settings)
    row = repo.upsert_hospital_profile(user_id=str(current_user["id"]), payload=payload.model_dump())
    return _to_hospital_out(row)


@router.get("/me")
def get_my_hospital_profile(
    current_user: Dict[str, Any] = Depends(require_roles("hospital", "admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    hosp = repo.get_hospital_by_user_id(str(current_user["id"]))
    if not hosp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital registration not submitted yet.")
    docs = repo.list_hospital_documents(str(hosp["id"]))
    history = repo.get_hospital_verification_history(str(hosp["id"]))
    return {
        "hospital": _to_hospital_out(hosp).model_dump(),
        "documents": docs,
        "verification_history": [HospitalVerificationHistoryOut(**h).model_dump() for h in history],
    }


@router.post("/me/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_hospital_document(
    document_type: str = Form(..., min_length=2, max_length=80),
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(require_roles("hospital", "admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    if (
        settings.require_aadhaar_for_actions
        and current_user.get("role") != "admin"
        and not current_user.get("aadhaar_verified")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aadhaar verification is required for hospital registering staff before uploading licensing documents.",
        )
    repo = get_repository(settings)
    hosp = repo.get_hospital_by_user_id(str(current_user["id"]))
    if not hosp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Save hospital registration profile before uploading licensing documents.",
        )

    ext = Path(file.filename or "").suffix.lower()
    mime = (file.content_type or "").lower()
    expected_ext = ALLOWED_HOSPITAL_DOC_MIME.get(mime)
    if not expected_ext or ext not in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF, PNG, JPG, or WEBP hospital licensing documents are allowed.",
        )
    content = await file.read()
    if not content or len(content) > settings.max_document_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document must be between 1 byte and {settings.max_document_size_bytes // (1024 * 1024)} MB.",
        )
    safe_name = f"{uuid.uuid4().hex}{ext}"
    storage_path = repo.store_hospital_document_bytes(
        hospital_id=str(hosp["id"]),
        safe_filename=safe_name,
        content_bytes=content,
        settings=settings,
    )
    return repo.submit_hospital_document(
        hospital_id=str(hosp["id"]),
        document_type=document_type,
        storage_path=storage_path,
    )


@router.get("/requests")
def list_hospital_city_requests(
    current_user: Dict[str, Any] = Depends(require_roles("hospital")),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    repo = get_repository(settings)
    hosp = _require_verified_hospital(repo, current_user)
    repo.expire_stale_requests()
    rows = repo.hospital_list_requests(hosp)
    return [r for r in rows if repo.hospital_can_manage_request(hosp, r)]


@router.post("/requests/{request_id}/confirm")
def hospital_confirm_request(
    request_id: str,
    payload: HospitalRequestConfirmUpdate,
    current_user: Dict[str, Any] = Depends(require_roles("hospital")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    hosp = _require_verified_hospital(repo, current_user)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if not repo.hospital_can_manage_request(hosp, req):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hospital accounts can only manage requests matching their facility or assigned hospital ID.",
        )
    if req["status"] in CLOSED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot confirm or update a request that is already {req['status']}.",
        )
    return repo.hospital_confirm_or_update_request(
        hospital_row=hosp,
        req=req,
        actor_id=str(current_user["id"]),
        decision=payload.verification_decision,
        still_required=payload.still_required,
        units_requested=payload.units_requested,
        additional_information=payload.additional_information,
        notes=payload.notes,
    )


@router.post("/requests/{request_id}/close")
def hospital_close_request(
    request_id: str,
    payload: HospitalRequestClose,
    current_user: Dict[str, Any] = Depends(require_roles("hospital")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    hosp = _require_verified_hospital(repo, current_user)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    if not repo.hospital_can_manage_request(hosp, req):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hospital accounts can only close requests linked to their facility.",
        )
    if req["status"] in ("fulfilled", "cancelled", "expired"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request is already {req['status']}.",
        )
    return repo.hospital_close_request(
        hospital_row=hosp,
        req=req,
        actor_id=str(current_user["id"]),
        target_status=payload.status,
        reason=payload.reason,
    )
