import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import get_repository, reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit

_AADHAAR_SEQ = 8000


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "e2e_acceptance.db"),
            app_jwt_secret="e2e-acceptance-secret-key-at-least-32-bytes",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc, settings
        reset_repository_cache()


def _reg_and_verify(tc: TestClient, name: str, email: str, phone: str, role: str, blood_group: str | None = None):
    global _AADHAAR_SEQ
    _AADHAAR_SEQ += 1
    prefix = f"8{_AADHAAR_SEQ:010d}"
    payload = {
        "full_name": name,
        "email": email,
        "phone_number": phone,
        "password": "Password123!",
        "city": "Mathura",
        "approximate_location": "Chaumuha",
        "role_preference": role,
        "aadhaar_number": prefix + verhoeff_generate_digit(prefix),
        "aadhaar_consent": True,
        "terms_accepted": True,
    }
    if blood_group:
        payload["blood_group"] = blood_group
    res = tc.post("/api/auth/register", json=payload)
    assert res.status_code == 201
    tok = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    ver = tc.post("/api/auth/dev-verify-phone", headers=headers)
    assert ver.status_code == 200
    assert ver.json()["phone_verified"] is True
    return headers, res.json()["user"]


def test_full_b_positive_emergency_end_to_end_scenario(client):
    """
    Acceptance Test matching Master Prompt Section 21 (Steps 1-22):
    Requester needs B+ blood -> verifies phone -> creates request -> matching runs ->
    donors notified -> accept/decline -> private chat -> chatbot tracks live status ->
    escalation to blood bank & hospital fallback -> genuine outcome -> history verified.
    """
    tc, settings = client

    # 1-2. Requester, Donors, and Admin register & verify
    req_h, _ = _reg_and_verify(tc, "Rohan Sharma", "rohan@example.com", "+919855000001", "requester")
    don1_h, _ = _reg_and_verify(tc, "Ananya Verma", "ananya@example.com", "+919855000002", "donor", "B+")
    don2_h, _ = _reg_and_verify(tc, "Vikram Rao", "vikram@example.com", "+919855000003", "donor", "B+")
    _, _ = _reg_and_verify(tc, "AdminOps", "adminops@example.com", "+919855000004", "requester")

    repo = get_repository(settings)
    repo.promote_to_admin_cli("adminops@example.com")
    admin_tok = tc.post("/api/auth/login", json={"identifier": "adminops@example.com", "password": "Password123!"}).json()["access_token"]
    admin_h = {"Authorization": f"Bearer {admin_tok}"}

    # Admin adds a verified blood bank facility
    bank = tc.post(
        "/api/admin/blood-banks",
        headers=admin_h,
        json={
            "facility_name": "K.D. Medical College Blood Bank",
            "address": "NH-19 Akbarpur",
            "city": "Mathura",
            "phone": "+915652500000",
            "source": "Verified Directory Entry",
        },
    ).json()

    # Donors mark availability
    tc.patch("/api/donors/me/availability", headers=don1_h, json={"availability_status": "available_now"})
    tc.patch("/api/donors/me/availability", headers=don2_h, json={"availability_status": "available_today"})

    # 3-5. Requester creates B+ emergency request
    created = tc.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Patient R. Sharma",
            "blood_group": "B+",
            "units_requested": 2,
            "hospital_name": "K.D. Hospital",
            "hospital_location": "NH-19 Akbarpur",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "urgency": "emergency",
            "consent_given": True,
        },
    )
    assert created.status_code == 201
    req_id = created.json()["id"]

    # 6-9. Matching identifies, prioritizes, and notifies both donors
    match = tc.post(f"/api/matching/{req_id}/run", headers=req_h).json()
    assert match["newly_notified_count"] == 2
    assert match["request_status"] == "donors_notified"

    # 10-12. Donor 2 declines; Donor 1 accepts ("I CAN HELP") -> opens private chat, NOT fulfilled
    assert tc.post(f"/api/responses/{req_id}/respond", headers=don2_h, json={"response": "declined"}).status_code == 200
    acc = tc.post(f"/api/responses/{req_id}/respond", headers=don1_h, json={"response": "accepted"}).json()
    conv_id = acc["conversation_id"]
    assert conv_id is not None
    assert tc.get(f"/api/requests/{req_id}", headers=req_h).json()["status"] == "connection_in_progress"

    # 13. Both communicate privately without automatic phone sharing
    assert tc.post(f"/api/messages/{conv_id}", headers=req_h, json={"message_text": "Thank you! Are you near Akbarpur?"}).status_code == 201
    assert tc.post(f"/api/messages/{conv_id}", headers=don1_h, json={"message_text": "Yes, reaching the blood bank desk in 20 mins."}).status_code == 201
    cs = tc.get(f"/api/contact-sharing/{req_id}", headers=don1_h).json()
    assert cs["counterpart_phone_number"] is None

    # 14. LifeLink Assistant fetches real status from DB
    bot = tc.post("/api/chatbot/message", headers=req_h, json={"message": "Track my request status"}).json()
    assert "2 potential donor(s) notified" in bot["reply"]
    assert "1 accepted, 1 declined" in bot["reply"]

    # 15-18. Progressive escalation -> Blood-Bank Assistance -> Hospital Fallback -> Unresolved
    tc.post(f"/api/matching/{req_id}/escalate", headers=req_h)
    tc.post(f"/api/matching/{req_id}/escalate", headers=req_h)
    esc4 = tc.post(f"/api/matching/{req_id}/escalate", headers=req_h).json()
    assert esc4["request_status"] == "blood_bank_assistance"
    esc5 = tc.post(f"/api/matching/{req_id}/escalate", headers=req_h).json()
    assert esc5["request_status"] == "escalation_in_progress"

    # Requester logs blood-bank contact and marks unresolved while confirming
    tc.post(
        f"/api/blood-banks/{bank['id']}/contact-attempt",
        headers=req_h,
        json={"request_id": req_id, "outcome": "confirmed_available", "notes": "Crossmatch underway"},
    )
    assert tc.post(f"/api/requests/{req_id}/outcome", headers=req_h, json={"outcome": "unresolved"}).json()["status"] == "unresolved"

    # 19-22. Blood arranged through hospital blood bank -> fulfilled + history + notifications recorded
    final_res = tc.post(
        f"/api/requests/{req_id}/outcome",
        headers=req_h,
        json={"outcome": "fulfilled", "notes": "2 units arranged via K.D. Medical College Blood Bank"},
    )
    assert final_res.status_code == 200
    assert final_res.json()["status"] == "fulfilled"

    history = tc.get(f"/api/requests/{req_id}/history", headers=req_h).json()
    statuses = [h["new_status"] for h in history]
    assert statuses[0] == "created"
    assert "connection_in_progress" in statuses
    assert "blood_bank_assistance" in statuses
    assert "unresolved" in statuses
    assert statuses[-1] == "fulfilled"

    # Donor received final status update notification
    don1_notifs = tc.get("/api/notifications", headers=don1_h).json()
    assert any("Fulfilled" in n["title"] for n in don1_notifs)
