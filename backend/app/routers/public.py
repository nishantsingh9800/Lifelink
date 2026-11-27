from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.schemas.user import PublicBloodBankItem, PublicDonorSearchItem

router = APIRouter(prefix="/api/public", tags=["Public Discovery"])


@router.get("/donors", response_model=List[PublicDonorSearchItem])
def search_public_donors(
    blood_group: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> List[PublicDonorSearchItem]:
    """
    Privacy-safe donor discovery: returns approximate location and availability only.
    Phone numbers, emails, and exact addresses are NEVER exposed here.
    """
    repo = get_repository(settings)
    rows = repo.search_public_donors(blood_group=blood_group, city=city)
    return [PublicDonorSearchItem(**row) for row in rows]


@router.get("/blood-banks", response_model=List[PublicBloodBankItem])
def search_public_blood_banks(
    city: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> List[PublicBloodBankItem]:
    """Search verified/listed blood-bank directory entries."""
    repo = get_repository(settings)
    rows = repo.search_blood_banks(city=city, query_text=q)
    return [PublicBloodBankItem(**row) for row in rows]
