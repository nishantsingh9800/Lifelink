import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase5.db"),
            app_jwt_secret="phase5-secret-key-at-least-32-bytes-long",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc
        reset_repository_cache()


def test_rule_based_assistant_flows_tracking_and_safety_refusal(client):
    reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Meera Joshi",
            "email": "meera@example.com",
            "phone_number": "+919822000001",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "role_preference": "requester",
            "aadhaar_number": "50000000001" + verhoeff_generate_digit("50000000001"),
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    ).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # 1. Medical safety refusal
    med = client.post(
        "/api/chatbot/message",
        headers=headers,
        json={"message": "Can you diagnose my low hemoglobin and tell me if I am medically fit?"},
    ).json()
    assert med["intent"] == "medical_safety_refusal"
    assert "not a medical professional" in med["reply"].lower()

    # 2. Emergency guidance never suggests waiting
    emg = client.post(
        "/api/chatbot/message",
        headers=headers,
        json={"message": "This is an immediate emergency help"},
    ).json()
    assert emg["intent"] == "emergency_guidance"
    assert "treating hospital" in emg["reply"].lower()

    # 3. Guided request creation prepares pre-fill URL without auto-submitting
    draft = client.post(
        "/api/chatbot/message",
        headers=headers,
        json={"message": "I need B+ blood in Mathura urgent"},
    ).json()
    assert draft["intent"] == "create_request_guidance"
    assert "blood_group=B%2B" in draft["suggested_actions"][0]["url"]
    assert client.get("/api/requests", headers=headers).json() == []

    # 4. Real request tracking reflects actual DB records
    req = client.post(
        "/api/requests",
        headers=headers,
        json={
            "patient_reference_name": "Patient M",
            "blood_group": "B+",
            "units_requested": 1,
            "hospital_name": "District Hospital",
            "hospital_location": "Dampier Nagar",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "urgency": "urgent",
            "consent_given": True,
        },
    ).json()

    track = client.post(
        "/api/chatbot/message",
        headers=headers,
        json={"session_id": draft["session_id"], "message": "Track my request status"},
    ).json()
    assert track["intent"] == "request_tracking"
    assert "District Hospital" in track["reply"]
    assert "0 potential donor(s) notified" in track["reply"]

    # History persisted
    hist = client.get("/api/chatbot/history", headers=headers).json()
    assert len(hist["messages"]) == 8
