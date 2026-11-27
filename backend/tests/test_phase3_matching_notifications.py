import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit

_AADHAAR_SEQ = 2000


def _create_user(tc: TestClient, email: str, phone: str, role: str, city: str = "Mathura", blood_group: str | None = None):
    global _AADHAAR_SEQ
    _AADHAAR_SEQ += 1
    prefix = f"3{_AADHAAR_SEQ:010d}"
    payload = {
        "full_name": f"User {email.split('@')[0]}",
        "email": email,
        "phone_number": phone,
        "password": "Password123!",
        "city": city,
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
    return res.json()["access_token"], res.json()["user"]


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase3.db"),
            app_jwt_secret="phase3-secret-key-at-least-32-bytes-long",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc
        reset_repository_cache()


def test_matching_prioritization_notifications_accept_decline_and_escalation(client):
    req_token, _ = _create_user(client, "req3@example.com", "+919800221100", "requester", "Mathura")
    req_h = {"Authorization": f"Bearer {req_token}"}

    # Exact B+ donor available_now in Mathura
    d1_tok, _ = _create_user(client, "d1@example.com", "+919800221101", "donor", "Mathura", "B+")
    client.patch("/api/donors/me/availability", headers={"Authorization": f"Bearer {d1_tok}"}, json={"availability_status": "available_now"})

    # Compatible O+ donor available_today in Mathura
    d2_tok, _ = _create_user(client, "d2@example.com", "+919800221102", "donor", "Mathura", "O+")
    client.patch("/api/donors/me/availability", headers={"Authorization": f"Bearer {d2_tok}"}, json={"availability_status": "available_today"})

    # Opted-out B+ donor (must be excluded)
    d3_tok, _ = _create_user(client, "d3@example.com", "+919800221103", "donor", "Mathura", "B+")
    client.patch(
        "/api/donors/me/availability",
        headers={"Authorization": f"Bearer {d3_tok}"},
        json={"availability_status": "available_now", "emergency_notifications_enabled": False},
    )

    # Wider city B+ donor in Agra (excluded in Stage 1, included in Stage 3)
    d4_tok, _ = _create_user(client, "d4@example.com", "+919800221104", "donor", "Agra", "B+")
    client.patch("/api/donors/me/availability", headers={"Authorization": f"Bearer {d4_tok}"}, json={"availability_status": "available_now"})

    # Create B+ request in Mathura
    req = client.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Patient B+",
            "blood_group": "B+",
            "units_requested": 1,
            "hospital_name": "Mathura Hospital",
            "hospital_location": "NH-19",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "urgency": "emergency",
            "consent_given": True,
        },
    ).json()
    req_id = req["id"]

    # Run Stage 1 matching
    match_res = client.post(f"/api/matching/{req_id}/run", headers=req_h)
    assert match_res.status_code == 200
    mdata = match_res.json()
    assert mdata["newly_notified_count"] == 2
    assert mdata["request_status"] == "donors_notified"
    # Exact B+ must outrank compatible O+
    assert mdata["candidates"][0]["blood_group"] == "B+"
    assert mdata["candidates"][1]["blood_group"] == "O+"

    # Re-running matching does NOT send duplicate notifications
    rerun = client.post(f"/api/matching/{req_id}/run", headers=req_h)
    assert rerun.json()["newly_notified_count"] == 0

    # Opted-out donor has zero notifications
    assert client.get("/api/notifications", headers={"Authorization": f"Bearer {d3_tok}"}).json() == []

    # Donor 2 declines
    d2_h = {"Authorization": f"Bearer {d2_tok}"}
    inc2 = client.get("/api/responses/incoming", headers=d2_h).json()
    assert len(inc2) == 1
    dec = client.post(f"/api/responses/{req_id}/respond", headers=d2_h, json={"response": "declined"})
    assert dec.status_code == 200
    assert dec.json()["response"] == "declined"

    # Donor 1 accepts ("I CAN HELP") -> connection_in_progress (NEVER fulfilled!) + conversation created
    d1_h = {"Authorization": f"Bearer {d1_tok}"}
    acc = client.post(f"/api/responses/{req_id}/respond", headers=d1_h, json={"response": "accepted"})
    assert acc.status_code == 200
    assert acc.json()["conversation_id"] is not None

    req_after = client.get(f"/api/requests/{req_id}", headers=req_h).json()
    assert req_after["status"] == "connection_in_progress"
    assert req_after["status"] != "fulfilled"

    # Escalate Stage 2 -> Stage 3 (reaches Agra donor d4)
    client.post(f"/api/matching/{req_id}/escalate", headers=req_h)
    esc3 = client.post(f"/api/matching/{req_id}/escalate", headers=req_h).json()
    assert esc3["escalation_stage"] == 3
    assert esc3["newly_notified_count"] == 1

    # Stage 4 -> Blood-Bank Assistance, Stage 5 -> Hospital-Coordinated Wider Search
    esc4 = client.post(f"/api/matching/{req_id}/escalate", headers=req_h).json()
    assert esc4["escalation_stage"] == 4
    assert esc4["request_status"] == "blood_bank_assistance"

    esc5 = client.post(f"/api/matching/{req_id}/escalate", headers=req_h).json()
    assert esc5["escalation_stage"] == 5
    assert esc5["request_status"] == "escalation_in_progress"

    # Notifications mark read works
    notifs = client.get("/api/notifications", headers=req_h).json()
    assert len(notifs) >= 3
    first_id = notifs[0]["id"]
    marked = client.post(f"/api/notifications/{first_id}/read", headers=req_h)
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None


def test_no_candidates_escalates_to_blood_bank_and_cancelled_blocks_matching(client):
    req_token, _ = _create_user(client, "lonely@example.com", "+919800221199", "requester", "Mathura")
    req_h = {"Authorization": f"Bearer {req_token}"}

    req = client.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Patient AB-",
            "blood_group": "AB-",
            "units_requested": 1,
            "hospital_name": "Mathura Hospital",
            "hospital_location": "NH-19",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "urgency": "emergency",
            "consent_given": True,
        },
    ).json()

    res = client.post(f"/api/matching/{req['id']}/run", headers=req_h).json()
    assert res["newly_notified_count"] == 0
    assert res["request_status"] == "blood_bank_assistance"
    assert res["escalation_stage"] == 4

    client.post(f"/api/requests/{req['id']}/cancel", headers=req_h, json={"reason": "Closed"})
    blocked = client.post(f"/api/matching/{req['id']}/run", headers=req_h)
    assert blocked.status_code == 400
