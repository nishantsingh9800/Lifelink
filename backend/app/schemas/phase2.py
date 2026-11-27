from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class UserPreferencesUpdate(BaseModel):
    preferred_language: Optional[Literal["en", "hi", "mr", "bn", "ta"]] = None
    text_size: Optional[Literal["normal", "large", "xlarge"]] = None
    high_contrast: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    emergency_override_quiet_hours: Optional[bool] = None
    reminder_frequency_days: Optional[int] = Field(default=None, ge=7, le=180)


class DonorAvailabilityCalendarUpdate(BaseModel):
    availability_status: Optional[
        Literal["available_now", "available_today", "available_selected_dates", "unavailable", "emergency_only"]
    ] = None
    available_dates: Optional[List[str]] = None
    preferred_distance_km: Optional[int] = Field(default=None, ge=1, le=250)
    quiet_hours_start: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    paused_until: Optional[str] = None
    emergency_notifications_enabled: Optional[bool] = None


class FamilyContactInviteRequest(BaseModel):
    member_identifier: str = Field(..., min_length=3, max_length=254)
    relationship: str = Field(..., min_length=2, max_length=60)
    can_create_requests: bool = True
    can_manage_requests: bool = True


class FamilyContactRespondRequest(BaseModel):
    accept: bool


class SharedRequestReportCreate(BaseModel):
    reason: str = Field(..., min_length=3, max_length=160)
    description: Optional[str] = Field(default=None, max_length=600)
