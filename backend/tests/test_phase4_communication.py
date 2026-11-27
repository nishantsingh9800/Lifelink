import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit

_AADHAAR_SEQ = 3000


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase4.db"),
            app_jwt_secret="phase4-secret-key-at-least-32-bytes-long",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc
        reset_repository_cache()


def _reg(tc: TestClient, email: str, phone: str, role: str, blood_group: str | None = None):
    global _AADHAAR_SEQ
    _AADHAAR_SEQ += 1
    prefix = f"4{_AADHAAR_SEQ:010d}"
    payload = {
        "full_name": f"User {email.split('@')[0]}",
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
    return res.json()["access_token"], res.json()["user"]


def test_private_chat_isolation_mutual_consent_and_blocking(client):
    req_tok, _ = _reg(client, "req4@example.com", "+919811000001", "requester")
    don_tok, don_user = _reg(client, "don4@example.com", "+919811000002", "donor", "B+")
    spy_tok, _ = _reg(client, "spy4@example.com", "+919811000003", "requester")

    req_h = {"Authorization": f"Bearer {req_tok}"}
    don_h = {"Authorization": f"Bearer {don_tok}"}
    spy_h = {"Authorization": f"Bearer {spy_tok}"}

    client.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})
    req = client.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Patient Chat",
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
    req_id = req["id"]

    client.post(f"/api/matching/{req_id}/run", headers=req_h)
    acc = client.post(f"/api/responses/{req_id}/respond", headers=don_h, json={"response": "accepted"}).json()
    conv_id = acc["conversation_id"]
    assert conv_id is not None

    # Spy cannot guess conversation ID or read/send messages or view contact sharing
    assert client.get(f"/api/conversations/{conv_id}", headers=spy_h).status_code == 403
    assert client.get(f"/api/messages/{conv_id}", headers=spy_h).status_code == 403
    assert client.post(f"/api/messages/{conv_id}", headers=spy_h, json={"message_text": "Snooping"}).status_code == 403
    assert client.get(f"/api/contact-sharing/{req_id}?donor_user_id={don_user['id']}", headers=spy_h).status_code == 403

    # Participants exchange messages cleanly
    sent = client.post(f"/api/messages/{conv_id}", headers=req_h, json={"message_text": "Can you reach Mathura Care?"})
    assert sent.status_code == 201
    msgs = client.get(f"/api/messages/{conv_id}", headers=don_h).json()
    assert len(msgs) == 1
    assert msgs[0]["is_mine"] is False
    assert client.post(f"/api/messages/{conv_id}/read", headers=don_h).json()["marked_read"] == 1

    # Single-sided consent MUST keep phone hidden
    one_side = client.post(
        f"/api/contact-sharing/{req_id}/consent?donor_user_id={don_user['id']}", headers=req_h
    ).json()
    assert one_side["requester_consent"] is True
    assert one_side["donor_consent"] is False
    assert one_side["status"] == "pending"
    assert one_side["counterpart_phone_number"] is None

    # Both consent -> phone revealed to participants
    both = client.post(f"/api/contact-sharing/{req_id}/consent", headers=don_h).json()
    assert both["status"] == "both_consented"
    assert both["counterpart_phone_number"] == "+919811000001"
    req_view = client.get(f"/api/contact-sharing/{req_id}?donor_user_id={don_user['id']}", headers=req_h).json()
    assert req_view["counterpart_phone_number"] == "+919811000002"

    # Withdraw consent -> phone hidden again
    withdrawn = client.post(f"/api/contact-sharing/{req_id}/withdraw", headers=don_h).json()
    assert withdrawn["status"] == "withdrawn"
    assert withdrawn["counterpart_phone_number"] is None

    # Report & Block user closes conversation
    rep = client.post(
        "/api/reports",
        headers=req_h,
        json={"reported_user_id": don_user["id"], "request_id": req_id, "reason": "Suspicious behaviour"},
    )
    assert rep.status_code == 201
    blk = client.post(
        "/api/reports/block",
        headers=req_h,
        json={"blocked_user_id": don_user["id"], "conversation_id": conv_id},
    )
    assert blk.status_code == 201
    assert client.post(f"/api/messages/{conv_id}", headers=don_h, json={"message_text": "Hello?"}).status_code == 400
