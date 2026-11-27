import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase11_tracking.db"),
            app_jwt_secret="phase11-tracking-secret-key-at-least-32-bytes",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc
        reset_repository_cache()


def test_privacy_safe_radius_tracking_and_access_control(client):
    a_req = "92000000001" + verhoeff_generate_digit("92000000001")
    a_don = "92000000002" + verhoeff_generate_digit("92000000002")
    a_spy = "92000000003" + verhoeff_generate_digit("92000000003")

    req_reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Requester Eleven",
            "email": "req11@example.com",
            "phone_number": "+919888000001",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "role_preference": "requester",
            "aadhaar_number": a_req,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    ).json()
    don_reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Donor Eleven",
            "email": "don11@example.com",
            "phone_number": "+919888000002",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "role_preference": "donor",
            "blood_group": "B+",
            "aadhaar_number": a_don,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    ).json()
    spy_reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Spy Eleven",
            "email": "spy11@example.com",
            "phone_number": "+919888000003",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "role_preference": "requester",
            "aadhaar_number": a_spy,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    ).json()

    req_h = {"Authorization": f"Bearer {req_reg['access_token']}"}
    don_h = {"Authorization": f"Bearer {don_reg['access_token']}"}
    spy_h = {"Authorization": f"Bearer {spy_reg['access_token']}"}

    client.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})

    blood_req = client.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Patient Map",
            "blood_group": "B+",
            "units_requested": 1,
            "hospital_name": "Mathura Care",
            "hospital_location": "NH-19",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "urgency": "emergency",
            "consent_given": True,
        },
    ).json()
    req_id = blood_req["id"]
    client.post(f"/api/matching/{req_id}/run", headers=req_h)

    # Accepting with exact GPS coordinates stores ONLY obfuscated ~1 km zone center
    exact_lat = 27.494817
    exact_lon = 77.673942
    acc = client.post(
        f"/api/responses/{req_id}/respond",
        headers=don_h,
        json={"response": "accepted", "latitude": exact_lat, "longitude": exact_lon},
    )
    assert acc.status_code == 200

    # Spy cannot read or update tracking
    assert client.get(f"/api/tracking/{req_id}", headers=spy_h).status_code == 403
    assert (
        client.post(
            f"/api/tracking/{req_id}/update",
            headers=spy_h,
            json={"latitude": exact_lat, "longitude": exact_lon, "tracking_status": "nearby"},
        ).status_code
        == 403
    )

    # Requester sees radius zone WITHOUT exact GPS coordinates
    zones = client.get(f"/api/tracking/{req_id}", headers=req_h).json()
    assert len(zones) == 1
    assert zones[0]["zone_lat"] == 27.49
    assert zones[0]["zone_lon"] == 77.67
    assert zones[0]["zone_lat"] != exact_lat
    assert zones[0]["zone_lon"] != exact_lon
    assert zones[0]["radius_meters"] == 1000
    assert zones[0]["tracking_status"] == "en_route"
    assert zones[0]["is_active"] is True

    # Donor updates status -> arrived_at_hospital, then stops sharing
    upd = client.post(
        f"/api/tracking/{req_id}/update",
        headers=don_h,
        json={"latitude": 27.516234, "longitude": 77.651234, "tracking_status": "arrived_at_hospital"},
    )
    assert upd.status_code == 200
    assert upd.json()["tracking_status"] == "arrived_at_hospital"
    assert upd.json()["zone_lat"] == 27.52

    assert client.post(f"/api/tracking/{req_id}/stop", headers=don_h).status_code == 200
    stopped = client.get(f"/api/tracking/{req_id}", headers=req_h).json()
    assert stopped[0]["is_active"] is False

    # Closed request blocks further tracking updates
    client.post(f"/api/requests/{req_id}/cancel", headers=req_h, json={"reason": "Closed"})
    closed_upd = client.post(
        f"/api/tracking/{req_id}/update",
        headers=don_h,
        json={"latitude": exact_lat, "longitude": exact_lon, "tracking_status": "nearby"},
    )
    assert closed_upd.status_code == 400
