import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit


def _next_aadhaar(seed: int) -> str:
    prefix = f"2{seed:010d}"
    return prefix + verhoeff_generate_digit(prefix)


_AADHAAR_SEQ = 1000


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase2.db"),
            app_jwt_secret="phase2-secret-key-at-least-32-bytes-long",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc, settings
        reset_repository_cache()


def _register(tc: TestClient, email: str, phone: str, role: str, blood_group: str | None = None):
    global _AADHAAR_SEQ
    _AADHAAR_SEQ += 1
    payload = {
        "full_name": f"User {email.split('@')[0]}",
        "email": email,
        "phone_number": phone,
        "password": "Password123!",
        "city": "Mathura",
        "approximate_location": "Chaumuha",
        "role_preference": role,
        "aadhaar_number": _next_aadhaar(_AADHAAR_SEQ),
        "aadhaar_consent": True,
        "terms_accepted": True,
    }
    if blood_group:
        payload["blood_group"] = blood_group
    res = tc.post("/api/auth/register", json=payload)
    assert res.status_code == 201
    return res.json()["access_token"], res.json()["user"]


def test_donor_profile_availability_and_history_privacy(client):
    tc, _ = client
    token, _ = _register(tc, "donor2@example.com", "+919800112201", "donor", "B+")
    headers = {"Authorization": f"Bearer {token}"}

    # Get donor profile
    me = tc.get("/api/donors/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["blood_group"] == "B+"
    assert me.json()["availability_status"] == "unavailable"

    # Update availability to available_now
    avail = tc.patch(
        "/api/donors/me/availability",
        headers=headers,
        json={"availability_status": "available_now", "emergency_notifications_enabled": True},
    )
    assert avail.status_code == 200
    assert avail.json()["availability_status"] == "available_now"

    # Public search shows donor now that they are available_now, WITHOUT leaking phone/email
    search = tc.get("/api/public/donors?blood_group=B%2B&city=Mathura")
    assert search.status_code == 200
    items = search.json()
    assert len(items) == 1
    assert "phone_number" not in items[0]
    assert "email" not in items[0]
    assert items[0]["city"] == "Mathura"

    # Update donation history within 90 days -> informational review note AND 3-month freeze triggered
    recent_date = (date.today() - timedelta(days=30)).isoformat()
    hist = tc.patch(
        "/api/donors/me/donation-history",
        headers=headers,
        json={"last_donation_date": recent_date},
    )
    assert hist.status_code == 200
    assert "eligibility review by the blood bank is required" in hist.json()["eligibility_review_note"]
    assert hist.json()["is_frozen"] is True
    assert hist.json()["availability_status"] == "unavailable"
    assert tc.get("/api/public/donors?blood_group=B%2B&city=Mathura").json() == []


def test_blood_request_lifecycle_duplicates_expiry_and_isolation(client):
    tc, settings = client
    req_token, _ = _register(tc, "req2@example.com", "+919800112202", "requester")
    other_token, _ = _register(tc, "other2@example.com", "+919800112203", "requester")
    req_headers = {"Authorization": f"Bearer {req_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # Consent must be True
    bad_consent = tc.post(
        "/api/requests",
        headers=req_headers,
        json={
            "patient_reference_name": "Patient A",
            "blood_group": "B+",
            "units_requested": 2,
            "hospital_name": "District Hospital",
            "hospital_location": "Dampier Nagar",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "emergency",
            "consent_given": False,
        },
    )
    assert bad_consent.status_code == 422

    # Valid creation
    created = tc.post(
        "/api/requests",
        headers=req_headers,
        json={
            "patient_reference_name": "Patient A",
            "blood_group": "B+",
            "units_requested": 2,
            "hospital_name": "District Hospital",
            "hospital_location": "Dampier Nagar",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "emergency",
            "consent_given": True,
        },
    )
    assert created.status_code == 201
    req_id = created.json()["id"]
    assert created.json()["status"] == "created"

    # Duplicate active request for same group & city is rejected
    dup = tc.post(
        "/api/requests",
        headers=req_headers,
        json={
            "patient_reference_name": "Patient A Dup",
            "blood_group": "B+",
            "units_requested": 1,
            "hospital_name": "District Hospital",
            "hospital_location": "Dampier Nagar",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "urgent",
            "consent_given": True,
        },
    )
    assert dup.status_code == 409

    # Other user cannot read or modify this request
    assert tc.get(f"/api/requests/{req_id}", headers=other_headers).status_code == 403
    assert tc.patch(f"/api/requests/{req_id}", headers=other_headers, json={"units_requested": 4}).status_code == 403

    # Requester updates units and cancels
    upd = tc.patch(f"/api/requests/{req_id}", headers=req_headers, json={"units_requested": 3})
    assert upd.status_code == 200
    assert upd.json()["units_requested"] == 3

    cancelled = tc.post(f"/api/requests/{req_id}/cancel", headers=req_headers, json={"reason": "Arranged locally"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # History contains created -> update -> cancelled
    hist = tc.get(f"/api/requests/{req_id}/history", headers=req_headers)
    assert hist.status_code == 200
    assert [h["new_status"] for h in hist.json()] == ["created", "created", "cancelled"]

    # Expired request auto-transitions when expires_at is in the past
    past_req = tc.post(
        "/api/requests",
        headers=req_headers,
        json={
            "patient_reference_name": "Patient Past",
            "blood_group": "O+",
            "units_requested": 1,
            "hospital_name": "City Clinic",
            "hospital_location": "NH-19",
            "city": "Mathura",
            "approximate_location": "NH-19",
            "urgency": "normal",
            "requested_for": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
            "expiry_hours": 1,
            "consent_given": True,
        },
    )
    assert past_req.status_code == 201
    past_id = past_req.json()["id"]

    from backend.app.database import get_repository
    repo = get_repository(settings)
    with repo._connect() as conn:
        conn.execute(
            "UPDATE blood_requests SET expires_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(), past_id),
        )

    fetched = tc.get(f"/api/requests/{past_id}", headers=req_headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "expired"
