import tempfile
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
            dev_db_path=str(Path(tmpdir) / "phase15_addons_phase4.db"),
            app_jwt_secret="phase15-addons-secret-key-at-least-32-bytes",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc, settings
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


def test_phase4_integration_readiness_honest_gating_masked_call_consent_and_regional_languages(env_ctx):
    tc, settings = env_ctx
    repo = get_repository(settings)

    _adm, adm_h = _register(tc, name="Admin Four", email="adm4@example.com", phone="+919955000001", role="requester", seed="97000000001")
    with repo._connect() as conn:
        conn.execute("UPDATE profiles SET role = 'admin' WHERE email = 'adm4@example.com'")

    req_u, req_h = _register(tc, name="Req Four", email="req4@example.com", phone="+919955000002", role="requester", seed="97000000002")
    don_u, don_h = _register(tc, name="Don Four", email="don4@example.com", phone="+919955000003", role="donor", seed="97000000003", blood_group="O+")
    tc.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})

    # 1. Integration readiness never claims unconfigured integrations are live
    status_res = tc.get("/api/integrations/status")
    assert status_res.status_code == 200
    sdata = status_res.json()
    lang_codes = {item["code"] for item in sdata["supported_languages"]}
    assert {"en", "hi", "mr", "bn", "ta"}.issubset(lang_codes)
    assert sdata["integrations"]["eraktkosh_live_sync"]["status"] == "not_configured"
    assert sdata["integrations"]["masked_calling"]["status"] == "not_configured"
    assert sdata["integrations"]["push_notifications"]["status"] == "not_configured"

    # Admin calls unconfigured sync & push -> honest 501 Not Implemented (and req blocked 403)
    assert tc.post("/api/integrations/eraktkosh/sync", headers=req_h).status_code == 403
    assert tc.post("/api/integrations/eraktkosh/sync", headers=adm_h).status_code == 501
    assert tc.post("/api/integrations/push/dispatch", headers=adm_h).status_code == 501

    # 2. Additional regional language persistence (Marathi / Bengali / Tamil)
    for code in ("mr", "bn", "ta"):
        upd = tc.patch("/api/users/me/preferences", headers=req_h, json={"preferred_language": code})
        assert upd.status_code == 200
        assert upd.json()["preferred_language"] == code

    # 3. Masked calling consent gate: must have mutual consent FIRST (403 before both consent, 501 when unconfigured after both consent)
    req = tc.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Ward 9",
            "blood_group": "O+",
            "units_requested": 1,
            "hospital_name": "City Centre Hospital",
            "hospital_location": "NH-19",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "urgent",
            "consent_given": True,
        },
    ).json()
    tc.post(f"/api/matching/{req['id']}/run", headers=req_h)
    tc.post(f"/api/responses/{req['id']}/respond", headers=don_h, json={"response": "accepted"})

    # Before mutual consent -> 403 Forbidden
    assert tc.post(f"/api/integrations/masked-call/{req['id']}/initiate", headers=req_h).status_code == 403

    # After mutual consent -> unconfigured provider returns 501 Not Implemented cleanly
    tc.post(f"/api/contact-sharing/{req['id']}/consent", headers=req_h, json={"grant": True})
    tc.post(f"/api/contact-sharing/{req['id']}/consent", headers=don_h, json={"grant": True})
    masked_res = tc.post(f"/api/integrations/masked-call/{req['id']}/initiate", headers=req_h)
    assert masked_res.status_code == 501

    # 4. Verified hospitals partnership endpoint returns only verified hospitals cleanly
    _hosp_u, hosp_h = _register(tc, name="Partner Hosp", email="partnerh@example.com", phone="+919955000004", role="hospital", seed="97000000004")
    h = tc.post(
        "/api/hospitals/me",
        headers=hosp_h,
        json={
            "hospital_name": "Braj Verified Medical",
            "registration_number": "UP-P4-777",
            "address": "Vrindavan Road",
            "city": "Mathura",
            "official_phone": "+915652400555",
            "authorized_rep_name": "Dr. K. Sharma",
            "authorized_rep_role": "Director",
        },
    ).json()
    assert len(tc.get("/api/hospitals/verified").json()) == 0
    tc.patch(f"/api/admin/hospitals/{h['id']}/review", headers=adm_h, json={"verification_status": "verified", "notes": "Approved"})
    verified_list = tc.get("/api/hospitals/verified").json()
    assert len(verified_list) == 1
    assert verified_list[0]["hospital_name"] == "Braj Verified Medical"
    assert "does not guarantee blood stock" in verified_list[0]["badge_disclaimer"].lower()

    # 5. Hindi chatbot support (Devanagari & user preferred_language='hi')
    tc.patch("/api/users/me/preferences", headers=req_h, json={"preferred_language": "hi"})
    hi_bot = tc.post("/api/chatbot/message", headers=req_h, json={"message": "मुझे तुरंत मदद और खून चाहिए"})
    assert hi_bot.status_code == 200
    assert hi_bot.json()["intent"] == "emergency_guidance"
    assert "LifeLink" in hi_bot.json()["disclaimer"]
    assert any(ord(ch) >= 0x0900 and ord(ch) <= 0x097F for ch in hi_bot.json()["reply"])
