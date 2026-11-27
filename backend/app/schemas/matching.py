from typing import List, Literal, Optional

from pydantic import BaseModel


class DonorMatchOut(BaseModel):
    id: str
    request_id: str
    donor_id: str
    donor_display_name: str
    blood_group: str
    city: str
    approximate_location: str
    availability_status: str
    verification_status: str
    priority_score: float
    match_reason: str
    match_status: str
    escalation_stage: int
    created_at: str


class MatchingRunResponse(BaseModel):
    request_id: str
    request_status: str
    escalation_stage: int
    newly_notified_count: int
    total_candidates_count: int
    candidates: List[DonorMatchOut]
    message: str


class DonorResponseCreate(BaseModel):
    response: Literal["accepted", "declined"]
    face_image_base64: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class DonorResponseOut(BaseModel):
    id: str
    request_id: str
    donor_id: str
    donor_display_name: str
    blood_group: str
    response: Literal["accepted", "declined"]
    responded_at: str
    conversation_id: Optional[str] = None


class IncomingRequestItem(BaseModel):
    match_id: str
    request_id: str
    blood_group: str
    units_requested: int
    hospital_name: str
    hospital_location: str
    city: str
    approximate_location: str
    urgency: str
    request_status: str
    match_status: str
    priority_score: float
    match_reason: str
    expires_at: str
    my_response: Optional[str] = None
    conversation_id: Optional[str] = None


class NotificationOut(BaseModel):
    id: str
    user_id: str
    notification_type: str
    title: str
    message: str
    related_request_id: Optional[str] = None
    delivery_status: str
    read_at: Optional[str] = None
    created_at: str
