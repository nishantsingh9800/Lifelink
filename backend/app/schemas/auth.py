from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.utils.security import is_valid_aadhaar, normalize_aadhaar

BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
AVAILABILITY_STATUSES = ("available_now", "available_today", "unavailable", "emergency_only")


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=254)
    phone_number: str = Field(..., min_length=10, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)
    date_of_birth: Optional[date] = None
    city: str = Field(..., min_length=2, max_length=100)
    approximate_location: str = Field(..., min_length=2, max_length=160)
    role_preference: Literal["requester", "donor", "hospital"] = "requester"
    blood_group: Optional[Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]] = None
    aadhaar_number: Optional[str] = Field(default=None, max_length=20)
    aadhaar_consent: bool = False
    aadhaar_verification_token: Optional[str] = None
    referral_code: Optional[str] = Field(default=None, max_length=32)
    terms_accepted: bool = Field(...)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or "." not in cleaned.split("@")[-1]:
            raise ValueError("Please provide a valid email address.")
        return cleaned

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        digits = normalize_aadhaar(value)
        if not is_valid_aadhaar(digits):
            raise ValueError("Please enter a valid 12-digit Aadhaar number (Verhoeff checksum failed).")
        return digits

    @model_validator(mode="after")
    def validate_aadhaar_consent_if_provided(self) -> "RegisterRequest":
        if self.aadhaar_number and not self.aadhaar_consent:
            raise ValueError("Consent for Aadhaar identity verification is required when providing an Aadhaar number.")
        return self

    @field_validator("terms_accepted")
    @classmethod
    def must_accept_terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must accept the Terms and Privacy Policy to register.")
        return value


class AadhaarVerifyInitRequest(BaseModel):
    aadhaar_number: str = Field(..., min_length=12, max_length=20)
    aadhaar_consent: bool = Field(...)

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, value: str) -> str:
        digits = normalize_aadhaar(value)
        if not is_valid_aadhaar(digits):
            raise ValueError("Please enter a valid 12-digit Aadhaar number (Verhoeff checksum failed).")
        return digits

    @field_validator("aadhaar_consent")
    @classmethod
    def must_consent_aadhaar(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Consent for Aadhaar verification is required.")
        return value


class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=254, description="Email address or phone number")
    password: str = Field(..., min_length=1, max_length=128)


class PhoneOtpSendRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=20)


class PhoneOtpVerifyRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=20)
    otp_code: str = Field(..., min_length=4, max_length=10)


class ProfileResponse(BaseModel):
    id: str
    full_name: str
    email: Optional[str] = None
    phone_number: str
    role: Literal["requester", "donor", "hospital", "admin"]
    city: str
    approximate_location: str
    date_of_birth: Optional[str] = None
    account_status: str
    phone_verified: bool
    aadhaar_masked: str
    aadhaar_verified: bool
    preferred_language: str = "en"
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    auth_mode: str
    user: ProfileResponse
    message: str
