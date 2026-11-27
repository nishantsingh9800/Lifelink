from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

BloodGroup = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
UrgencyLevel = Literal["normal", "urgent", "emergency"]

REQUEST_STATUSES = (
    "created",
    "matching",
    "donors_notified",
    "responses_received",
    "connection_in_progress",
    "blood_bank_assistance",
    "escalation_in_progress",
    "fulfilled",
    "unresolved",
    "cancelled",
    "expired",
)


class BloodRequestCreate(BaseModel):
    patient_reference_name: str = Field(..., min_length=2, max_length=120)
    blood_group: BloodGroup
    units_requested: int = Field(default=1, ge=1, le=20)
    hospital_name: str = Field(..., min_length=2, max_length=160)
    hospital_location: str = Field(..., min_length=2, max_length=200)
    city: str = Field(..., min_length=2, max_length=100)
    approximate_location: str = Field(..., min_length=2, max_length=160)
    urgency: UrgencyLevel = "urgent"
    additional_information: Optional[str] = Field(default=None, max_length=600)
    requester_contact_preference: Literal["in_app_chat", "consent_phone"] = "in_app_chat"
    requested_for: Optional[datetime] = None
    expiry_hours: Optional[int] = Field(default=None, ge=1, le=168)
    is_emergency_quick: bool = False
    coordinator_contact_name: Optional[str] = Field(default=None, max_length=120)
    coordinator_contact_relation: Optional[str] = Field(default=None, max_length=80)
    hospital_id: Optional[str] = None
    on_behalf_of_user_id: Optional[str] = None
    consent_given: bool

    @field_validator("consent_given")
    @classmethod
    def must_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Consent to process and share request coordination details is required.")
        return value


class BloodRequestUpdate(BaseModel):
    units_requested: Optional[int] = Field(default=None, ge=1, le=20)
    hospital_name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    hospital_location: Optional[str] = Field(default=None, min_length=2, max_length=200)
    approximate_location: Optional[str] = Field(default=None, min_length=2, max_length=160)
    urgency: Optional[UrgencyLevel] = None
    additional_information: Optional[str] = Field(default=None, max_length=600)


class BloodRequestCancel(BaseModel):
    reason: Optional[str] = Field(default="Cancelled by requester", max_length=300)


class BloodRequestOutcome(BaseModel):
    outcome: Literal["fulfilled", "unresolved"]
    donated_by_donor_id: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=400)


class BloodRequestResponse(BaseModel):
    id: str
    requester_id: str
    created_by_user_id: Optional[str] = None
    patient_reference_name: str
    blood_group: BloodGroup
    units_requested: int
    hospital_name: str
    hospital_location: str
    city: str
    approximate_location: str
    urgency: UrgencyLevel
    additional_information: Optional[str] = None
    requester_contact_preference: str
    status: str
    escalation_stage: int
    is_emergency_quick: bool = False
    coordinator_contact_name: Optional[str] = None
    coordinator_contact_relation: Optional[str] = None
    hospital_id: Optional[str] = None
    hospital_verification_status: str = "unconfirmed"
    hospital_confirmed_at: Optional[str] = None
    cancellation_reason: Optional[str] = None
    requested_for: str
    expires_at: str
    created_at: str
    updated_at: str
    safety_notice: str = (
        "LifeLink does not guarantee blood availability. Urgent requests are not medically verified "
        "until confirmed by a verified hospital. Never delay emergency care while waiting for donor outreach."
    )


class RequestStatusHistoryItem(BaseModel):
    id: str
    request_id: str
    previous_status: Optional[str] = None
    new_status: str
    changed_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
