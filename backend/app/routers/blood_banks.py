import math
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.app.config import Settings, get_settings
from backend.app.database import get_repository
from backend.app.dependencies.auth import get_current_user
from backend.app.schemas.phase1 import BloodBankStockUpdateOut, BloodBankStockUpdateCreate
from backend.app.services.nearby_facilities import ERAKT_KOSH_PORTAL_URL, fetch_nearby_external_facilities

router = APIRouter(prefix="/api/blood-banks", tags=["Blood Banks & Fallback"])


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return round(2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


class ContactAttemptCreate(BaseModel):
    request_id: str
    outcome: Literal["contacted", "confirmed_available", "unavailable", "no_response"]
    notes: Optional[str] = Field(default=None, max_length=400)


class BloodBankDetailOut(BaseModel):
    id: str
    facility_name: str
    address: str
    city: str
    phone: str
    website: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    directions_url: str
    verification_status: str
    availability_status: str
    availability_label: str
    source: str
    last_verified_at: Optional[str] = None


def _enrich_bank(row: Dict[str, Any], lat: Optional[float], lon: Optional[float]) -> BloodBankDetailOut:
    b_lat = row.get("latitude")
    b_lon = row.get("longitude")
    dist = None
    if lat is not None and lon is not None and b_lat is not None and b_lon is not None:
        dist = _haversine_km(lat, lon, float(b_lat), float(b_lon))
    query = quote_plus(f"{row['facility_name']}, {row['address']}, {row['city']}")
    return BloodBankDetailOut(
        id=str(row["id"]),
        facility_name=row["facility_name"],
        address=row["address"],
        city=row["city"],
        phone=row["phone"],
        website=row.get("website"),
        latitude=float(b_lat) if b_lat is not None else None,
        longitude=float(b_lon) if b_lon is not None else None,
        distance_km=dist,
        directions_url=f"https://www.google.com/maps/search/?api=1&query={query}",
        verification_status=row["verification_status"],
        availability_status=row["availability_status"],
        availability_label=row["availability_label"],
        source=row["source"],
        last_verified_at=str(row["last_verified_at"]) if row.get("last_verified_at") else None,
    )


@router.get("", response_model=List[BloodBankDetailOut])
def search_blood_banks(
    city: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> List[BloodBankDetailOut]:
    repo = get_repository(settings)
    rows = repo.search_blood_banks(city=city, query_text=q)
    enriched = [_enrich_bank(r, lat, lon) for r in rows]
    if lat is not None and lon is not None:
        enriched.sort(key=lambda b: (b.distance_km is None, b.distance_km or 0.0))
    return enriched


@router.get("/attempts/{request_id}")
def list_contact_attempts(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    repo = get_repository(settings)
    req = repo.get_blood_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    uid = str(current_user["id"])
    if (
        current_user.get("role") != "admin"
        and str(req["requester_id"]) != uid
        and not repo.is_active_coordinator_for_request(uid, request_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    return repo.list_blood_bank_contact_attempts(request_id)


class NearbyFacilityOut(BaseModel):
    id: str
    is_platform_entry: bool = False
    facility_name: str
    facility_type: str
    address: str
    city: str
    phone: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    opening_hours: Optional[str] = None
    operator_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    directions_url: str
    google_search_url: str
    eraktkosh_url: str
    verification_status: str
    availability_status: str
    availability_label: str
    stock_notice: str
    stock_updates: List[Dict[str, Any]] = []
    source: str
    last_verified_at: Optional[str] = None


class NearbyLiveDirectoryResponse(BaseModel):
    facilities: List[NearbyFacilityOut]
    center_city: Optional[str] = None
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None
    sources_used: List[str]
    live_stock_api_configured: bool
    live_stock_note: str
    maps_nearby_search_url: str
    provider_notice: Optional[str] = None


@router.get("/nearby-live", response_model=NearbyLiveDirectoryResponse)
def search_nearby_live_facilities(
    city: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
    facility_type: Literal["all", "blood_bank", "hospital"] = Query(default="all"),
    radius_km: float = Query(default=35.0, ge=5.0, le=100.0),
    include_external: bool = Query(default=True),
    settings: Settings = Depends(get_settings),
) -> NearbyLiveDirectoryResponse:
    """Search LifeLink verified blood banks/hospitals plus real nearby OpenStreetMap/Google facilities."""
    repo = get_repository(settings)
    facilities: List[NearbyFacilityOut] = []
    seen_names: set[str] = set()
    sources_used: List[str] = []

    # 1. Platform DB blood banks (with any facility-reported stock updates)
    db_banks = repo.search_blood_banks(city=city, query_text=q)
    for row in db_banks:
        b = _enrich_bank(row, lat, lon)
        stock_rows = repo.list_blood_bank_stock_updates(b.id)
        name_q = quote_plus(f"{b.facility_name} {b.city} blood bank contact".strip())
        seen_names.add(b.facility_name.lower().strip())
        facilities.append(
            NearbyFacilityOut(
                id=b.id,
                is_platform_entry=True,
                facility_name=b.facility_name,
                facility_type="blood_bank",
                address=b.address,
                city=b.city,
                phone=b.phone,
                website=b.website,
                latitude=b.latitude,
                longitude=b.longitude,
                distance_km=b.distance_km,
                directions_url=b.directions_url,
                google_search_url=f"https://www.google.com/search?q={name_q}",
                eraktkosh_url=ERAKT_KOSH_PORTAL_URL,
                verification_status=b.verification_status,
                availability_status=b.availability_status,
                availability_label=b.availability_label,
                stock_notice="Platform entry — verify urgent blood units directly with facility or e-RaktKosh.",
                stock_updates=stock_rows[:5],
                source=b.source,
                last_verified_at=b.last_verified_at,
            )
        )
    if db_banks:
        sources_used.append("LifeLink Verified Directory")

    # 2. Platform-verified partner hospitals
    verified_hospitals = repo.list_verified_hospitals(city=city)
    for hosp in verified_hospitals:
        h_name = str(hosp["hospital_name"]).strip()
        if q and q.strip().lower() not in f"{h_name} {hosp['address']} {hosp['city']}".lower():
            continue
        if h_name.lower() in seen_names:
            continue
        seen_names.add(h_name.lower())
        maps_q = quote_plus(f"{h_name}, {hosp['address']}, {hosp['city']}")
        google_q = quote_plus(f"{h_name} {hosp['city']} blood bank phone".strip())
        facilities.append(
            NearbyFacilityOut(
                id=f"hosp-{hosp['id']}",
                is_platform_entry=False,
                facility_name=h_name,
                facility_type="hospital",
                address=hosp["address"],
                city=hosp["city"],
                phone=hosp.get("official_phone"),
                email=hosp.get("official_email"),
                directions_url=f"https://www.google.com/maps/search/?api=1&query={maps_q}",
                google_search_url=f"https://www.google.com/search?q={google_q}",
                eraktkosh_url=ERAKT_KOSH_PORTAL_URL,
                verification_status="platform_verified_hospital",
                availability_status="contact_required",
                availability_label="Call hospital blood counter for live units",
                stock_notice="Verified partner hospital registration; live unit inventory is confirmed by calling directly.",
                source="LifeLink Verified Hospital",
                last_verified_at=str(hosp["verified_at"]) if hosp.get("verified_at") else None,
            )
        )
    if verified_hospitals and "LifeLink Verified Hospital" not in sources_used:
        sources_used.append("LifeLink Verified Hospital")

    # 3. Live external facilities (Google Places if key configured, else OpenStreetMap Nominatim)
    ext = {"items": [], "center_lat": lat, "center_lon": lon, "sources": [], "provider_notice": None}
    if include_external:
        ext = fetch_nearby_external_facilities(
            city=city,
            query_text=q,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            google_api_key=settings.geocoding_api_key,
        )
        for item in ext["items"]:
            key = item["facility_name"].lower().strip()
            if key in seen_names:
                continue
            seen_names.add(key)
            facilities.append(NearbyFacilityOut(**item))
        for src in ext["sources"]:
            if src not in sources_used:
                sources_used.append(src)

    if facility_type != "all":
        facilities = [f for f in facilities if f.facility_type == facility_type]

    location_label = (city or "").strip() or (
        f"{lat:.4f},{lon:.4f}" if lat is not None and lon is not None else "nearby"
    )
    maps_nearby_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(f'blood bank and hospital near {location_label}')}"
    erakt_configured = bool(settings.eraktkosh_api_url.strip() and settings.eraktkosh_api_key.strip())

    return NearbyLiveDirectoryResponse(
        facilities=facilities,
        center_city=(city or "").strip() or None,
        center_lat=ext.get("center_lat"),
        center_lon=ext.get("center_lon"),
        sources_used=sources_used,
        live_stock_api_configured=erakt_configured,
        live_stock_note=(
            "Live e-RaktKosh unit stock API is configured."
            if erakt_configured
            else "Real-time unit counts per blood group require official e-RaktKosh API credentials at deployment; use the phone numbers below or e-RaktKosh portal to confirm live blood availability."
        ),
        maps_nearby_search_url=maps_nearby_url,
        provider_notice=ext.get("provider_notice"),
    )


@router.get("/{blood_bank_id}", response_model=BloodBankDetailOut)
def get_blood_bank(
    blood_bank_id: str,
    settings: Settings = Depends(get_settings),
) -> BloodBankDetailOut:
    repo = get_repository(settings)
    row = repo.get_blood_bank_by_id(blood_bank_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood bank not found.")
    return _enrich_bank(row, None, None)


@router.post("/{blood_bank_id}/contact-attempt", status_code=status.HTTP_201_CREATED)
def record_contact_attempt(
    blood_bank_id: str,
    payload: ContactAttemptCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    repo = get_repository(settings)
    bank = repo.get_blood_bank_by_id(blood_bank_id)
    if not bank:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood bank not found.")
    req = repo.get_blood_request(payload.request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    uid = str(current_user["id"])
    if (
        current_user.get("role") != "admin"
        and str(req["requester_id"]) != uid
        and not repo.is_active_coordinator_for_request(uid, payload.request_id, "can_contact_blood_banks")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requester, authorized coordinator, or admin can log contact attempts.",
        )

    return repo.record_blood_bank_contact_attempt(
        request_id=payload.request_id,
        blood_bank_id=blood_bank_id,
        recorded_by=uid,
        outcome=payload.outcome,
        notes=payload.notes,
    )


@router.get("/{blood_bank_id}/stock-updates", response_model=List[BloodBankStockUpdateOut])
def get_blood_bank_stock_updates(
    blood_bank_id: str,
    settings: Settings = Depends(get_settings),
) -> List[BloodBankStockUpdateOut]:
    repo = get_repository(settings)
    bank = repo.get_blood_bank_by_id(blood_bank_id)
    if not bank:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood bank not found.")
    rows = repo.list_blood_bank_stock_updates(blood_bank_id)
    return [BloodBankStockUpdateOut(**r) for r in rows]


@router.post("/{blood_bank_id}/stock-updates", response_model=BloodBankStockUpdateOut, status_code=status.HTTP_201_CREATED)
def post_blood_bank_stock_update(
    blood_bank_id: str,
    payload: BloodBankStockUpdateCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> BloodBankStockUpdateOut:
    """Update blood-bank availability status (admin or verified hospital only)."""
    repo = get_repository(settings)
    bank = repo.get_blood_bank_by_id(blood_bank_id)
    if not bank:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood bank not found.")
    is_admin = current_user.get("role") == "admin"
    is_verified_hosp = False
    if current_user.get("role") == "hospital":
        hosp = repo.get_hospital_by_user_id(str(current_user["id"]))
        is_verified_hosp = bool(hosp and hosp.get("verification_status") == "verified")
    if not is_admin and not is_verified_hosp:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators or verified hospitals can post blood-bank stock updates.",
        )
    row = repo.record_blood_bank_stock_update(
        blood_bank_id=blood_bank_id,
        blood_group=payload.blood_group,
        availability_status=payload.availability_status,
        notes=payload.notes,
        actor_id=str(current_user["id"]),
    )
    return BloodBankStockUpdateOut(**row)
