import base64
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit


def _make_shaded_face_b64(variant: int = 0, shift_x: int = 0) -> str:
    yy, xx = np.mgrid[0:240, 0:240]
    img = np.full((240, 240), 210.0, dtype=np.float32)
    cx = 120 + shift_x
    face = ((xx - cx) / 64.0) ** 2 + ((yy - 120) / 82.0) ** 2 <= 1.0
    img[face] = 175.0 - 25.0 * (((xx[face] - cx) / 64.0) ** 2)
    for ex in (cx - 28, cx + 28):
        img -= 65.0 * np.exp(-(((xx - ex) ** 2) / 180.0 + ((yy - 102) ** 2) / 70.0))
        img -= 30.0 * np.exp(-(((xx - ex) ** 2) / 30.0 + ((yy - 102) ** 2) / 20.0))
    img += 25.0 * np.exp(-(((xx - cx) ** 2) / 40.0 + ((yy - 118) ** 2) / 300.0))
    img -= 40.0 * np.exp(-(((xx - cx) ** 2) / 160.0 + ((yy - 142) ** 2) / 30.0))
    img -= 55.0 * np.exp(-(((xx - cx) ** 2) / 360.0 + ((yy - 166) ** 2) / 35.0))
    if variant == 1:
        img -= 35.0 * np.exp(-(((xx - cx) ** 2) / 800.0 + ((yy - 65) ** 2) / 150.0))
    u8 = np.clip(img, 0, 255).astype(np.uint8)
    bgr = cv2.cvtColor(u8, cv2.COLOR_GRAY2BGR)
    _, buf = cv2.imencode(".png", bgr)
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _make_blank_b64() -> str:
    img = np.full((200, 200, 3), 240, dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase9_face.db"),
            app_jwt_secret="phase9-face-secret-key-at-least-32-bytes",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc
        reset_repository_cache()


def test_face_enrollment_verification_and_acceptance_anti_impersonation(client):
    a_req = "90000000001" + verhoeff_generate_digit("90000000001")
    a_don = "90000000002" + verhoeff_generate_digit("90000000002")

    req_reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Requester Face",
            "email": "reqface@example.com",
            "phone_number": "+919866000001",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "role_preference": "requester",
            "aadhaar_number": a_req,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    ).json()
    don_reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Donor Face",
            "email": "donface@example.com",
            "phone_number": "+919866000002",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "role_preference": "donor",
            "blood_group": "B+",
            "aadhaar_number": a_don,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    ).json()

    req_h = {"Authorization": f"Bearer {req_reg['access_token']}"}
    don_h = {"Authorization": f"Bearer {don_reg['access_token']}"}

    client.patch("/api/donors/me/availability", headers=don_h, json={"availability_status": "available_now"})

    # 1. Consent required for enrollment
    no_consent = client.post(
        "/api/donors/me/face/enroll",
        headers=don_h,
        json={"image_base64": _make_shaded_face_b64(0), "consent_given": False},
    )
    assert no_consent.status_code == 422

    # 2. Blank image with no face rejected (400)
    blank = client.post(
        "/api/donors/me/face/enroll",
        headers=don_h,
        json={"image_base64": _make_blank_b64(), "consent_given": True},
    )
    assert blank.status_code == 400

    # 3. Valid face enrollment succeeds; status never exposes descriptor_json
    donor_face_0 = _make_shaded_face_b64(0)
    enrolled = client.post(
        "/api/donors/me/face/enroll",
        headers=don_h,
        json={"image_base64": donor_face_0, "consent_given": True},
    )
    assert enrolled.status_code == 200
    assert enrolled.json()["enrolled"] is True

    face_status = client.get("/api/donors/me/face", headers=don_h)
    assert face_status.status_code == 200
    assert "descriptor" not in face_status.text

    # 4. Same face (with slight horizontal shift) verifies True; different person fails False
    same_verify = client.post(
        "/api/donors/me/face/verify",
        headers=don_h,
        json={"image_base64": _make_shaded_face_b64(0, shift_x=2)},
    )
    assert same_verify.status_code == 200
    assert same_verify.json()["verified"] is True

    impostor_face = _make_shaded_face_b64(1)
    diff_verify = client.post(
        "/api/donors/me/face/verify",
        headers=don_h,
        json={"image_base64": impostor_face},
    )
    assert diff_verify.status_code == 200
    assert diff_verify.json()["verified"] is False

    # 5. Request acceptance enforces live face verification when donor has enrolled face
    blood_req = client.post(
        "/api/requests",
        headers=req_h,
        json={
            "patient_reference_name": "Patient Face",
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
    req_id = blood_req["id"]
    client.post(f"/api/matching/{req_id}/run", headers=req_h)

    # Without live face photo -> 403
    no_face_accept = client.post(
        f"/api/responses/{req_id}/respond",
        headers=don_h,
        json={"response": "accepted"},
    )
    assert no_face_accept.status_code == 403

    # Impostor face -> 403
    impostor_accept = client.post(
        f"/api/responses/{req_id}/respond",
        headers=don_h,
        json={"response": "accepted", "face_image_base64": impostor_face},
    )
    assert impostor_accept.status_code == 403

    # Registered donor's matching face -> 200 accepted
    valid_accept = client.post(
        f"/api/responses/{req_id}/respond",
        headers=don_h,
        json={"response": "accepted", "face_image_base64": donor_face_0},
    )
    assert valid_accept.status_code == 200
    assert valid_accept.json()["response"] == "accepted"
