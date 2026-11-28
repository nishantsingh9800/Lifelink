import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import get_repository, reset_repository_cache
from backend.app.main import create_app
from backend.app.utils.security import verhoeff_generate_digit


def _aadhaar(prefix11: str) -> str:
    return prefix11 + verhoeff_generate_digit(prefix11)


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = str(Path(tmpdir) / "test_lifelink.db")
        settings = Settings(
            dev_auth_mode=True,
            dev_db_path=db_file,
            app_jwt_secret="test-secret-key-for-lifelink-phase-1",
            supabase_url="",
            supabase_anon_key="",
            supabase_service_role_key="",
        )
        reset_repository_cache()
        app = create_app(settings)
        with TestClient(app) as test_client:
            yield test_client, settings
        reset_repository_cache()


def test_health_and_public_config_never_exposes_secrets(client):
    test_client, _ = client
    health = test_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["storage_mode"] == "local_dev_sqlite"

    cfg = test_client.get("/api/config/public")
    assert cfg.status_code == 200
    body = cfg.json()
    assert "supabase_service_role_key" not in body
    assert "app_jwt_secret" not in body
    assert body["dev_auth_mode"] is True


def test_frontend_pages_and_internal_links_are_valid(client):
    import re
    from backend.app.config import PROJECT_ROOT

    test_client, _ = client
    frontend_root = PROJECT_ROOT / "frontend"

    html_files = list(frontend_root.rglob("*.html"))
    assert len(html_files) >= 11

    for html_file in html_files:
        rel_url = "/" + html_file.relative_to(frontend_root).as_posix()
        res = test_client.get(rel_url)
        assert res.status_code == 200, f"Failed serving {rel_url}"

        content = html_file.read_text(encoding="utf-8")
        for _attr, url in re.findall(r'(href|src)="(/[^"?#]+)"', content):
            if url == "/docs":
                continue
            target = frontend_root / url.lstrip("/")
            assert target.exists(), f"Broken link {url} in {rel_url}"

    assert test_client.get("/").status_code == 200
    assert test_client.get("/favicon.ico").status_code == 200
    assert test_client.get("/css/styles.css").status_code == 200


def test_registration_login_and_security_controls(client):
    test_client, settings = client
    a1 = _aadhaar("23456789012")
    a2 = _aadhaar("34567890123")
    a3 = _aadhaar("45678901234")

    # 0. Registration works without Aadhaar (not required at signup/login); if Aadhaar IS provided, invalid checksum still fails 422
    no_aadhaar_ok = test_client.post(
        "/api/auth/register",
        json={
            "full_name": "Quick User",
            "email": "noaadhaar@example.com",
            "phone_number": "+919800000010",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "NH-19",
            "role_preference": "requester",
            "terms_accepted": True,
        },
    )
    assert no_aadhaar_ok.status_code == 201
    assert no_aadhaar_ok.json()["user"]["aadhaar_verified"] is False

    bad_checksum = test_client.post(
        "/api/auth/register",
        json={
            "full_name": "Bad Aadhaar",
            "email": "badaadhaar@example.com",
            "phone_number": "+919800000011",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "NH-19",
            "role_preference": "requester",
            "aadhaar_number": a1[:-1] + str((int(a1[-1]) + 1) % 10),
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    )
    assert bad_checksum.status_code == 422

    # 1. Cannot self-register as admin
    admin_attempt = test_client.post(
        "/api/auth/register",
        json={
            "full_name": "Evil User",
            "email": "evil@example.com",
            "phone_number": "+919800000001",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "NH-19",
            "role_preference": "admin",
            "aadhaar_number": a1,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    )
    assert admin_attempt.status_code == 422

    # 2. Must accept terms
    no_terms = test_client.post(
        "/api/auth/register",
        json={
            "full_name": "Requester One",
            "email": "req1@example.com",
            "phone_number": "+919800000002",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Chaumuha",
            "role_preference": "requester",
            "aadhaar_number": a1,
            "aadhaar_consent": True,
            "terms_accepted": False,
        },
    )
    assert no_terms.status_code == 422

    # 3. Pre-signup Aadhaar authentication + valid requester registration (never returns plaintext Aadhaar)
    verify_init = test_client.post(
        "/api/auth/aadhaar/verify-init",
        json={"aadhaar_number": a1, "aadhaar_consent": True},
    )
    assert verify_init.status_code == 200
    aadhaar_tok = verify_init.json()["aadhaar_verification_token"]

    reg_req = test_client.post(
        "/api/auth/register",
        json={
            "full_name": "Aarav Verma",
            "email": "aarav@example.com",
            "phone_number": "+919800000003",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Krishna Nagar",
            "role_preference": "requester",
            "aadhaar_number": a1,
            "aadhaar_consent": True,
            "aadhaar_verification_token": aadhaar_tok,
            "terms_accepted": True,
        },
    )
    assert reg_req.status_code == 201
    req_data = reg_req.json()
    req_token = req_data["access_token"]
    assert req_data["user"]["role"] == "requester"
    assert req_data["user"]["phone_verified"] is False
    assert req_data["user"]["aadhaar_verified"] is True
    assert req_data["user"]["aadhaar_masked"] == f"XXXX-XXXX-{a1[-4:]}"
    assert a1 not in reg_req.text

    # 3b. Duplicate Aadhaar number rejected even with new email & phone
    dup_aadhaar = test_client.post(
        "/api/auth/register",
        json={
            "full_name": "Duplicate Aadhaar",
            "email": "dupaadhaar@example.com",
            "phone_number": "+919800000099",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Krishna Nagar",
            "role_preference": "requester",
            "aadhaar_number": a1,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    )
    assert dup_aadhaar.status_code == 409

    # 4. Duplicate email rejected
    dup_req = test_client.post(
        "/api/auth/register",
        json={
            "full_name": "Aarav Clone",
            "email": "aarav@example.com",
            "phone_number": "+919800000009",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Krishna Nagar",
            "role_preference": "requester",
            "aadhaar_number": a3,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    )
    assert dup_req.status_code == 409

    # 5. Valid donor registration requires blood_group
    donor_missing_bg = test_client.post(
        "/api/auth/register",
        json={
            "full_name": "Priya Singh",
            "email": "priya@example.com",
            "phone_number": "+919800000004",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "role_preference": "donor",
            "aadhaar_number": a2,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    )
    assert donor_missing_bg.status_code == 422

    donor_reg = test_client.post(
        "/api/auth/register",
        json={
            "full_name": "Priya Singh",
            "email": "priya@example.com",
            "phone_number": "+919800000004",
            "password": "Password123!",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "role_preference": "donor",
            "blood_group": "B+",
            "aadhaar_number": a2,
            "aadhaar_consent": True,
            "terms_accepted": True,
        },
    )
    assert donor_reg.status_code == 201
    assert donor_reg.json()["user"]["role"] == "donor"

    # 6. Unauthenticated /me fails
    assert test_client.get("/api/auth/me").status_code == 401

    # 7. Authenticated /me succeeds and dev-verify-phone works
    headers = {"Authorization": f"Bearer {req_token}"}
    me = test_client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "aarav@example.com"

    verified = test_client.post("/api/auth/dev-verify-phone", headers=headers)
    assert verified.status_code == 200
    assert verified.json()["phone_verified"] is True

    # 8. Attempted role escalation via PATCH /api/users/me does NOT elevate role
    patch = test_client.patch(
        "/api/users/me",
        headers=headers,
        json={"full_name": "Aarav Updated", "role": "admin"},
    )
    assert patch.status_code == 200
    assert patch.json()["full_name"] == "Aarav Updated"
    assert patch.json()["role"] == "requester"

    # 9. Ordinary user cannot access admin endpoints
    assert test_client.get("/api/admin/overview", headers=headers).status_code == 403
    assert test_client.get("/api/admin/users", headers=headers).status_code == 403

    # 10. Public search returns empty when donor is unavailable, and blood banks empty initially
    assert test_client.get("/api/public/donors").json() == []
    assert test_client.get("/api/public/blood-banks").json() == []

    # 11. Promote via backend CLI/repository helper and verify admin endpoints work
    repo = get_repository(settings)
    promoted = repo.promote_to_admin_cli("aarav@example.com")
    assert promoted["role"] == "admin"

    # Re-login to obtain admin-scoped session (also test phone login & invalid password)
    bad_login = test_client.post(
        "/api/auth/login",
        json={"identifier": "aarav@example.com", "password": "WrongPassword!"},
    )
    assert bad_login.status_code == 401

    login_res = test_client.post(
        "/api/auth/login",
        json={"identifier": "+919800000003", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    admin_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
    overview = test_client.get("/api/admin/overview", headers=admin_headers)
    assert overview.status_code == 200
    assert overview.json()["total_users"] == 3
    assert overview.json()["total_donors"] == 1
    assert overview.json()["verified_donors"] == 0

    users_list = test_client.get("/api/admin/users?role=donor", headers=admin_headers)
    assert users_list.status_code == 200
    assert len(users_list.json()) == 1
    assert users_list.json()[0]["email"] == "priya@example.com"


def test_unconfigured_supabase_with_dev_mode_disabled_returns_503():
    settings = Settings(
        dev_auth_mode=False,
        supabase_url="",
        supabase_anon_key="",
        supabase_service_role_key="",
    )
    reset_repository_cache()
    app = create_app(settings)
    with TestClient(app) as tc:
        res = tc.get("/api/health")
        assert res.status_code == 503
    reset_repository_cache()


def test_forgot_password_instagram_style_recovery_codes(test_client_and_settings):
    test_client, _ = test_client_and_settings
    reg = test_client.post(
        "/api/auth/register",
        json={
            "full_name": "Recovery User",
            "email": "recoverme@example.com",
            "phone_number": "+919811223344",
            "password": "OldPassword123!",
            "city": "Mathura",
            "approximate_location": "Dampier Nagar",
            "role_preference": "requester",
            "terms_accepted": True,
        },
    )
    assert reg.status_code == 201
    codes = reg.json().get("recovery_codes") or []
    assert len(codes) == 6
    assert "-" in codes[0]
    tok = reg.json()["access_token"]
    hdrs = {"Authorization": f"Bearer {tok}"}

    # Preferences update must preserve recovery codes
    pref_res = test_client.patch(
        "/api/users/me/preferences",
        headers=hdrs,
        json={"preferred_language": "hi", "text_size": "large"},
    )
    assert pref_res.status_code == 200
    status_res = test_client.get("/api/auth/recovery-codes", headers=hdrs)
    assert status_res.status_code == 200
    assert status_res.json()["remaining_count"] == 6

    # Recover using first backup code (even ignoring hyphen/case) and log in immediately
    first_code_clean = codes[0].replace("-", "").lower()
    rec = test_client.post(
        "/api/auth/recover-with-code",
        json={
            "identifier": "recoverme@example.com",
            "recovery_code": first_code_clean,
            "new_password": "NewStrongPassword!99",
        },
    )
    assert rec.status_code == 200
    assert rec.json()["access_token"]
    assert "5 backup code(s) remaining" in rec.json()["message"]

    # Reusing the same single-use code must fail (401)
    reuse = test_client.post(
        "/api/auth/recover-with-code",
        json={
            "identifier": "+919811223344",
            "recovery_code": codes[0],
            "new_password": "AnotherPassword!99",
        },
    )
    assert reuse.status_code == 401

    # Old password no longer works; new password works
    assert (
        test_client.post(
            "/api/auth/login",
            json={"identifier": "recoverme@example.com", "password": "OldPassword123!"},
        ).status_code
        == 401
    )
    assert (
        test_client.post(
            "/api/auth/login",
            json={"identifier": "+919811223344", "password": "NewStrongPassword!99"},
        ).status_code
        == 200
    )

    # Regenerate fresh 6 codes invalidates old unused codes (e.g., codes[1])
    regen = test_client.post("/api/auth/recovery-codes/regenerate", headers=hdrs)
    assert regen.status_code == 200
    new_codes = regen.json()["recovery_codes"]
    assert len(new_codes) == 6
    assert (
        test_client.post(
            "/api/auth/recover-with-code",
            json={
                "identifier": "recoverme@example.com",
                "recovery_code": codes[1],
                "new_password": "ShouldFailPassword!1",
            },
        ).status_code
        == 401
    )
