import tempfile
from datetime import datetime, timedelta, timezone
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
            dev_db_path=str(Path(tmpdir) / "phase12_addons_phase1.db"),
            upload_dir=str(Path(tmpdir) / "uploads"),
            app_jwt_secret="phase12-addons-secret-key-at-least-32-bytes",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc, settings
        reset_repository_cache()


def _aadhaar(seed: str) -> str:
    return seed + verhoeff_generate_digit(seed)


def _register(tc: TestClient, *, full_name: str, email: str, phone: str, role: str, seed: str, blood_group=None):
    payload = {
        "full_name": full_name,
        "email": email,
        "phone_number": phone,
        "password": "Password123!",
        "city": "Mathura",
        "approximate_location": "Dampier Nagar",
        "role_preference": role,
        "aadhaar_number": _aadhaar(seed),
        "aadhaar_consent": True,
        "terms_accepted": True,
    }
    if blood_group:
        payload["blood_group"] = blood_group
    res = tc.post("/api/auth/register", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    return data["user"], {"Authorization": f"Bearer {data['access_token']}"}


def test_quick_request_live_tracking_coordinator_and_cancellation_notifications(env_ctx):
    tc, _settings = env_ctx
    _req_u, req_h = _register(tc, full_name="Requester One", email="reqp1@example.com", phone="+919911000001", role="requester", seed="93000000001")
    _don_u, don_h = _register(tc, full_name="Donor One", email="donp1@example.com", phone="+919911000002", role="donor", seed="93000000002", blood_group="O+")
    _coord_u, coord_h = _register(tc, full_name="Trusted Coordinator", email="coord1@example.com", phone="+919911000003", role="requester", seed="93000000003")
    _spy_u, spy_h = _register(tc, full_name="Spy User", email="spyp1@example.com", phone="+919911000004", role="requester", seed="93000000004")

    tc.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})

    # 1. Quick Emergency Request with family/coordinator reference
    create_res = tc.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Ward 3 Emergency",
            "blood_group": "O+",
            "units_requested": 2,
            "hospital_name": "District Hospital Mathura",
            "hospital_location": "Dampier Nagar",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "emergency",
            "is_emergency_quick": True,
            "coordinator_contact_name": "Trusted Coordinator",
            "coordinator_contact_relation": "Brother",
            "consent_given": True,
        },
    )
    assert create_res.status_code == 201
    req_data = create_res.json()
    req_id = req_data["id"]
    assert req_data["is_emergency_quick"] is True
    assert "not medically verified" in req_data["safety_notice"].lower()

    # Duplicate active request prevented
    dup = tc.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Dup",
            "blood_group": "O+",
            "units_requested": 1,
            "hospital_name": "District Hospital Mathura",
            "hospital_location": "Dampier Nagar",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "urgent",
            "consent_given": True,
        },
    )
    assert dup.status_code == 409

    # 2. Match donor -> donor accepts -> live tracking 8 steps
    run = tc.post(f"/api/matching/{req_id}/run", headers=req_h)
    assert run.status_code == 200
    assert run.json()["newly_notified_count"] == 1

    resp = tc.post(f"/api/responses/{req_id}/respond", headers=don_h, json={"response": "accepted"})
    assert resp.status_code == 200
    conv_id = resp.json()["conversation_id"]
    assert conv_id

    track = tc.get(f"/api/requests/{req_id}/tracking-summary", headers=req_h)
    assert track.status_code == 200
    tdata = track.json()
    assert len(tdata["timeline"]) == 8
    assert tdata["donors_notified"] == 1
    assert tdata["donors_interested"] == 1
    assert "+919911000002" not in track.text  # Phone strictly never leaked

    # Spy blocked from tracking
    assert tc.get(f"/api/requests/{req_id}/tracking-summary", headers=spy_h).status_code == 403

    # 3. Emergency Coordinator invite -> accept -> chat & progress update -> revoke -> blocked!
    invite = tc.post(
        f"/api/coordinators/{req_id}/invite",
        headers=req_h,
        json={"coordinator_identifier": "coord1@example.com"},
    )
    assert invite.status_code == 201
    assign_id = invite.json()["id"]
    assert invite.json()["status"] == "invited"

    # Unaccepted coordinator cannot access tracking yet
    assert tc.get(f"/api/requests/{req_id}/tracking-summary", headers=coord_h).status_code == 403

    accept = tc.post(f"/api/coordinators/{assign_id}/respond", headers=coord_h, json={"accept": True})
    assert accept.status_code == 200
    assert accept.json()["status"] == "active"

    # Active coordinator can view tracking, chat in conversation, and post progress update
    assert tc.get(f"/api/requests/{req_id}/tracking-summary", headers=coord_h).status_code == 200
    coord_msg = tc.post(f"/api/messages/{conv_id}", headers=coord_h, json={"message_text": "Coordinating gate pass at blood bank."})
    assert coord_msg.status_code == 201
    prog = tc.post(f"/api/coordinators/{req_id}/progress", headers=coord_h, json={"notes": "Blood bank counter alerted"})
    assert prog.status_code == 200

    # Requester revokes coordinator -> immediate 403 rejection on tracking, chat & progress
    revoked = tc.post(f"/api/coordinators/{assign_id}/revoke", headers=req_h)
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert tc.get(f"/api/requests/{req_id}/tracking-summary", headers=coord_h).status_code == 403
    assert tc.post(f"/api/messages/{conv_id}", headers=coord_h, json={"message_text": "After revoke"}).status_code == 403
    assert tc.post(f"/api/coordinators/{req_id}/progress", headers=coord_h, json={"notes": "Blocked"}).status_code == 403

    # 4. Cancellation notifies contacted donor and blocks further donor responses
    cancel = tc.post(
        f"/api/requests/{req_id}/cancel",
        headers=req_h,
        json={"reason": "Arranged within family"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    assert cancel.json()["cancellation_reason"] == "Arranged within family"

    don_notifs = tc.get("/api/notifications", headers=don_h).json()
    assert any(n["notification_type"] == "request_cancelled" and n["related_request_id"] == req_id for n in don_notifs)
    assert tc.post(f"/api/responses/{req_id}/respond", headers=don_h, json={"response": "declined"}).status_code == 400


def test_hospital_verification_request_management_and_expiry_notifications(env_ctx):
    tc, settings = env_ctx
    repo = get_repository(settings)

    _adm, adm_h = _register(tc, full_name="Admin User", email="admp1@example.com", phone="+919922000001", role="requester", seed="94000000001")
    with repo._connect() as conn:
        conn.execute("UPDATE profiles SET role = 'admin' WHERE email = 'admp1@example.com'")

    _hosp_u, hosp_h = _register(tc, full_name="Hospital Rep", email="hospp1@example.com", phone="+919922000002", role="hospital", seed="94000000002")
    _other_hosp, other_hosp_h = _register(tc, full_name="Other Hospital", email="otherh@example.com", phone="+919922000005", role="hospital", seed="94000000005")
    _req_u, req_h = _register(tc, full_name="Requester Two", email="reqp2@example.com", phone="+919922000003", role="requester", seed="94000000003")
    _don_u, don_h = _register(tc, full_name="Donor Two", email="donp2@example.com", phone="+919922000004", role="donor", seed="94000000004", blood_group="B+")
    tc.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})

    # Submit hospital registration & upload document
    h_reg = tc.post(
        "/api/hospitals/me",
        headers=hosp_h,
        json={
            "hospital_name": "Mathura Trauma Center",
            "registration_number": "UP-HOSP-109",
            "address": "NH-19 Mathura",
            "city": "Mathura",
            "official_phone": "+915652400999",
            "authorized_rep_name": "Dr. Meera",
            "authorized_rep_role": "Blood Bank In-Charge",
        },
    )
    assert h_reg.status_code == 200
    hosp_id = h_reg.json()["id"]
    assert h_reg.json()["verification_status"] == "pending_verification"

    up = tc.post(
        "/api/hospitals/me/documents/upload",
        headers=hosp_h,
        data={"document_type": "Licensed Blood Centre Permit"},
        files={"file": ("license.pdf", b"%PDF-1.4\n%licensed\n", "application/pdf")},
    )
    assert up.status_code == 201
    doc_id = up.json()["id"]

    # Create a blood bank entry too
    bb = tc.post(
        "/api/admin/blood-banks",
        headers=adm_h,
        json={
            "facility_name": "Mathura Trauma Blood Centre",
            "address": "NH-19 Mathura",
            "city": "Mathura",
            "phone": "+915652400999",
            "source": "Official Directory",
        },
    ).json()

    # Requester creates request for Mathura Trauma Center
    req_res = tc.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Patient Case 2",
            "blood_group": "B+",
            "units_requested": 1,
            "hospital_name": "Mathura Trauma Center",
            "hospital_location": "NH-19",
            "city": "Mathura",
            "approximate_location": "NH-19",
            "urgency": "urgent",
            "consent_given": True,
        },
    )
    assert req_res.status_code == 201
    req_id = req_res.json()["id"]

    # Unverified hospital MUST be blocked (403) from viewing/confirming/posting stock updates
    assert tc.get("/api/hospitals/requests", headers=hosp_h).status_code == 403
    assert tc.post(f"/api/hospitals/requests/{req_id}/confirm", headers=hosp_h, json={"verification_decision": "confirmed_genuine"}).status_code == 403
    assert tc.post(f"/api/blood-banks/{bb['id']}/stock-updates", headers=hosp_h, json={"blood_group": "B+", "availability_status": "confirmed_available"}).status_code == 403

    # Admin inspects uploaded license, marks under_review -> verified
    assert tc.get(f"/api/admin/hospitals/documents/{doc_id}/file", headers=adm_h).status_code == 200
    assert tc.get(f"/api/admin/hospitals/documents/{doc_id}/file", headers=req_h).status_code == 403

    rev1 = tc.patch(f"/api/admin/hospitals/{hosp_id}/review", headers=adm_h, json={"verification_status": "under_review", "notes": "Checking registry"}).json()
    assert rev1["verification_status"] == "under_review"
    rev2 = tc.patch(f"/api/admin/hospitals/{hosp_id}/review", headers=adm_h, json={"verification_status": "verified", "notes": "Approved permit"}).json()
    assert rev2["verification_status"] == "verified"

    hist = tc.get(f"/api/admin/hospitals/{hosp_id}/history", headers=adm_h).json()
    assert [h["new_status"] for h in hist] == ["pending_verification", "under_review", "verified"]

    # Verified other hospital with different name MUST be blocked from managing unrelated facility's request
    oh = tc.post(
        "/api/hospitals/me",
        headers=other_hosp_h,
        json={
            "hospital_name": "Unrelated Clinic",
            "registration_number": "UP-OTH-2",
            "address": "Vrindavan Road",
            "city": "Mathura",
            "official_phone": "+915652400888",
            "authorized_rep_name": "Dr. X",
            "authorized_rep_role": "Officer",
        },
    ).json()
    tc.patch(f"/api/admin/hospitals/{oh['id']}/review", headers=adm_h, json={"verification_status": "verified", "notes": "OK"})
    assert tc.post(f"/api/hospitals/requests/{req_id}/confirm", headers=other_hosp_h, json={"verification_decision": "confirmed_genuine"}).status_code == 403

    # Verified Mathura Trauma Center confirms request, posts stock update with honest label, and closes another expired test
    conf = tc.post(
        f"/api/hospitals/requests/{req_id}/confirm",
        headers=hosp_h,
        json={"verification_decision": "confirmed_genuine", "units_requested": 2, "notes": "Ward 2 verified"},
    )
    assert conf.status_code == 200
    assert conf.json()["hospital_verification_status"] == "confirmed_genuine"
    assert conf.json()["units_requested"] == 2

    stock = tc.post(
        f"/api/blood-banks/{bb['id']}/stock-updates",
        headers=hosp_h,
        json={"blood_group": "B+", "availability_status": "reported_awaiting_confirmation", "notes": "Caller reported 2 units"},
    )
    assert stock.status_code == 201
    assert stock.json()["availability_label"] == "Reported available — awaiting confirmation"

    # Match donor and force expiry -> donor notified about expiry!
    tc.post(f"/api/matching/{req_id}/run", headers=req_h)
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with repo._connect() as conn:
        conn.execute("UPDATE blood_requests SET expires_at = ? WHERE id = ?", (past, req_id))

    # Next read triggers expire_stale_requests()
    details = tc.get(f"/api/requests/{req_id}", headers=req_h)
    assert details.status_code == 200
    assert details.json()["status"] == "expired"
    don_notifs = tc.get("/api/notifications", headers=don_h).json()
    assert any(n["notification_type"] == "request_expired" and n["related_request_id"] == req_id for n in don_notifs)
