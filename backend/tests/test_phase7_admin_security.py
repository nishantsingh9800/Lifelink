import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import get_repository, reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=str(Path(tmpdir) / "phase7.db"),
            upload_dir=str(Path(tmpdir) / "uploads"),
            google_drive_folder_url="https://drive.google.com/drive/folders/1zi9cOxgHIYbzP18VU8Af9ZGMrFK7kwC3",
            app_jwt_secret="phase7-secret-key-at-least-32-bytes-long",
            rate_limit_requests_per_minute=20,
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as tc:
            yield tc, settings
        reset_repository_cache()


def test_admin_moderation_document_review_blood_banks_analytics_and_rate_limit(client):
    tc, settings = client

    admin_reg = tc.post(
        "/api/auth/register",
        json={
            "full_name": "Admin User",
            "email": "admin7@example.com",
            "phone_number": "+919844000001",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "role_preference": "requester",
            "aadhaar_number": "70000000001" + verhoeff_generate_digit("70000000001"),
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    ).json()
    donor_reg = tc.post(
        "/api/auth/register",
        json={
            "full_name": "Donor Seven",
            "email": "donor7@example.com",
            "phone_number": "+919844000002",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "role_preference": "donor",
            "blood_group": "O+",
            "aadhaar_number": "70000000002" + verhoeff_generate_digit("70000000002"),
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    ).json()

    donor_h = {"Authorization": f"Bearer {donor_reg['access_token']}"}
    # Non-admin blocked on all admin routes
    for path in [
        "/api/admin/overview",
        "/api/admin/analytics",
        "/api/admin/donor-documents",
        "/api/admin/audit-logs",
        "/api/admin/storage-config",
    ]:
        assert tc.get(path, headers=donor_h).status_code == 403

    # Donor cannot upload unsupported file type or empty file
    bad_ext = tc.post(
        "/api/donors/me/documents/upload",
        headers=donor_h,
        data={"document_type": "Blood Donor Card"},
        files={"file": ("malware.exe", b"MZ...", "application/octet-stream")},
    )
    assert bad_ext.status_code == 400

    empty_file = tc.post(
        "/api/donors/me/documents/upload",
        headers=donor_h,
        data={"document_type": "Blood Donor Card"},
        files={"file": ("card.pdf", b"", "application/pdf")},
    )
    assert empty_file.status_code == 400

    # Donor uploads real verification document file
    doc = tc.post(
        "/api/donors/me/documents/upload",
        headers=donor_h,
        data={"document_type": "Blood Donor Card"},
        files={"file": ("donor7_card.pdf", b"%PDF-1.4 sample verification doc", "application/pdf")},
    )
    assert doc.status_code == 201
    doc_id = doc.json()["id"]
    assert len(tc.get("/api/donors/me/documents", headers=donor_h).json()) == 1

    # Non-admin cannot download stored verification document
    assert tc.get(f"/api/admin/donor-documents/{doc_id}/file", headers=donor_h).status_code == 403

    # Promote admin via CLI repo helper
    repo = get_repository(settings)
    repo.promote_to_admin_cli("admin7@example.com")
    admin_login = tc.post(
        "/api/auth/login",
        json={"identifier": "admin7@example.com", "password": "Password123!"},
    ).json()
    admin_h = {"Authorization": f"Bearer {admin_login['access_token']}"}

    # Admin can download the uploaded verification file & inspect configured Drive folder
    storage_cfg = tc.get("/api/admin/storage-config", headers=admin_h)
    assert storage_cfg.status_code == 200
    assert storage_cfg.json()["google_drive_folder_id"] == "1zi9cOxgHIYbzP18VU8Af9ZGMrFK7kwC3"

    downloaded = tc.get(f"/api/admin/donor-documents/{doc_id}/file", headers=admin_h)
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-1.4 sample verification doc"

    # Verify donor document -> updates donor_profiles.verification_status
    rev = tc.patch(
        f"/api/admin/donor-documents/{doc_id}",
        headers=admin_h,
        json={"review_status": "verified", "notes": "ID verified"},
    )
    assert rev.status_code == 200
    assert tc.get("/api/donors/me", headers=donor_h).json()["verification_status"] == "verified"

    # Blood-bank CRUD by admin
    bb = tc.post(
        "/api/admin/blood-banks",
        headers=admin_h,
        json={
            "facility_name": "Mathura Red Cross Bank",
            "address": "Civil Lines",
            "city": "Mathura",
            "phone": "+915652401111",
            "source": "Official State Registry",
        },
    )
    assert bb.status_code == 201
    bb_id = bb.json()["id"]
    assert tc.delete(f"/api/admin/blood-banks/{bb_id}", headers=admin_h).status_code == 200

    # Suspend donor account -> suspended donor blocked on protected endpoints
    susp = tc.patch(
        f"/api/admin/users/{donor_reg['user']['id']}/status",
        headers=admin_h,
        json={"account_status": "suspended", "reason": "Test suspension"},
    )
    assert susp.status_code == 200
    assert tc.get("/api/auth/me", headers=donor_h).status_code == 403

    # Analytics & audit logs
    analytics = tc.get("/api/admin/analytics", headers=admin_h)
    assert analytics.status_code == 200
    assert "requests_by_status" in analytics.json()
    assert len(tc.get("/api/admin/audit-logs", headers=admin_h).json()) >= 4

    # Security headers present
    health = tc.get("/api/health")
    assert health.headers.get("x-content-type-options") == "nosniff"
    assert health.headers.get("x-frame-options") == "DENY"

    # Rate limit triggers 429 after max_requests_per_minute
    statuses = [
        tc.post("/api/auth/login", json={"identifier": "nobody@example.com", "password": "bad"}).status_code
        for _ in range(25)
    ]
    assert 429 in statuses
