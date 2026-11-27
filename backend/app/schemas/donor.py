from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

BloodGroup = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
AvailabilityStatus = Literal[
    "available_now",
    "available_today",
    "available_selected_dates",
    "unavailable",
    "emergency_only",
]
ContactMethod = Literal["in_app_chat", "consent_phone"]


class DonorProfileUpsertRequest(BaseModel):
    blood_group: BloodGroup
    availability_status: AvailabilityStatus = "unavailable"
    last_donation_date: Optional[date] = None
    preferred_contact_method: ContactMethod = "in_app_chat"
    emergency_notifications_enabled: bool = True


class DonorAvailabilityUpdateRequest(BaseModel):
    availability_status: AvailabilityStatus
    emergency_notifications_enabled: Optional[bool] = None


class DonorHistoryUpdateRequest(BaseModel):
    last_donation_date: Optional[date] = None


class DonorDocumentSubmitRequest(BaseModel):
    document_type: str = Field(..., min_length=2, max_length=80)
    storage_path: str = Field(..., min_length=3, max_length=255)


class FaceEnrollRequest(BaseModel):
    image_base64: str = Field(..., min_length=50)
    consent_given: bool


class FaceVerifyRequest(BaseModel):
    image_base64: str = Field(..., min_length=50)
    request_id: Optional[str] = None


class DonorProfileResponse(BaseModel):
    id: str
    user_id: str
    blood_group: BloodGroup
    availability_status: AvailabilityStatus
    last_donation_date: Optional[str] = None
    donor_frozen_until: Optional[str] = None
    is_frozen: bool = False
    donor_freeze_reason: Optional[str] = None
    preferred_contact_method: ContactMethod
    verification_status: str
    emergency_notifications_enabled: bool
    profile_completed: bool
    eligibility_review_note: str
    eligibility_disclaimer: str = (
        "Final donor eligibility, screening, and crossmatching are determined exclusively "
        "by licensed blood banks and qualified healthcare professionals."
    )
    created_at: str
    updated_at: str
