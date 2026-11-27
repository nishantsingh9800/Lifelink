from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

DonationType = Literal["whole_blood", "platelets", "plasma", "double_red_cells"]


class DonationRecordCreate(BaseModel):
    donation_date: date
    donation_type: DonationType = "whole_blood"
    facility_name: str = Field(default="Licensed Blood Centre", min_length=2, max_length=160)
    supporting_document_id: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=400)


class DonationRecordCorrect(BaseModel):
    donation_date: Optional[date] = None
    donation_type: Optional[DonationType] = None
    facility_name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    notes: Optional[str] = Field(default=None, max_length=400)
    correction_reason: str = Field(..., min_length=3, max_length=300)


class RecognitionPreferenceUpdate(BaseModel):
    recognition_public: bool
