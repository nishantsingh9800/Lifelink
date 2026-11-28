import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jwt

from backend.app.config import Settings

PBKDF2_ITERATIONS = 310_000

_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def normalize_aadhaar(aadhaar: str) -> str:
    """Strip whitespace and hyphens from an Aadhaar input."""
    return re.sub(r"[\s-]", "", (aadhaar or "").strip())


def verhoeff_validate(digits: str) -> bool:
    """Validate an integer digit string using the Verhoeff checksum algorithm."""
    c = 0
    for idx, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[idx % 8][int(ch)]]
    return c == 0


def verhoeff_generate_digit(partial_11_digits: str) -> str:
    """Compute the 12th Verhoeff check digit for an 11-digit prefix."""
    c = 0
    for idx, ch in enumerate(reversed(partial_11_digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(idx + 1) % 8][int(ch)]]
    return str(_VERHOEFF_INV[c])


def is_valid_aadhaar(aadhaar: str) -> bool:
    """Validate 12-digit Aadhaar format (starts 2-9, non-uniform, passes Verhoeff checksum)."""
    digits = normalize_aadhaar(aadhaar)
    if len(digits) != 12 or not digits.isdigit():
        return False
    if digits[0] in ("0", "1"):
        return False
    if len(set(digits)) == 1:
        return False
    return verhoeff_validate(digits)


def compute_aadhaar_hash(aadhaar: str, settings: Settings) -> str:
    """Compute keyed HMAC-SHA256 hash so plaintext Aadhaar is never stored."""
    digits = normalize_aadhaar(aadhaar)
    return hmac.new(
        settings.app_jwt_secret.encode("utf-8"),
        digits.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def mask_aadhaar_last4(last4: str) -> str:
    return f"XXXX-XXXX-{last4}"


def create_aadhaar_dev_token(aadhaar_hash: str, settings: Settings) -> str:
    """Short-lived signed token proving pre-signup dev Aadhaar verification for this hash."""
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": "aadhaar_dev_verify",
        "aadhaar_hash": aadhaar_hash,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
    }
    return jwt.encode(payload, settings.app_jwt_secret, algorithm="HS256")


def verify_aadhaar_dev_token(token: str, expected_hash: str, settings: Settings) -> bool:
    try:
        claims = jwt.decode(token, settings.app_jwt_secret, algorithms=["HS256"])
        return (
            claims.get("purpose") == "aadhaar_dev_verify"
            and hmac.compare_digest(str(claims.get("aadhaar_hash", "")), expected_hash)
        )
    except jwt.PyJWTError:
        return False


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random 16-byte salt."""
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash."""
    try:
        algorithm, iter_str, salt_hex, hash_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False

    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)


def normalize_phone(phone: str) -> str:
    """Normalize phone numbers to a consistent E.164-like digits representation."""
    cleaned = re.sub(r"[^\d+]", "", phone.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+") and len(cleaned) == 10:
        cleaned = "+91" + cleaned
    return cleaned


def mask_display_name(full_name: str) -> str:
    """Return first name and last initial for privacy-safe public donor search."""
    parts = [part for part in full_name.strip().split() if part]
    if not parts:
        return "Verified Member"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0].upper()}."


def create_dev_access_token(profile: Dict[str, Any], settings: Settings) -> str:
    """Create a signed HS256 JWT for local development authentication only."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(profile["id"]),
        "profile_id": str(profile["id"]),
        "role": profile["role"],
        "auth_mode": "dev_only",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.app_jwt_secret, algorithm="HS256")


def decode_dev_access_token(token: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Decode and validate a local development HS256 JWT."""
    try:
        return jwt.decode(token, settings.app_jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def decode_supabase_jwt(token: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Decode a Supabase JWT if SUPABASE_JWT_SECRET is provided."""
    if not settings.supabase_jwt_secret:
        return None
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError:
        return None


_RECOVERY_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_recovery_codes(count: int = 6) -> List[str]:
    """Generate single-use Instagram-style backup recovery codes formatted as XXXX-XXXX."""
    codes: List[str] = []
    for _ in range(count):
        part1 = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4))
        part2 = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4))
        codes.append(f"{part1}-{part2}")
    return codes


def normalize_recovery_code(code: str) -> str:
    """Normalize a backup recovery code by stripping hyphens/spaces and uppercasing."""
    return re.sub(r"[^A-Za-z0-9]", "", (code or "").strip()).upper()


def hash_recovery_code(code: str, settings: Settings) -> str:
    """Compute keyed HMAC-SHA256 digest of a normalized backup recovery code."""
    normalized = normalize_recovery_code(code)
    return hmac.new(
        settings.app_jwt_secret.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
