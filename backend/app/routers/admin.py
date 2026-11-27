import mimetypes
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import require_roles
from backend.app.schemas.phase1 import HospitalReviewUpdate
from backend.app.schemas.user import AdminOverviewStats

router = APIRouter(prefix="/api/admin", tags=["Admin"])


class UserAccountStatusUpdate(BaseModel):
    account_status: Literal["active", "suspended"]
    reason: Optional[str] = Field(default=None, max_length=300)


class DocumentReviewUpdate(BaseModel):
    review_status: Literal["verified", "rejected"]
    notes: Optional[str] = Field(default=None, max_length=300)


class RequestModerationUpdate(BaseModel):
    status: Literal["cancelled", "unresolved", "fulfilled"]
    notes: str = Field(..., min_length=3, max_length=400)


class ReportReviewUpdate(BaseModel):
    status: Literal["under_review", "resolved", "dismissed"]


class BloodBankCreateUpdate(BaseModel):
    facility_name: str = Field(..., min_length=2, max_length=160)
    address: str = Field(..., min_length=2, max_length=240)
    city: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=6, max_length=40)
    website: Optional[str] = Field(default=None, max_length=240)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    verification_status: Literal["licensed_verified", "directory_listing", "outdated", "unverified"] = "licensed_verified"
    availability_status: Literal[
        "directory_listing_only",
        "availability_not_available",
        "contact_required",
        "availability_confirmed_by_facility",
        "availability_unavailable",
        "information_outdated",
    ] = "contact_required"
    source: str = Field(..., min_length=2, max_length=160)


@router.get("/overview", response_model=AdminOverviewStats)
def get_admin_overview(
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> AdminOverviewStats:
    repo = get_repository(settings)
    return AdminOverviewStats(**repo.get_admin_overview())


@router.get("/storage-config")
def get_admin_storage_config(
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Return configured verification storage & Google Drive folder details to administrators."""
    return {
        "storage_mode": settings.storage_mode,
        "google_drive_folder_url": settings.google_drive_folder_url.strip().rstrip("\\/"),
        "google_drive_folder_id": settings.resolved_google_drive_folder_id,
        "google_drive_auto_upload_enabled": settings.is_google_drive_upload_enabled,
    }


@router.get("/users")
def list_users(
    role: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    repo = get_repository(settings)
    return repo.list_users_for_admin(role=role, search=search)


@router.patch("/users/{user_id}/status")
def update_user_account_status(
    user_id: str,
    payload: UserAccountStatusUpdate,
    admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    if user_id == str(admin["id"]) and payload.account_status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot suspend their own account.",
        )
    repo = get_repository(settings)
    updated = repo.admin_update_user_status(
        user_id=user_id,
        account_status=payload.account_status,
        admin_id=str(admin["id"]),
        reason=payload.reason,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return updated


@router.get("/donor-documents")
def list_donor_documents(
    review_status: Optional[str] = Query(default=None),
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    repo = get_repository(settings)
    return repo.admin_list_donor_documents(review_status=review_status)


@router.patch("/donor-documents/{doc_id}")
def review_donor_document(
    doc_id: str,
    payload: DocumentReviewUpdate,
    admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    updated = repo.admin_review_donor_document(
        doc_id=doc_id,
        review_status=payload.review_status,
        admin_id=str(admin["id"]),
        notes=payload.notes,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return updated


@router.get("/donor-documents/{doc_id}/file")
def download_donor_document_file(
    doc_id: str,
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Serve an uploaded donor verification file strictly to administrators."""
    repo = get_repository(settings)
    doc = repo.get_donor_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    data = repo.read_donor_document_bytes(doc["storage_path"], settings)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored document file not found.")
    media_type, _ = mimetypes.guess_type(doc["storage_path"])
    return Response(
        content=data,
        media_type=media_type or "application/octet-stream",
        headers={"Content-Disposition": "inline"},
    )


@router.get("/requests")
def list_requests_for_admin(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    blood_group: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    repo = get_repository(settings)
    repo.expire_stale_requests()
    return repo.admin_list_requests(status_filter=status_filter, blood_group=blood_group, city=city)


@router.patch("/requests/{request_id}/moderate")
def moderate_request(
    request_id: str,
    payload: RequestModerationUpdate,
    admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    return repo.admin_moderate_request(
        request_row=req,
        new_status=payload.status,
        notes=payload.notes,
        admin_id=str(admin["id"]),
    )


@router.get("/reports")
def list_reports(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    repo = get_repository(settings)
    return repo.admin_list_reports(status_filter=status_filter)


@router.patch("/reports/{report_id}")
def review_report(
    report_id: str,
    payload: ReportReviewUpdate,
    admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    updated = repo.admin_update_report(
        report_id=report_id, status_value=payload.status, admin_id=str(admin["id"])
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return updated


@router.post("/blood-banks", status_code=status.HTTP_201_CREATED)
def create_blood_bank(
    payload: BloodBankCreateUpdate,
    admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    return repo.admin_create_blood_bank(payload.model_dump(), admin_id=str(admin["id"]))


@router.patch("/blood-banks/{bank_id}")
def update_blood_bank(
    bank_id: str,
    payload: BloodBankCreateUpdate,
    admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    updated = repo.admin_update_blood_bank(bank_id, payload.model_dump(), admin_id=str(admin["id"]))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood bank not found.")
    return updated


@router.delete("/blood-banks/{bank_id}")
def delete_blood_bank(
    bank_id: str,
    admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, str]:
    repo = get_repository(settings)
    deleted = repo.admin_delete_blood_bank(bank_id, admin_id=str(admin["id"]))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood bank not found.")
    return {"status": "deleted"}


@router.get("/analytics")
def get_admin_analytics(
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    return repo.admin_get_analytics()


@router.get("/audit-logs")
def get_audit_logs(
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    repo = get_repository(settings)
    return repo.admin_list_audit_logs()


@router.get("/hospitals")
def list_hospitals_for_admin(
    verification_status: Optional[str] = Query(default=None),
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    repo = get_repository(settings)
    return repo.admin_list_hospitals(status_filter=verification_status)


@router.get("/hospitals/{hospital_id}/history")
def get_hospital_audit_history(
    hospital_id: str,
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    repo = get_repository(settings)
    hosp = repo.get_hospital_by_id(hospital_id)
    if not hosp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found.")
    return repo.get_hospital_verification_history(hospital_id)


@router.patch("/hospitals/{hospital_id}/review")
def review_hospital_registration(
    hospital_id: str,
    payload: HospitalReviewUpdate,
    admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    updated = repo.admin_review_hospital(
        hospital_id=hospital_id,
        verification_status=payload.verification_status,
        admin_id=str(admin["id"]),
        notes=payload.notes,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital registration not found.")
    return updated


@router.get("/hospitals/documents/{doc_id}/file")
def download_hospital_document_file(
    doc_id: str,
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    settings: Settings = Depends(get_settings),
) -> Response:
    repo = get_repository(settings)
    doc = repo.get_hospital_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital document not found.")
    data = repo.read_donor_document_bytes(doc["storage_path"], settings)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored document file not found.")
    media_type, _ = mimetypes.guess_type(doc["storage_path"])
    return Response(
        content=data,
        media_type=media_type or "application/octet-stream",
        headers={"Content-Disposition": "inline"},
    )
