import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import get_repository, reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase6.db"),
            app_jwt_secret="phase6-secret-key-at-least-32-bytes-long",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc, settings
        reset_repository_cache()


def test_blood_bank_directory_contact_attempts_and_outcomes(client):
    tc, settings = client
    reg = tc.post(
        "/api/auth/register",
        json={
            "full_name": "Karan Patel",
            "email": "karan@example.com",
            "phone_number": "+919833000001",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "role_preference": "requester",
            "aadhaar_number": "60000000001" + verhoeff_generate_digit("60000000001"),
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    ).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Empty initially (no fabricated entries)
    assert tc.get("/api/blood-banks").json() == []

    # Add a verified blood bank directly in DB as an admin entry for testing search & contact logging
    repo = get_repository(settings)
    with repo._connect() as conn:
        conn.execute(
            """
            INSERT INTO blood_banks (
                id, facility_name, address, city, phone, latitude, longitude,
                verification_status, availability_status, source, created_at, updated_at
            ) VALUES ('bb-1', 'District Hospital Blood Bank', 'Dampier Nagar', 'Mathura', '+915652400000',
                      27.4924, 77.6737, 'licensed_verified', 'contact_required', 'Official Test Entry',
                      '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
            """
        )

    banks = tc.get("/api/blood-banks?city=Mathura&lat=27.5&lon=77.67").json()
    assert len(banks) == 1
    assert banks[0]["availability_label"] == "Contact required"
    assert banks[0]["distance_km"] is not None
    assert "google.com/maps" in banks[0]["directions_url"]

    req = tc.post(
        "/api/requests",
        headers=headers,
        json={
            "patient_reference_name": "Patient K",
            "blood_group": "B+",
            "units_requested": 1,
            "hospital_name": "District Hospital",
            "hospital_location": "Dampier Nagar",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "emergency",
            "consent_given": True,
        },
    ).json()

    # Record contact attempt
    att = tc.post(
        "/api/blood-banks/bb-1/contact-attempt",
        headers=headers,
        json={"request_id": req["id"], "outcome": "confirmed_available", "notes": "1 unit reserved at counter"},
    )
    assert att.status_code == 201
    updated_bank = tc.get("/api/blood-banks/bb-1").json()
    assert updated_bank["availability_label"] == "Availability confirmed by facility"

    attempts = tc.get(f"/api/blood-banks/attempts/{req['id']}", headers=headers).json()
    assert len(attempts) == 1

    # Record unresolved first, then fulfilled
    unres = tc.post(
        f"/api/requests/{req['id']}/outcome",
        headers=headers,
        json={"outcome": "unresolved", "notes": "Waiting on hospital crossmatch"},
    )
    assert unres.status_code == 200
    assert unres.json()["status"] == "unresolved"

    ful = tc.post(
        f"/api/requests/{req['id']}/outcome",
        headers=headers,
        json={"outcome": "fulfilled", "notes": "Arranged through District Hospital Blood Bank"},
    )
    assert ful.status_code == 200
    assert ful.json()["status"] == "fulfilled"


def test_nearby_live_directory_combines_db_and_external_sources(client, monkeypatch):
    tc, settings = client
    repo = get_repository(settings)
    with repo._connect() as conn:
        conn.execute(
            """
            INSERT INTO blood_banks (
                id, facility_name, address, city, phone, latitude, longitude,
                verification_status, availability_status, source, created_at, updated_at
            ) VALUES ('bb-live-1', 'District Hospital Blood Bank', 'Dampier Nagar', 'Mathura', '+915652400000',
                      27.4924, 77.6737, 'licensed_verified', 'contact_required', 'Official Test Entry',
                      '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
            """
        )

    def _fake_external(**kwargs):
        return {
            "items": [
                {
                    "id": "osm-node-1",
                    "facility_name": "Sadbhawna Charitable Blood Bank",
                    "facility_type": "blood_bank",
                    "address": "NH44, Mathura",
                    "city": "Mathura",
                    "phone": "5652421198",
                    "mobile": "9897529288",
                    "email": "sadbhawnabloodbank@gmail.com",
                    "website": None,
                    "opening_hours": "24/7",
                    "operator_type": "ngo",
                    "latitude": 27.49,
                    "longitude": 77.67,
                    "distance_km": 0.4,
                    "directions_url": "https://www.google.com/maps/search/?api=1&query=Sadbhawna+Mathura",
                    "google_search_url": "https://www.google.com/search?q=Sadbhawna+Mathura",
                    "eraktkosh_url": "https://www.eraktkosh.in/BLDAHIMS/bloodbank/transactions/bbpublicindex.html",
                    "verification_status": "external_public_listing",
                    "availability_status": "contact_required",
                    "availability_label": "Call facility / check e-RaktKosh for live units",
                    "stock_notice": "Live blood-unit inventory is not exposed publicly; call the facility or check e-RaktKosh.",
                    "source": "OpenStreetMap Live",
                },
                {
                    "id": "osm-node-2",
                    "facility_name": "District Combined Hospital",
                    "facility_type": "hospital",
                    "address": "Mathura Road, Mathura",
                    "city": "Mathura",
                    "phone": None,
                    "mobile": None,
                    "email": None,
                    "website": None,
                    "opening_hours": None,
                    "operator_type": "government",
                    "latitude": 27.50,
                    "longitude": 77.68,
                    "distance_km": 1.1,
                    "directions_url": "https://www.google.com/maps/search/?api=1&query=District+Combined+Hospital",
                    "google_search_url": "https://www.google.com/search?q=District+Combined+Hospital",
                    "eraktkosh_url": "https://www.eraktkosh.in/BLDAHIMS/bloodbank/transactions/bbpublicindex.html",
                    "verification_status": "external_public_listing",
                    "availability_status": "contact_required",
                    "availability_label": "Call facility / check e-RaktKosh for live units",
                    "stock_notice": "Live blood-unit inventory is not exposed publicly; call the facility or check e-RaktKosh.",
                    "source": "OpenStreetMap Live",
                },
            ],
            "center_lat": 27.4924,
            "center_lon": 77.6737,
            "sources": ["OpenStreetMap Live"],
            "provider_notice": None,
        }

    monkeypatch.setattr("backend.app.routers.blood_banks.fetch_nearby_external_facilities", _fake_external)

    resp = tc.get("/api/blood-banks/nearby-live?city=Mathura")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["facilities"]) == 3
    assert body["live_stock_api_configured"] is False
    assert "e-RaktKosh" in body["live_stock_note"]
    assert "google.com/maps" in body["maps_nearby_search_url"]
    assert any(f["phone"] == "5652421198" for f in body["facilities"])

    bb_only = tc.get("/api/blood-banks/nearby-live?city=Mathura&facility_type=blood_bank").json()
    assert all(f["facility_type"] == "blood_bank" for f in bb_only["facilities"])
    assert len(bb_only["facilities"]) == 2

