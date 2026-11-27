import tempfile
from datetime import date, timedelta
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
            dev_db_path=str(Path(tmpdir) / "phase10_freeze.db"),
            app_jwt_secret="phase10-freeze-secret-key-at-least-32-bytes",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc, settings
        reset_repository_cache()


def test_three_month_post_donation_freeze_blocks_donor_outreach_until_cooldown_ends(client):
    tc, settings = client
    a_req = "91000000001" + verhoeff_generate_digit("91000000001")
    a_don = "91000000002" + verhoeff_generate_digit("91000000002")

    req_reg = tc.post(
        "/api/auth/register",
        json={
            "full_name": "Requester Ten",
            "email": "req10@example.com",
            "phone_number": "+919877000001",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "role_preference": "requester",
            "aadhaar_number": a_req,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    ).json()
    don_reg = tc.post(
        "/api/auth/register",
        json={
            "full_name": "Donor Ten",
            "email": "don10@example.com",
            "phone_number": "+919877000002",
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

    req_h = {"Authorization": f"Bearer {req_reg['access_token']}"}
    don_h = {"Authorization": f"Bearer {don_reg['access_token']}"}

    tc.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})

    # 1. Create request, match donor, donor accepts
    req1 = tc.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Patient 10A",
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
    tc.post(f"/api/matching/{req1['id']}/run", headers=req_h)
    tc.post(f"/api/responses/{req1['id']}/respond", headers=don_h, json={"response": "accepted"})

    donor_profile = tc.get("/api/donors/me", headers=don_h).json()

    # 2. Fulfill request crediting this donor -> triggers 90-day (3-month) freeze!
    ful = tc.post(
        f"/api/requests/{req1['id']}/outcome",
        headers=req_h,
        json={"outcome": "fulfilled", "donated_by_donor_id": donor_profile["id"]},
    )
    assert ful.status_code == 200

    frozen_profile = tc.get("/api/donors/me", headers=don_h).json()
    expected_unlock = (date.today() + timedelta(days=90)).isoformat()
    assert frozen_profile["is_frozen"] is True
    assert frozen_profile["donor_frozen_until"] == expected_unlock
    assert frozen_profile["availability_status"] == "unavailable"

    # Donor receives cooldown notification
    don_notifs = tc.get("/api/notifications", headers=don_h).json()
    assert any("3-Month Cooldown" in n["title"] for n in don_notifs)

    # 3. Frozen donor CANNOT set availability back to available_now
    re_enable = tc.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})
    assert re_enable.status_code == 403

    # 4. Frozen donor is excluded from public donor search and new request matching
    assert tc.get("/api/public/donors?blood_group=B%2B&city=Mathura").json() == []

    req2 = tc.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Patient 10B",
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
    match2 = tc.post(f"/api/matching/{req2['id']}/run", headers=req_h).json()
    assert match2["newly_notified_count"] == 0

    # 5. Frozen donor CAN still create a request as a requester (not locked out of emergency help)
    own_req = tc.post(
        "/api/requests",
        headers=don_h,
        json={
            "patient_reference_name": "Family Member",
            "blood_group": "O+",
            "units_requested": 1,
            "hospital_name": "District Hospital",
            "hospital_location": "Dampier Nagar",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "urgency": "urgent",
            "consent_given": True,
        },
    )
    assert own_req.status_code == 201

    # 6. Once the 90-day cooldown passes, donor can re-enable availability
    repo = get_repository(settings)
    past_date = (date.today() - timedelta(days=95)).isoformat()
    with repo._connect() as conn:
        conn.execute(
            "UPDATE donor_profiles SET last_donation_date = ?, donor_frozen_until = ? WHERE id = ?",
            (past_date, (date.today() - timedelta(days=5)).isoformat(), donor_profile["id"]),
        )
    unfrozen = tc.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})
    assert unfrozen.status_code == 200
    assert unfrozen.json()["is_frozen"] is False
    assert unfrozen.json()["availability_status"] == "available_now"
