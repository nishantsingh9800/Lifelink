from typing import List, Literal, Optional

from pydantic import BaseModel, Field

HospitalVerificationStatus = Literal[
    "pending_verification",
    "under_review",
    "verified",
    "rejected",
    "suspended",
]

StockAvailabilityStatus = Literal[
    "confirmed_available",
    "reported_awaiting_confirmation",
    "availability_unknown",
    "currently_unavailable",
    "information_outdated",
]


class HospitalRegisterRequest(BaseModel):
    hospital_name: str = Field(..., min_length=2, max_length=160)
    registration_number: str = Field(..., min_length=3, max_length=80)
    address: str = Field(..., min_length=4, max_length=240)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(default="", max_length=100)
    official_phone: str = Field(..., min_length=6, max_length=40)
    official_email: Optional[str] = Field(default=None, max_length=254)
    authorized_rep_name: str = Field(..., min_length=2, max_length=120)
    authorized_rep_role: str = Field(..., min_length=2, max_length=100)


class HospitalReviewUpdate(BaseModel):
    verification_status: Literal["under_review", "verified", "rejected", "suspended"]
    notes: str = Field(..., min_length=3, max_length=400)


class HospitalRequestConfirmUpdate(BaseModel):
    verification_decision: Literal["confirmed_genuine", "hospital_updated", "flagged_invalid"] = "confirmed_genuine"
    still_required: bool = True
    units_requested: Optional[int] = Field(default=None, ge=1, le=20)
    additional_information: Optional[str] = Field(default=None, max_length=600)
    notes: Optional[str] = Field(default=None, max_length=400)


class HospitalRequestClose(BaseModel):
    status: Literal["fulfilled", "cancelled"]
    reason: str = Field(..., min_length=3, max_length=400)


class HospitalVerificationHistoryOut(BaseModel):
    id: str
    hospital_id: str
    previous_status: Optional[str] = None
    new_status: str
    actor_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: str


class HospitalProfileOut(BaseModel):
    id: str
    user_id: str
    hospital_name: str
    registration_number: str
    address: str
    city: str
    state: str = ""
    official_phone: str
    official_email: Optional[str] = None
    authorized_rep_name: str
    authorized_rep_role: str
    verification_status: str
    admin_notes: Optional[str] = None
    verified_at: Optional[str] = None
    created_at: str
    updated_at: str
    badge_disclaimer: str = (
        "Platform verification confirms submitted hospital documentation only; it does not "
        "guarantee blood stock availability or clinical decisions."
    )


class CoordinatorInviteRequest(BaseModel):
    coordinator_identifier: str = Field(..., min_length=3, max_length=254)
    can_chat: bool = True
    can_contact_blood_banks: bool = True
    can_update_progress: bool = True


class CoordinatorRespondRequest(BaseModel):
    accept: bool


class CoordinatorProgressUpdate(BaseModel):
    notes: str = Field(..., min_length=3, max_length=400)


class CoordinatorAssignmentOut(BaseModel):
    id: str
    request_id: str
    requester_id: str
    coordinator_user_id: str
    coordinator_display_name: str
    request_blood_group: Optional[str] = None
    request_hospital_name: Optional[str] = None
    request_status: Optional[str] = None
    status: str
    can_chat: bool
    can_contact_blood_banks: bool
    can_update_progress: bool
    invited_at: str
    responded_at: Optional[str] = None
    revoked_at: Optional[str] = None


class BloodBankStockUpdateCreate(BaseModel):
    blood_group: Literal["ALL", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"] = "ALL"
    availability_status: StockAvailabilityStatus
    notes: Optional[str] = Field(default=None, max_length=300)


class BloodBankStockUpdateOut(BaseModel):
    id: str
    blood_bank_id: str
    blood_group: str
    availability_status: str
    availability_label: str
    notes: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: str


class LiveTimelineStep(BaseModel):
    step: int
    key: str
    label: str
    state: Literal["completed", "current", "pending", "terminal"]
    timestamp: Optional[str] = None
    detail: str


class LiveRequestTrackingSummary(BaseModel):
    request_id: str
    status: str
    urgency: str
    blood_group: str
    units_requested: int
    hospital_name: str
    hospital_verification_status: str
    escalation_stage: int
    donors_notified: int
    responses_received: int
    donors_interested: int
    donors_declined: int
    last_status_update: str
    expires_at: str
    timeline: List[LiveTimelineStep]
    next_steps: List[str]
    disclaimer: str = (
        "LifeLink tracking shows coordination progress only and never exposes private donor phone numbers. "
        "Urgent requests are not clinically verified until confirmed by a verified hospital or licensed blood centre."
    )
