import math
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import httpx

_CACHE_TTL_SECONDS = 300
_NEARBY_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_HTTP_HEADERS = {"User-Agent": "LifeLink-BloodDonorApp/1.0 (https://github.com/lifelink)"}
ERAKT_KOSH_PORTAL_URL = "https://www.eraktkosh.in/BLDAHIMS/bloodbank/transactions/bbpublicindex.html"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return round(2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


def clear_nearby_cache() -> None:
    _NEARBY_CACHE.clear()


def _normalize_phone(extra: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    primary = (
        extra.get("phone")
        or extra.get("contact:phone")
        or extra.get("mobile")
        or extra.get("contact:mobile")
        or ""
    ).strip()
    mobile = (extra.get("contact:mobile") or extra.get("mobile") or "").strip()
    if mobile and mobile == primary:
        mobile = ""
    return primary, (mobile or None)


def _extract_address(item: Dict[str, Any], fallback_city: str) -> Tuple[str, str]:
    addr = item.get("address") or {}
    city_name = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("state_district")
        or addr.get("county")
        or fallback_city
        or ""
    )
    parts = [
        addr.get("road"),
        addr.get("suburb") or addr.get("neighbourhood"),
        city_name,
        addr.get("state"),
        addr.get("postcode"),
    ]
    cleaned = ", ".join(str(p).strip() for p in parts if p and str(p).strip())
    if not cleaned:
        cleaned = str(item.get("display_name") or "").strip()
    return cleaned, str(city_name).strip()


def _geocode_city_nominatim(client: httpx.Client, city: str) -> Optional[Tuple[float, float]]:
    q = city.strip()
    if not q:
        return None
    if "india" not in q.lower():
        q = f"{q}, India"
    resp = client.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": q, "format": "jsonv2", "limit": 1},
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return None
    return float(rows[0]["lat"]), float(rows[0]["lon"])


def _query_nominatim_facilities(
    client: httpx.Client,
    *,
    search_term: str,
    facility_type: str,
    center_lat: float,
    center_lon: float,
    city_label: str,
    radius_km: float,
) -> List[Dict[str, Any]]:
    deg_pad = min(1.0, max(0.25, radius_km / 95.0))
    viewbox = f"{center_lon - deg_pad},{center_lat + deg_pad},{center_lon + deg_pad},{center_lat - deg_pad}"
    params = {
        "q": search_term,
        "format": "jsonv2",
        "addressdetails": 1,
        "extratags": 1,
        "limit": 15,
        "viewbox": viewbox,
        "bounded": 1,
    }
    resp = client.get("https://nominatim.openstreetmap.org/search", params=params)
    resp.raise_for_status()
    rows = resp.json() or []

    out: List[Dict[str, Any]] = []
    for item in rows:
        try:
            f_lat = float(item["lat"])
            f_lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        dist = haversine_km(center_lat, center_lon, f_lat, f_lon)
        if dist > max(radius_km, 60.0):
            continue

        display_name = str(item.get("display_name") or "").strip()
        name = str(item.get("name") or "").strip()
        if not name and display_name:
            name = display_name.split(",")[0].strip()
        if not name:
            continue

        extra = item.get("extratags") or {}
        phone, mobile = _normalize_phone(extra)
        address, resolved_city = _extract_address(item, city_label)
        lower_name = name.lower()
        resolved_type = "blood_bank" if ("blood" in lower_name or facility_type == "blood_bank") else "hospital"
        maps_q = quote_plus(f"{name}, {address}")
        google_q = quote_plus(f"{name} {resolved_city} contact number blood bank".strip())

        out.append(
            {
                "id": f"osm-{item.get('osm_type', 'n')}-{item.get('osm_id', abs(hash(name)))}",
                "facility_name": name,
                "facility_type": resolved_type,
                "address": address,
                "city": resolved_city or city_label or "Nearby",
                "phone": phone or None,
                "mobile": mobile,
                "email": (extra.get("email") or extra.get("contact:email") or None),
                "website": (extra.get("website") or extra.get("contact:website") or None),
                "opening_hours": (extra.get("opening_hours") or None),
                "operator_type": (extra.get("operator:type") or None),
                "latitude": f_lat,
                "longitude": f_lon,
                "distance_km": dist,
                "directions_url": f"https://www.google.com/maps/search/?api=1&query={maps_q}",
                "google_search_url": f"https://www.google.com/search?q={google_q}",
                "eraktkosh_url": ERAKT_KOSH_PORTAL_URL,
                "verification_status": "external_public_listing",
                "availability_status": "contact_required",
                "availability_label": "Call facility / check e-RaktKosh for live units",
                "stock_notice": "Live blood-unit inventory is not exposed publicly; call the facility or check e-RaktKosh.",
                "source": "OpenStreetMap Live",
            }
        )
    return out


def _query_google_places_facilities(
    client: httpx.Client,
    *,
    api_key: str,
    city: str,
    query_text: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    radius_km: float,
) -> Tuple[List[Dict[str, Any]], Optional[float], Optional[float]]:
    terms = [query_text] if query_text else ["blood bank", "hospital"]
    items: List[Dict[str, Any]] = []
    center_lat, center_lon = lat, lon

    for term in terms:
        full_q = f"{term} in {city}".strip() if city else term
        params: Dict[str, Any] = {"query": full_q, "key": api_key}
        if center_lat is not None and center_lon is not None:
            params["location"] = f"{center_lat},{center_lon}"
            params["radius"] = int(min(50000, radius_km * 1000))
        resp = client.get("https://maps.googleapis.com/maps/api/place/textsearch/json", params=params)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") not in ("OK", "ZERO_RESULTS"):
            raise RuntimeError(payload.get("error_message") or f"Google Places status: {payload.get('status')}")

        for r in (payload.get("results") or [])[:12]:
            loc = (r.get("geometry") or {}).get("location") or {}
            f_lat = loc.get("lat")
            f_lon = loc.get("lng")
            if center_lat is None and f_lat is not None and f_lon is not None:
                center_lat, center_lon = float(f_lat), float(f_lon)
            dist = (
                haversine_km(center_lat, center_lon, float(f_lat), float(f_lon))
                if center_lat is not None and center_lon is not None and f_lat is not None and f_lon is not None
                else None
            )
            name = str(r.get("name") or "").strip()
            address = str(r.get("formatted_address") or "").strip()
            place_id = str(r.get("place_id") or "").strip()
            phone = None
            website = None
            if place_id:
                try:
                    det = client.get(
                        "https://maps.googleapis.com/maps/api/place/details/json",
                        params={
                            "place_id": place_id,
                            "fields": "formatted_phone_number,international_phone_number,website,opening_hours",
                            "key": api_key,
                        },
                    )
                    if det.status_code == 200:
                        d_res = (det.json() or {}).get("result") or {}
                        phone = d_res.get("international_phone_number") or d_res.get("formatted_phone_number")
                        website = d_res.get("website")
                except httpx.HTTPError:
                    pass

            resolved_type = "blood_bank" if "blood" in name.lower() or "blood" in term.lower() else "hospital"
            maps_q = quote_plus(f"{name}, {address}")
            google_q = quote_plus(f"{name} {city} contact number blood bank".strip())
            items.append(
                {
                    "id": f"gplaces-{place_id or abs(hash(name))}",
                    "facility_name": name,
                    "facility_type": resolved_type,
                    "address": address or city or "Nearby",
                    "city": city or "Nearby",
                    "phone": phone,
                    "mobile": None,
                    "email": None,
                    "website": website,
                    "opening_hours": "Open now" if (r.get("opening_hours") or {}).get("open_now") else None,
                    "operator_type": None,
                    "latitude": float(f_lat) if f_lat is not None else None,
                    "longitude": float(f_lon) if f_lon is not None else None,
                    "distance_km": dist,
                    "directions_url": f"https://www.google.com/maps/search/?api=1&query={maps_q}",
                    "google_search_url": f"https://www.google.com/search?q={google_q}",
                    "eraktkosh_url": ERAKT_KOSH_PORTAL_URL,
                    "verification_status": "external_google_places",
                    "availability_status": "contact_required",
                    "availability_label": "Call facility / check e-RaktKosh for live units",
                    "stock_notice": "Live blood-unit inventory is not exposed by Google Maps; call the facility or check e-RaktKosh.",
                    "source": "Google Places Live",
                }
            )
    return items, center_lat, center_lon


def fetch_nearby_external_facilities(
    *,
    city: Optional[str] = None,
    query_text: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: float = 35.0,
    google_api_key: str = "",
) -> Dict[str, Any]:
    """Fetch real nearby blood banks and hospitals from Google Places (if key configured) or OpenStreetMap."""
    norm_city = (city or "").strip()
    norm_q = (query_text or "").strip()
    if not norm_city and (lat is None or lon is None) and not norm_q:
        return {
            "items": [],
            "center_lat": None,
            "center_lon": None,
            "sources": [],
            "provider_notice": "Enter a city or click 'Use My GPS Location' to load nearby blood banks and hospitals.",
        }

    cache_key = "|".join(
        [
            "g" if google_api_key.strip() else "osm",
            norm_city.lower(),
            norm_q.lower(),
            f"{lat:.2f}" if lat is not None else "",
            f"{lon:.2f}" if lon is not None else "",
            str(int(radius_km)),
        ]
    )
    now = time.time()
    cached = _NEARBY_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    items: List[Dict[str, Any]] = []
    sources: List[str] = []
    center_lat, center_lon = lat, lon
    provider_notice: Optional[str] = None

    with httpx.Client(headers=_HTTP_HEADERS, timeout=10.0) as client:
        if google_api_key.strip():
            try:
                items, center_lat, center_lon = _query_google_places_facilities(
                    client,
                    api_key=google_api_key.strip(),
                    city=norm_city,
                    query_text=norm_q or None,
                    lat=center_lat,
                    lon=center_lon,
                    radius_km=radius_km,
                )
                sources.append("Google Places Live")
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                provider_notice = f"Google Places unavailable ({exc}); falling back to OpenStreetMap."

        if not items:
            try:
                if (center_lat is None or center_lon is None) and norm_city:
                    coords = _geocode_city_nominatim(client, norm_city)
                    if coords:
                        center_lat, center_lon = coords

                if center_lat is not None and center_lon is not None:
                    terms: List[Tuple[str, str]]
                    if norm_q:
                        terms = [(norm_q, "blood_bank" if "blood" in norm_q.lower() else "hospital")]
                    else:
                        terms = [("blood bank", "blood_bank"), ("hospital", "hospital")]

                    for term, f_type in terms:
                        found = _query_nominatim_facilities(
                            client,
                            search_term=term,
                            facility_type=f_type,
                            center_lat=center_lat,
                            center_lon=center_lon,
                            city_label=norm_city,
                            radius_km=radius_km,
                        )
                        items.extend(found)
                    if items:
                        sources.append("OpenStreetMap Live")
                    elif not provider_notice:
                        provider_notice = "No public OpenStreetMap facilities found within range; check e-RaktKosh or Google Maps."
                else:
                    provider_notice = f"Could not resolve coordinates for '{norm_city}'. Try a major city name or click 'Use My GPS Location'."
            except (httpx.HTTPError, ValueError) as exc:
                provider_notice = f"Live external map directory temporarily unreachable ({exc}). You can still search e-RaktKosh or Google Maps directly."

    # Deduplicate by normalized facility name and filter by query text if specified
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for entry in items:
        key = entry["facility_name"].lower().strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)

    deduped.sort(
        key=lambda x: (
            0 if x["facility_type"] == "blood_bank" else 1,
            0 if x.get("phone") else 1,
            x["distance_km"] if x.get("distance_km") is not None else 9999.0,
        )
    )

    result = {
        "items": deduped,
        "center_lat": center_lat,
        "center_lon": center_lon,
        "sources": sources,
        "provider_notice": provider_notice,
    }
    if items:
        _NEARBY_CACHE[cache_key] = (now, result)
    return result
