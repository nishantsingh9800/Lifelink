import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import reset_repository_cache
from backend.app.main import create_app
from backend.app.services.matching import score_candidate
from backend.app.utils.security import verhoeff_generate_digit


@pytest.fixture()
def tc():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase13_addons_phase2.db"),
            app_jwt_secret="phase13-addons-secret-key-at-least-32-bytes",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as client:
            yield client
        reset_repository_cache()


def _register(tc: TestClient, *, name: str, email: str, phone: str, role: str, seed: str, blood_group=None):
    aadhaar = seed + verhoeff_generate_digit(seed)
    payload = {
        "full_name": name,
        "email": email,
        "phone_number": phone,
        "password": "Password123!",
        "city": "Mathura",
        "approximate_location": "Dampier Nagar",
        "role_preference": role,
        "aadhaar_number": aadhaar,
        "aadhaar_consent": True,
        "terms_accepted": True,
    }
    if blood_group:
        payload["blood_group"] = blood_group
    res = tc.post("/api/auth/register", json=payload)
    assert res.status_code == 201, res.text
    d = res.json()
    return d["user"], {"Authorization": f"Bearer {d['access_token']}"}


def test_preferences_donor_calendar_matching_rules_family_account_and_share_links(tc: TestClient):
    owner, owner_h = _register(tc, name="Owner Family", email="ownp2@example.com", phone="+919933000001", role="requester", seed="95000000001")
    fam, fam_h = _register(tc, name="Family Member", email="famp2@example.com", phone="+919933000002", role="requester", seed="95000000002")
    donor, don_h = _register(tc, name="Calendar Donor", email="doncal@example.com", phone="+919933000003", role="donor", seed="95000000003", blood_group="A+")

    # 1. Language (Hindi) + Accessibility Preferences persistence
    pref = tc.patch(
        "/api/users/me/preferences",
        headers=owner_h,
        json={"preferred_language": "hi", "text_size": "xlarge", "high_contrast": True, "quiet_hours_enabled": True},
    )
    assert pref.status_code == 200
    assert pref.json()["preferred_language"] == "hi"
    assert pref.json()["text_size"] == "xlarge"
    assert pref.json()["high_contrast"] is True
    assert tc.get("/api/auth/me", headers=owner_h).json()["preferred_language"] == "hi"

    # 2. Donor Availability Calendar (selected dates, quiet hours, temporary pause)
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
    cal = tc.put(
        "/api/donors/me/calendar",
        headers=don_h,
        json={
            "availability_status": "available_selected_dates",
            "available_dates": [tomorrow],
            "preferred_distance_km": 15,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "07:00",
        },
    )
    assert cal.status_code == 200
    assert cal.json()["available_dates"] == [tomorrow]
    assert cal.json()["last_availability_updated_at"]

    # Deterministic score_candidate checks for selected dates & quiet hours & pause
    base_req = {"requester_id": owner["id"], "blood_group": "A+", "city": "Mathura", "approximate_location": "Dampier Nagar", "urgency": "normal"}
    base_don = {
        "user_id": donor["id"],
        "account_status": "active",
        "blood_group": "A+",
        "city": "Mathura",
        "approximate_location": "Dampier Nagar",
        "availability_status": "available_selected_dates",
        "available_dates": [tomorrow],
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "07:00",
        "quiet_hours_enabled": True,
        "emergency_override_quiet_hours": True,
    }
    # Outside selected dates -> ineligible
    ok_today, _, _ = score_candidate(request_row=base_req, donor_row=base_don, allow_wider_city=False, review_interval_days=90, evaluation_dt=datetime.now().replace(hour=12, minute=0))
    assert ok_today is False

    # On selected date, outside quiet hours -> eligible
    tm_noon = datetime.fromisoformat(f"{tomorrow}T12:00:00")
    ok_tm, _, _ = score_candidate(request_row=base_req, donor_row=base_don, allow_wider_city=False, review_interval_days=90, evaluation_dt=tm_noon)
    assert ok_tm is True

    # On selected date, during quiet hours for normal urgency -> excluded; emergency -> allowed
    tm_night = datetime.fromisoformat(f"{tomorrow}T23:30:00")
    ok_qh_norm, _, _ = score_candidate(request_row=base_req, donor_row=base_don, allow_wider_city=False, review_interval_days=90, evaluation_dt=tm_night)
    assert ok_qh_norm is False
    ok_qh_emerg, _, _ = score_candidate(request_row={**base_req, "urgency": "emergency"}, donor_row=base_don, allow_wider_city=False, review_interval_days=90, evaluation_dt=tm_night)
    assert ok_qh_emerg is True

    # Paused until tomorrow blocks donor even on selected date
    paused_don = {**base_don, "paused_until": tomorrow}
    ok_paused, _, _ = score_candidate(request_row=base_req, donor_row=paused_don, allow_wider_city=False, review_interval_days=90, evaluation_dt=tm_noon)
    assert ok_paused is False

    # 3. Family Emergency Account authorization -> on-behalf-of creation -> revoke blocks access!
    # Uninvited family member rejected
    unauth_req = tc.post(
        "/api/requests",
        headers=fam_h,
        json={
            "patient_reference_name": "Dad Ward 1",
            "blood_group": "A+",
            "units_requested": 1,
            "hospital_name": "City Hospital",
            "hospital_location": "NH-19",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "urgent",
            "on_behalf_of_user_id": owner["id"],
            "consent_given": True,
        },
    )
    assert unauth_req.status_code == 403

    fam_inv = tc.post(
        "/api/family/contacts",
        headers=owner_h,
        json={"member_identifier": "famp2@example.com", "relationship": "Son"},
    )
    assert fam_inv.status_code == 201
    contact_id = fam_inv.json()["id"]
    tc.post(f"/api/family/contacts/{contact_id}/respond", headers=fam_h, json={"accept": True})

    # Authorized family member creates request on behalf of owner
    behalf_req = tc.post(
        "/api/requests",
        headers=fam_h,
        json={
            "patient_reference_name": "Dad Ward 1",
            "blood_group": "A+",
            "units_requested": 1,
            "hospital_name": "City Hospital",
            "hospital_location": "NH-19",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "urgent",
            "on_behalf_of_user_id": owner["id"],
            "consent_given": True,
        },
    )
    assert behalf_req.status_code == 201
    req_data = behalf_req.json()
    req_id = req_data["id"]
    assert req_data["requester_id"] == owner["id"]
    assert req_data["created_by_user_id"] == fam["id"]

    # Revoke family access -> immediately blocks member from reading request
    rev = tc.post(f"/api/family/contacts/{contact_id}/revoke", headers=owner_h)
    assert rev.status_code == 200
    assert rev.json()["status"] == "revoked"
    assert tc.get(f"/api/requests/{req_id}", headers=fam_h).status_code == 403

    # 4. Privacy-safe request sharing -> public view hides phone/PII -> report -> closure auto-expires link (410)
    share = tc.post(f"/api/share/{req_id}", headers=owner_h)
    assert share.status_code == 201
    token = share.json()["share_token"]

    pub = tc.get(f"/api/public/shared/{token}")
    assert pub.status_code == 200
    pdata = pub.json()
    assert pdata["blood_group"] == "A+"
    assert pdata["hospital_name"] == "City Hospital"
    assert "+919933000001" not in pub.text
    assert "Owner Family" not in pub.text
    assert "Dad Ward 1" not in pub.text

    rep = tc.post(
        f"/api/public/shared/{token}/report",
        json={"reason": "Suspicious shared post", "description": "Testing report"},
    )
    assert rep.status_code == 201

    # Cancelling request immediately expires the public shared link
    tc.post(f"/api/requests/{req_id}/cancel", headers=owner_h, json={"reason": "Arranged locally"})
    expired_pub = tc.get(f"/api/public/shared/{token}")
    assert expired_pub.status_code == 410
