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
def env_ctx():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase14_addons_phase3.db"),
            app_jwt_secret="phase14-addons-secret-key-at-least-32-bytes",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc, settings
        reset_repository_cache()


def _register(tc: TestClient, *, name: str, email: str, phone: str, role: str, seed: str, blood_group=None, referral_code=None):
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
    if referral_code:
        payload["referral_code"] = referral_code
    res = tc.post("/api/auth/register", json=payload)
    assert res.status_code == 201, res.text
    d = res.json()
    return d["user"], {"Authorization": f"Bearer {d['access_token']}"}


def test_donor_trust_donation_history_correction_referrals_and_appreciation(env_ctx):
    tc, _settings = env_ctx
    don_u, don_h = _register(tc, name="Donor Trust", email="dontrust@example.com", phone="+919944000001", role="donor", seed="96000000001", blood_group="O+")
    _req_u, req_h = _register(tc, name="Requester Trust", email="reqtrust@example.com", phone="+919944000002", role="requester", seed="96000000002")
    _spy_u, spy_h = _register(tc, name="Stranger Spy", email="spytrust@example.com", phone="+919944000003", role="requester", seed="96000000003")

    donor_me = tc.get("/api/donors/me", headers=don_h).json()
    donor_id = donor_me["id"]

    # 1. Self-reported multi-type donation records + correction workflow (never becomes facility verified on self-claim)
    d_date = (date.today() - timedelta(days=40)).isoformat()
    add_rec = tc.post(
        "/api/donors/me/donations",
        headers=don_h,
        json={
            "donation_date": d_date,
            "donation_type": "platelets",
            "facility_name": "Mathura District Blood Bank",
            "notes": "Voluntary SDP donation",
        },
    )
    assert add_rec.status_code == 201
    rec_data = add_rec.json()
    assert rec_data["evidence_status"] == "self_reported"
    assert rec_data["guidance_window_days"] == 14  # Platelets configurable interval != universal 90d

    corr = tc.patch(
        f"/api/donors/me/donations/{rec_data['id']}",
        headers=don_h,
        json={"facility_name": "Corrected Mathura Blood Centre", "correction_reason": "Updated facility name"},
    )
    assert corr.status_code == 200
    assert corr.json()["is_corrected"] is True
    assert corr.json()["facility_name"] == "Corrected Mathura Blood Centre"

    rem = tc.post("/api/donors/me/availability-reminder", headers=don_h)
    assert rem.status_code == 200
    assert rem.json()["reminded"] is True

    # 2. Referrals & anti-abuse check
    ref = tc.get("/api/referrals/me", headers=don_h).json()
    code = ref["referral_code"]
    assert ref["successful_referrals_count"] == 0

    _invited_u, _ = _register(
        tc,
        name="Referred Friend",
        email="friendp3@example.com",
        phone="+919944000004",
        role="donor",
        seed="96000000004",
        blood_group="A+",
        referral_code=code,
    )
    ref_after = tc.get("/api/referrals/me", headers=don_h).json()
    assert ref_after["successful_referrals_count"] == 1

    # 3. Trust profile isolation: stranger blocked (403); matched requester allowed (verified vs self-declared separated)
    assert tc.get(f"/api/donors/{donor_id}/trust-profile", headers=spy_h).status_code == 403

    tc.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})
    req = tc.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Ward 6",
            "blood_group": "O+",
            "units_requested": 1,
            "hospital_name": "District Hospital",
            "hospital_location": "Dampier Nagar",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "urgent",
            "consent_given": True,
        },
    ).json()
    tc.post(f"/api/matching/{req['id']}/run", headers=req_h)

    trust = tc.get(f"/api/donors/{donor_id}/trust-profile", headers=req_h)
    assert trust.status_code == 200
    t_data = trust.json()
    assert t_data["verified_indicators"]["evidence_backed_donations_count"] == 0
    assert t_data["self_declared_indicators"]["self_reported_donations_count"] == 1
    assert "zero penalty" in t_data["response_summary"]["declining_policy"].lower()
    assert "+919944000001" not in trust.text

    # 4. Voluntary Appreciation & privacy toggle
    appr = tc.get("/api/donors/me/appreciation", headers=don_h).json()
    assert appr["recognition_public"] is False
    assert "NOT an official government or medical certificate" in appr["digital_card"]["disclaimer"]

    toggled = tc.patch("/api/donors/me/appreciation", headers=don_h, json={"recognition_public": True}).json()
    assert toggled["recognition_public"] is True
