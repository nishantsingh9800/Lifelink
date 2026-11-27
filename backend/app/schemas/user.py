from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    city: Optional[str] = Field(default=None, min_length=2, max_length=100)
    approximate_location: Optional[str] = Field(default=None, min_length=2, max_length=160)


class PublicDonorSearchItem(BaseModel):
    donor_id: str
    display_name: str
    blood_group: str
    city: str
    approximate_location: str
    availability_status: str
    verification_status: str
    match_label: str = "Potential match (medical eligibility determined by blood bank)"


class PublicBloodBankItem(BaseModel):
    id: str
    facility_name: str
    address: str
    city: str
    phone: str
    website: Optional[str] = None
    verification_status: str
    availability_status: str
    availability_label: str
    source: str
    last_verified_at: Optional[str] = None


class AdminOverviewStats(BaseModel):
    total_users: int
    total_donors: int
    verified_donors: int
    active_requests: int
    fulfilled_requests: int
    unresolved_requests: int
    pending_document_reviews: int
    open_reports: int
    blood_banks_count: int
    disclaimer: str = "Platform operational records only, not clinical outcomes."
