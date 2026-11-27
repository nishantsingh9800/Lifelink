import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit


def _register_no_aadhaar(tc: TestClient, *, name: str, email: str, phone: str, role: str, blood_group=None):
    payload = {
        "full_name": name,
        "email": email,
        "phone_number": phone,
        "password": "Password123!",
        "city": "Mathura",
        "approximate_location": "Dampier Nagar",
        "role_preference": role,
        "terms_accepted": True,
    }
    if blood_group:
        payload["blood_group"] = blood_group
    res = tc.post("/api/auth/register", json=payload)
    assert res.status_code == 201, res.text
    d = res.json()
    return d["user"], {"Authorization": f"Bearer {d['access_token']}"}


def test_aadhaar_off_by_default_allows_signup_login_donate_and_receive():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase16_off.db"),
            app_jwt_secret="phase16-off-secret-key-at-least-32-bytes",
            require_aadhaar_for_actions=False,
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            cfg = tc.get("/api/config/public").json()
            assert cfg["require_aadhaar_for_actions"] is False

            _req, req_h = _register_no_aadhaar(tc, name="NoAadhaar Req", email="nar@example.com", phone="+919966000001", role="requester")
            _don, don_h = _register_no_aadhaar(tc, name="NoAadhaar Don", email="nad@example.com", phone="+919966000002", role="donor", blood_group="O+")

            # Can log in cleanly
            login_res = tc.post("/api/auth/login", json={"identifier": "nar@example.com", "password": "Password123!"})
            assert login_res.status_code == 200

            # Can receive (create request) and donate (accept) without Aadhaar when turned off
            tc.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})
            req = tc.post(
                "/api/requests",
                headers=req_h,
                json={
                    "patient_reference_name": "Ward 1",
                    "blood_group": "O+",
                    "units_requested": 1,
                    "hospital_name": "District Hospital",
                    "hospital_location": "Dampier Nagar",
                    "city": "Mathura",
                    "approximate_location": "Dampier Nagar",
                    "urgency": "urgent",
                    "consent_given": True,
                },
            )
            assert req.status_code == 201
            req_id = req.json()["id"]
            tc.post(f"/api/matching/{req_id}/run", headers=req_h)
            acc = tc.post(f"/api/responses/{req_id}/respond", headers=don_h, json={"response": "accepted"})
            assert acc.status_code == 200
        reset_repository_cache()


def test_aadhaar_enforced_at_donation_and_receipt_when_enabled():
    a_req = "88000000001" + verhoeff_generate_digit("88000000001")
    a_don = "88000000002" + verhoeff_generate_digit("88000000002")
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase16_on.db"),
            app_jwt_secret="phase16-on-secret-key-at-least-32-bytes",
            require_aadhaar_for_actions=True,
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            cfg = tc.get("/api/config/public").json()
            assert cfg["require_aadhaar_for_actions"] is True

            # Signup & Login STILL succeed without Aadhaar!
            _req, req_h = _register_no_aadhaar(tc, name="Gate Req", email="gatereq@example.com", phone="+919977000001", role="requester")
            _don, don_h = _register_no_aadhaar(tc, name="Gate Don", email="gatedon@example.com", phone="+919977000002", role="donor", blood_group="B+")
            tc.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})

            # Receiving blocked until Aadhaar verified
            blocked_req = tc.post(
                "/api/requests",
                headers=req_h,
                json={
                    "patient_reference_name": "Ward 2",
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
            assert blocked_req.status_code == 403

            # Verify requester Aadhaar -> receiving now succeeds
            v_req = tc.post("/api/auth/aadhaar/verify", headers=req_h, json={"aadhaar_number": a_req, "aadhaar_consent": True})
            assert v_req.status_code == 200
            assert v_req.json()["aadhaar_verified"] is True

            ok_req = tc.post(
                "/api/requests",
                headers=req_h,
                json={
                    "patient_reference_name": "Ward 2",
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
            assert ok_req.status_code == 201
            req_id = ok_req.json()["id"]
            tc.post(f"/api/matching/{req_id}/run", headers=req_h)

            # Donor accepting (donating) blocked 403 until Aadhaar verified; declining works without Aadhaar
            blocked_don = tc.post(f"/api/responses/{req_id}/respond", headers=don_h, json={"response": "accepted"})
            assert blocked_don.status_code == 403

            v_don = tc.post("/api/auth/aadhaar/verify", headers=don_h, json={"aadhaar_number": a_don, "aadhaar_consent": True})
            assert v_don.status_code == 200
            assert v_don.json()["aadhaar_verified"] is True

            ok_don = tc.post(f"/api/responses/{req_id}/respond", headers=don_h, json={"response": "accepted"})
            assert ok_don.status_code == 200

            # Hospital registering staff also blocked 403 until Aadhaar verified
            a_hosp = "88000000003" + verhoeff_generate_digit("88000000003")
            _hosp, hosp_h = _register_no_aadhaar(tc, name="Hosp Staff", email="hospstaff@example.com", phone="+919977000003", role="hospital")
            hosp_payload = {
                "hospital_name": "LifeLink Staff Verified Hospital",
                "registration_number": "UP-16-999",
                "address": "Mathura Road",
                "city": "Mathura",
                "official_phone": "+915652400123",
                "authorized_rep_name": "Dr. Rep",
                "authorized_rep_role": "Medical Officer",
            }
            assert tc.post("/api/hospitals/me", headers=hosp_h, json=hosp_payload).status_code == 403
            tc.post("/api/auth/aadhaar/verify", headers=hosp_h, json={"aadhaar_number": a_hosp, "aadhaar_consent": True})
            assert tc.post("/api/hospitals/me", headers=hosp_h, json=hosp_payload).status_code == 200
        reset_repository_cache()
