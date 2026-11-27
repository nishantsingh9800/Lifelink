from typing import Optional

from pydantic import BaseModel, Field


class ConversationOut(BaseModel):
    id: str
    request_id: str
    blood_group: str
    hospital_name: str
    city: str
    counterpart_user_id: str
    counterpart_display_name: str
    my_role: str
    status: str
    unread_count: int = 0
    created_at: str
    updated_at: str


class MessageCreate(BaseModel):
    message_text: str = Field(..., min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    sender_display_name: str
    is_mine: bool
    message_text: str
    created_at: str
    read_at: Optional[str] = None


class ContactSharingStatusOut(BaseModel):
    request_id: str
    requester_consent: bool
    donor_consent: bool
    requester_consent_at: Optional[str] = None
    donor_consent_at: Optional[str] = None
    status: str
    counterpart_phone_number: Optional[str] = None
    privacy_notice: str = (
        "Phone numbers are shared ONLY when both participants explicitly agree. "
        "Consent can be withdrawn for future access, though previously viewed numbers "
        "cannot be technically recalled."
    )


class ReportCreate(BaseModel):
    reported_user_id: Optional[str] = None
    request_id: Optional[str] = None
    reason: str = Field(..., min_length=3, max_length=160)
    description: Optional[str] = Field(default=None, max_length=1000)


class BlockUserRequest(BaseModel):
    blocked_user_id: str
    conversation_id: Optional[str] = None
    reason: Optional[str] = Field(default="Blocked by user", max_length=300)
