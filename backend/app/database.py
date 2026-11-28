import hmac
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from backend.app.addons_phase1_db import (
    PHASE1_AVAILABILITY_LABELS,
    Phase1SQLiteMixin,
    Phase1SupabaseMixin,
)
from backend.app.addons_phase2_db import Phase2SQLiteMixin, Phase2SupabaseMixin
from backend.app.addons_phase3_db import Phase3SQLiteMixin, Phase3SupabaseMixin
from backend.app.config import Settings, get_settings
from backend.app.utils.security import (
    hash_password,
    mask_display_name,
    normalize_phone,
    verify_password,
)


class DatabaseUnavailableError(Exception):
    """Raised when the configured database backend cannot be reached."""


class ConflictError(Exception):
    """Raised on unique constraint violations (duplicate email/phone)."""


class AuthenticationError(Exception):
    """Raised on invalid credentials or suspended account."""


AVAILABILITY_LABELS = PHASE1_AVAILABILITY_LABELS


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_freeze_fields(
    last_donation_date: Optional[str], cooldown_days: int = 90
) -> Tuple[Optional[str], Optional[str]]:
    """Compute 3-month (90-day) post-donation freeze date if the donation is within the cooldown window."""
    if not last_donation_date:
        return None, None
    try:
        donated_on = date.fromisoformat(str(last_donation_date)[:10])
    except ValueError:
        return None, None
    freeze_until = donated_on + timedelta(days=cooldown_days)
    if freeze_until > datetime.now().date():
        return freeze_until.isoformat(), "3-month (90-day) post-donation recovery freeze"
    return None, None


class LocalDevSQLiteRepository(Phase1SQLiteMixin, Phase2SQLiteMixin, Phase3SQLiteMixin):
    """Real relational SQLite repository used strictly when SUPABASE_URL is unset and DEV_AUTH_MODE=true."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    auth_user_id TEXT UNIQUE,
                    full_name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    phone_number TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'requester' CHECK (role IN ('requester', 'donor', 'admin')),
                    city TEXT NOT NULL,
                    approximate_location TEXT NOT NULL,
                    date_of_birth TEXT,
                    account_status TEXT NOT NULL DEFAULT 'active' CHECK (account_status IN ('active', 'suspended', 'deleted')),
                    phone_verified INTEGER NOT NULL DEFAULT 0,
                    aadhaar_last4 TEXT NOT NULL DEFAULT '0000',
                    aadhaar_hash TEXT UNIQUE,
                    aadhaar_verified INTEGER NOT NULL DEFAULT 0,
                    aadhaar_consent_at TEXT,
                    terms_accepted_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS donor_profiles (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
                    blood_group TEXT NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
                    availability_status TEXT NOT NULL DEFAULT 'unavailable'
                        CHECK (availability_status IN ('available_now', 'available_today', 'unavailable', 'emergency_only')),
                    last_donation_date TEXT,
                    donor_frozen_until TEXT,
                    donor_freeze_reason TEXT,
                    preferred_contact_method TEXT NOT NULL DEFAULT 'in_app_chat',
                    verification_status TEXT NOT NULL DEFAULT 'not_submitted'
                        CHECK (verification_status IN ('not_submitted', 'pending_review', 'verified', 'rejected')),
                    emergency_notifications_enabled INTEGER NOT NULL DEFAULT 1,
                    profile_completed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS blood_requests (
                    id TEXT PRIMARY KEY,
                    requester_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    patient_reference_name TEXT NOT NULL,
                    blood_group TEXT NOT NULL,
                    units_requested INTEGER NOT NULL DEFAULT 1,
                    hospital_name TEXT NOT NULL,
                    hospital_location TEXT NOT NULL,
                    city TEXT NOT NULL,
                    approximate_location TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    additional_information TEXT,
                    requester_contact_preference TEXT NOT NULL DEFAULT 'in_app_chat',
                    consent_given INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'created',
                    escalation_stage INTEGER NOT NULL DEFAULT 1,
                    requested_for TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS donor_matches (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES blood_requests(id) ON DELETE CASCADE,
                    donor_id TEXT NOT NULL REFERENCES donor_profiles(id) ON DELETE CASCADE,
                    priority_score REAL NOT NULL DEFAULT 0,
                    match_reason TEXT NOT NULL,
                    match_status TEXT NOT NULL DEFAULT 'candidate',
                    escalation_stage INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (request_id, donor_id)
                );

                CREATE TABLE IF NOT EXISTS donor_responses (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES blood_requests(id) ON DELETE CASCADE,
                    donor_id TEXT NOT NULL REFERENCES donor_profiles(id) ON DELETE CASCADE,
                    response TEXT NOT NULL CHECK (response IN ('accepted', 'declined')),
                    responded_at TEXT NOT NULL,
                    UNIQUE (request_id, donor_id)
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    notification_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    related_request_id TEXT REFERENCES blood_requests(id) ON DELETE SET NULL,
                    delivery_status TEXT NOT NULL DEFAULT 'saved',
                    read_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES blood_requests(id) ON DELETE CASCADE,
                    requester_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    donor_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed', 'blocked')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (request_id, requester_id, donor_id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    sender_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    message_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    read_at TEXT
                );

                CREATE TABLE IF NOT EXISTS contact_sharing_consents (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES blood_requests(id) ON DELETE CASCADE,
                    requester_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    donor_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    requester_consent INTEGER NOT NULL DEFAULT 0,
                    donor_consent INTEGER NOT NULL DEFAULT 0,
                    requester_consent_at TEXT,
                    donor_consent_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'both_consented', 'withdrawn')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (request_id, requester_id, donor_id)
                );

                CREATE TABLE IF NOT EXISTS request_status_history (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES blood_requests(id) ON DELETE CASCADE,
                    previous_status TEXT,
                    new_status TEXT NOT NULL,
                    changed_by TEXT REFERENCES profiles(id) ON DELETE SET NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chatbot_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    session_status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chatbot_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES chatbot_sessions(id) ON DELETE CASCADE,
                    sender_type TEXT NOT NULL CHECK (sender_type IN ('user', 'assistant')),
                    message_text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_blocks (
                    id TEXT PRIMARY KEY,
                    blocker_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    blocked_user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (blocker_id, blocked_user_id)
                );

                CREATE TABLE IF NOT EXISTS blood_bank_contact_attempts (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES blood_requests(id) ON DELETE CASCADE,
                    blood_bank_id TEXT NOT NULL REFERENCES blood_banks(id) ON DELETE CASCADE,
                    recorded_by TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    outcome TEXT NOT NULL,
                    notes TEXT,
                    attempted_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS donor_documents (
                    id TEXT PRIMARY KEY,
                    donor_id TEXT NOT NULL REFERENCES donor_profiles(id) ON DELETE CASCADE,
                    storage_path TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'pending_review',
                    reviewed_by TEXT REFERENCES profiles(id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    reporter_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    reported_user_id TEXT REFERENCES profiles(id),
                    request_id TEXT REFERENCES blood_requests(id),
                    reason TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    reviewed_by TEXT REFERENCES profiles(id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS blood_banks (
                    id TEXT PRIMARY KEY,
                    facility_name TEXT NOT NULL,
                    address TEXT NOT NULL,
                    city TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    website TEXT,
                    latitude REAL,
                    longitude REAL,
                    verification_status TEXT NOT NULL DEFAULT 'directory_listing',
                    availability_status TEXT NOT NULL DEFAULT 'contact_required',
                    source TEXT NOT NULL,
                    last_verified_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    actor_id TEXT REFERENCES profiles(id),
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS donor_face_profiles (
                    id TEXT PRIMARY KEY,
                    donor_id TEXT NOT NULL UNIQUE REFERENCES donor_profiles(id) ON DELETE CASCADE,
                    descriptor_json TEXT NOT NULL,
                    consent_given INTEGER NOT NULL DEFAULT 1,
                    enrolled_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS face_verification_logs (
                    id TEXT PRIMARY KEY,
                    donor_id TEXT NOT NULL REFERENCES donor_profiles(id) ON DELETE CASCADE,
                    request_id TEXT REFERENCES blood_requests(id) ON DELETE SET NULL,
                    similarity_score REAL NOT NULL,
                    verified INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    verified_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS donor_location_tracking (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES blood_requests(id) ON DELETE CASCADE,
                    donor_id TEXT NOT NULL REFERENCES donor_profiles(id) ON DELETE CASCADE,
                    zone_lat REAL NOT NULL,
                    zone_lon REAL NOT NULL,
                    radius_meters INTEGER NOT NULL DEFAULT 1000,
                    tracking_status TEXT NOT NULL DEFAULT 'en_route',
                    distance_band TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (request_id, donor_id)
                );
                """
            )
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(profiles)").fetchall()}
            if "aadhaar_last4" not in cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN aadhaar_last4 TEXT NOT NULL DEFAULT '0000'")
            if "aadhaar_hash" not in cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN aadhaar_hash TEXT")
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_aadhaar_hash ON profiles(aadhaar_hash)")
            if "aadhaar_verified" not in cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN aadhaar_verified INTEGER NOT NULL DEFAULT 0")
            if "aadhaar_consent_at" not in cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN aadhaar_consent_at TEXT")
            dp_cols = {r["name"] for r in conn.execute("PRAGMA table_info(donor_profiles)").fetchall()}
            if "donor_frozen_until" not in dp_cols:
                conn.execute("ALTER TABLE donor_profiles ADD COLUMN donor_frozen_until TEXT")
            if "donor_freeze_reason" not in dp_cols:
                conn.execute("ALTER TABLE donor_profiles ADD COLUMN donor_freeze_reason TEXT")
            self._init_phase1_schema(conn)
            self._init_phase2_schema(conn)
            self._init_phase3_schema(conn)

    @staticmethod
    def _row_to_profile(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["phone_verified"] = bool(data["phone_verified"])
        data["aadhaar_verified"] = bool(data.get("aadhaar_verified", 0))
        data.pop("password_hash", None)
        data.pop("aadhaar_hash", None)
        return data

    def is_aadhaar_registered(self, aadhaar_hash: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM profiles WHERE aadhaar_hash = ? LIMIT 1", (aadhaar_hash,)
            ).fetchone()
        return row is not None

    def create_user(
        self,
        *,
        full_name: str,
        email: str,
        phone_number: str,
        password: str,
        city: str,
        approximate_location: str,
        date_of_birth: Optional[str],
        role_preference: str,
        blood_group: Optional[str],
        aadhaar_last4: str = "0000",
        aadhaar_hash: Optional[str] = None,
        aadhaar_verified: bool = False,
    ) -> Dict[str, Any]:
        if role_preference not in ("requester", "donor", "hospital"):
            raise ValueError("Public registration only allows 'requester', 'donor', or 'hospital' roles.")

        normalized_phone = normalize_phone(phone_number)
        normalized_email = email.strip().lower()
        now = _utc_now_iso()
        profile_id = str(uuid.uuid4())
        password_hash = hash_password(password)

        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO profiles (
                        id, auth_user_id, full_name, email, phone_number, password_hash,
                        role, city, approximate_location, date_of_birth, account_status,
                        phone_verified, aadhaar_last4, aadhaar_hash, aadhaar_verified,
                        aadhaar_consent_at, terms_accepted_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        profile_id,
                        full_name.strip(),
                        normalized_email,
                        normalized_phone,
                        password_hash,
                        role_preference,
                        city.strip(),
                        approximate_location.strip(),
                        date_of_birth,
                        aadhaar_last4,
                        aadhaar_hash,
                        int(aadhaar_verified),
                        now,
                        now,
                        now,
                        now,
                    ),
                )

                if role_preference == "donor" and blood_group:
                    conn.execute(
                        """
                        INSERT INTO donor_profiles (
                            id, user_id, blood_group, availability_status,
                            verification_status, emergency_notifications_enabled,
                            profile_completed, created_at, updated_at
                        ) VALUES (?, ?, ?, 'unavailable', 'not_submitted', 1, 1, ?, ?)
                        """,
                        (str(uuid.uuid4()), profile_id, blood_group, now, now),
                    )
        except sqlite3.IntegrityError as exc:
            if "aadhaar" in str(exc).lower():
                raise ConflictError("An account with this Aadhaar number already exists.") from exc
            raise ConflictError("An account with this email, phone number, or Aadhaar already exists.") from exc

        profile = self.get_profile_by_id(profile_id)
        assert profile is not None
        return profile

    def authenticate_user(self, identifier: str, password: str) -> Dict[str, Any]:
        cleaned = identifier.strip()
        normalized_phone = normalize_phone(cleaned)
        lowered_email = cleaned.lower()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE lower(email) = ? OR phone_number = ? LIMIT 1",
                (lowered_email, normalized_phone),
            ).fetchone()

        if row is None or not verify_password(password, row["password_hash"]):
            raise AuthenticationError("Invalid email/phone or password.")

        if row["account_status"] != "active":
            raise AuthenticationError("This account has been suspended or deactivated.")

        profile = self._row_to_profile(row)
        assert profile is not None
        return profile

    def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE id = ? LIMIT 1", (profile_id,)).fetchone()
        return self._row_to_profile(row)

    def get_profile_by_auth_user_id(self, auth_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE auth_user_id = ? LIMIT 1", (auth_user_id,)
            ).fetchone()
        return self._row_to_profile(row)

    def mark_phone_verified(self, profile_id: str) -> Optional[Dict[str, Any]]:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE profiles SET phone_verified = 1, updated_at = ? WHERE id = ?",
                (now, profile_id),
            )
        return self.get_profile_by_id(profile_id)

    def set_recovery_hashes(self, profile_id: str, hashes: List[str]) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT accessibility_prefs FROM profiles WHERE id = ? LIMIT 1", (profile_id,)
            ).fetchone()
            a11y: Dict[str, Any] = {"text_size": "normal", "high_contrast": False}
            if row and row["accessibility_prefs"]:
                try:
                    parsed = json.loads(row["accessibility_prefs"])
                    if isinstance(parsed, dict):
                        a11y.update(parsed)
                except Exception:
                    pass
            a11y["recovery_hashes"] = list(hashes)
            conn.execute(
                "UPDATE profiles SET accessibility_prefs = ?, updated_at = ? WHERE id = ?",
                (json.dumps(a11y), now, profile_id),
            )

    def get_recovery_hashes(self, profile_id: str) -> List[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT accessibility_prefs FROM profiles WHERE id = ? LIMIT 1", (profile_id,)
            ).fetchone()
        if not row or not row["accessibility_prefs"]:
            return []
        try:
            parsed = json.loads(row["accessibility_prefs"])
            if isinstance(parsed, dict):
                return [str(x) for x in (parsed.get("recovery_hashes") or [])]
        except Exception:
            pass
        return []

    def recover_password_with_code(
        self, *, identifier: str, code_hash: str, new_password: str
    ) -> Tuple[Dict[str, Any], int]:
        cleaned = identifier.strip()
        with self._connect() as conn:
            if "@" in cleaned:
                row = conn.execute(
                    "SELECT * FROM profiles WHERE lower(email) = ? LIMIT 1", (cleaned.lower(),)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM profiles WHERE phone_number = ? LIMIT 1", (normalize_phone(cleaned),)
                ).fetchone()

        if row is None or row["account_status"] != "active":
            raise AuthenticationError("Invalid account or recovery code.")

        profile_id = str(row["id"])
        hashes = self.get_recovery_hashes(profile_id)
        matched_idx = -1
        for idx, stored in enumerate(hashes):
            if hmac.compare_digest(str(stored), str(code_hash)):
                matched_idx = idx
                break
        if matched_idx < 0:
            raise AuthenticationError("Invalid or already-used recovery code.")

        remaining = [h for idx, h in enumerate(hashes) if idx != matched_idx]
        now = _utc_now_iso()
        new_hash = hash_password(new_password)
        with self._connect() as conn:
            conn.execute(
                "UPDATE profiles SET password_hash = ?, updated_at = ? WHERE id = ?",
                (new_hash, now, profile_id),
            )
        self.set_recovery_hashes(profile_id, remaining)
        profile = self.get_profile_by_id(profile_id)
        assert profile is not None
        return profile, len(remaining)

    def mark_aadhaar_verified(self, profile_id: str) -> Optional[Dict[str, Any]]:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE profiles SET aadhaar_verified = 1, updated_at = ? WHERE id = ?",
                (now, profile_id),
            )
        return self.get_profile_by_id(profile_id)

    def save_user_aadhaar_verification(
        self, *, profile_id: str, aadhaar_last4: str, aadhaar_hash: str
    ) -> Optional[Dict[str, Any]]:
        now = _utc_now_iso()
        try:
            with self._connect() as conn:
                dup = conn.execute(
                    "SELECT id FROM profiles WHERE aadhaar_hash = ? AND id != ? LIMIT 1",
                    (aadhaar_hash, profile_id),
                ).fetchone()
                if dup:
                    raise ConflictError("An account with this Aadhaar number is already registered.")
                conn.execute(
                    """
                    UPDATE profiles
                    SET aadhaar_last4 = ?, aadhaar_hash = ?, aadhaar_verified = 1,
                        aadhaar_consent_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (aadhaar_last4, aadhaar_hash, now, now, profile_id),
                )
        except sqlite3.IntegrityError as exc:
            raise ConflictError("An account with this Aadhaar number is already registered.") from exc
        return self.get_profile_by_id(profile_id)

    def update_profile(self, profile_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"full_name", "city", "approximate_location"}
        filtered = {k: v.strip() for k, v in updates.items() if k in allowed and v is not None}
        if not filtered:
            return self.get_profile_by_id(profile_id)

        filtered["updated_at"] = _utc_now_iso()
        assignments = ", ".join(f"{col} = ?" for col in filtered)
        values = list(filtered.values()) + [profile_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE profiles SET {assignments} WHERE id = ?", values)
        return self.get_profile_by_id(profile_id)

    def search_public_donors(
        self, blood_group: Optional[str] = None, city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT
                dp.id AS donor_id,
                p.full_name AS full_name,
                dp.blood_group AS blood_group,
                p.city AS city,
                p.approximate_location AS approximate_location,
                dp.availability_status AS availability_status,
                dp.verification_status AS verification_status
            FROM donor_profiles dp
            JOIN profiles p ON p.id = dp.user_id
            WHERE p.account_status = 'active'
              AND dp.availability_status != 'unavailable'
              AND (dp.donor_frozen_until IS NULL OR dp.donor_frozen_until <= ?)
        """
        params: List[Any] = [datetime.now().date().isoformat()]
        if blood_group:
            query += " AND dp.blood_group = ?"
            params.append(blood_group)
        if city:
            query += " AND lower(p.city) LIKE ?"
            params.append(f"%{city.strip().lower()}%")
        query += " ORDER BY dp.verification_status = 'verified' DESC, dp.updated_at DESC LIMIT 50"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            {
                "donor_id": row["donor_id"],
                "display_name": mask_display_name(row["full_name"]),
                "blood_group": row["blood_group"],
                "city": row["city"],
                "approximate_location": row["approximate_location"],
                "availability_status": row["availability_status"],
                "verification_status": row["verification_status"],
                "match_label": "Potential match (medical eligibility determined by blood bank)",
            }
            for row in rows
        ]

    def search_blood_banks(
        self, city: Optional[str] = None, query_text: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM blood_banks WHERE 1=1"
        params: List[Any] = []
        if city:
            sql += " AND lower(city) LIKE ?"
            params.append(f"%{city.strip().lower()}%")
        if query_text:
            sql += " AND (lower(facility_name) LIKE ? OR lower(address) LIKE ?)"
            q = f"%{query_text.strip().lower()}%"
            params.extend([q, q])
        sql += " ORDER BY facility_name ASC LIMIT 50"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        results = []
        for row in rows:
            item = dict(row)
            item["availability_label"] = AVAILABILITY_LABELS.get(
                item["availability_status"], "Contact required"
            )
            results.append(item)
        return results

    def get_admin_overview(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total_users = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
            total_donors = conn.execute("SELECT COUNT(*) FROM donor_profiles").fetchone()[0]
            verified_donors = conn.execute(
                "SELECT COUNT(*) FROM donor_profiles WHERE verification_status = 'verified'"
            ).fetchone()[0]
            active_requests = conn.execute(
                "SELECT COUNT(*) FROM blood_requests WHERE status NOT IN ('fulfilled', 'unresolved', 'cancelled', 'expired')"
            ).fetchone()[0]
            fulfilled_requests = conn.execute(
                "SELECT COUNT(*) FROM blood_requests WHERE status = 'fulfilled'"
            ).fetchone()[0]
            unresolved_requests = conn.execute(
                "SELECT COUNT(*) FROM blood_requests WHERE status = 'unresolved'"
            ).fetchone()[0]
            pending_document_reviews = conn.execute(
                "SELECT COUNT(*) FROM donor_documents WHERE review_status = 'pending_review'"
            ).fetchone()[0]
            open_reports = conn.execute(
                "SELECT COUNT(*) FROM reports WHERE status IN ('open', 'under_review')"
            ).fetchone()[0]
            blood_banks_count = conn.execute("SELECT COUNT(*) FROM blood_banks").fetchone()[0]

        return {
            "total_users": total_users,
            "total_donors": total_donors,
            "verified_donors": verified_donors,
            "active_requests": active_requests,
            "fulfilled_requests": fulfilled_requests,
            "unresolved_requests": unresolved_requests,
            "pending_document_reviews": pending_document_reviews,
            "open_reports": open_reports,
            "blood_banks_count": blood_banks_count,
            "disclaimer": "Platform operational records only, not clinical outcomes.",
        }

    def list_users_for_admin(
        self, role: Optional[str] = None, search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT id, full_name, email, phone_number, role, city,
                   approximate_location, account_status, phone_verified,
                   aadhaar_last4, aadhaar_verified, created_at
            FROM profiles WHERE 1=1
        """
        params: List[Any] = []
        if role:
            sql += " AND role = ?"
            params.append(role)
        if search:
            sql += " AND (lower(full_name) LIKE ? OR lower(email) LIKE ? OR lower(city) LIKE ?)"
            q = f"%{search.strip().lower()}%"
            params.extend([q, q, q])
        sql += " ORDER BY created_at DESC LIMIT 100"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["phone_verified"] = bool(item["phone_verified"])
            item["aadhaar_verified"] = bool(item.get("aadhaar_verified", 0))
            last4 = item.pop("aadhaar_last4", "0000") or "0000"
            item["aadhaar_masked"] = f"XXXX-XXXX-{last4}"
            results.append(item)
        return results

    def promote_to_admin_cli(self, email: str) -> Optional[Dict[str, Any]]:
        cleaned = email.strip().lower()
        now = _utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE profiles SET role = 'admin', updated_at = ? WHERE lower(email) = ?",
                (now, cleaned),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM profiles WHERE lower(email) = ? LIMIT 1", (cleaned,)
            ).fetchone()
        return self._row_to_profile(row)

    # --- Phase 2: Donor & Request Methods (SQLite) ---

    @staticmethod
    def _row_to_donor(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        d = dict(row)
        d["emergency_notifications_enabled"] = bool(d["emergency_notifications_enabled"])
        d["profile_completed"] = bool(d["profile_completed"])
        return d

    def get_donor_profile_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM donor_profiles WHERE user_id = ? LIMIT 1", (user_id,)
            ).fetchone()
        return self._row_to_donor(row)

    def upsert_donor_profile(
        self,
        *,
        user_id: str,
        blood_group: str,
        availability_status: str,
        last_donation_date: Optional[str],
        preferred_contact_method: str,
        emergency_notifications_enabled: bool,
        cooldown_days: int = 90,
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        frozen_until, freeze_reason = _compute_freeze_fields(last_donation_date, cooldown_days)
        effective_avail = "unavailable" if frozen_until else availability_status
        existing = self.get_donor_profile_by_user_id(user_id)
        with self._connect() as conn:
            if existing:
                conn.execute(
                    """
                    UPDATE donor_profiles
                    SET blood_group = ?, availability_status = ?, last_donation_date = ?,
                        donor_frozen_until = ?, donor_freeze_reason = ?,
                        preferred_contact_method = ?, emergency_notifications_enabled = ?,
                        profile_completed = 1, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (
                        blood_group,
                        effective_avail,
                        last_donation_date,
                        frozen_until,
                        freeze_reason,
                        preferred_contact_method,
                        int(emergency_notifications_enabled),
                        now,
                        user_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO donor_profiles (
                        id, user_id, blood_group, availability_status, last_donation_date,
                        donor_frozen_until, donor_freeze_reason,
                        preferred_contact_method, verification_status,
                        emergency_notifications_enabled, profile_completed, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'not_submitted', ?, 1, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        blood_group,
                        effective_avail,
                        last_donation_date,
                        frozen_until,
                        freeze_reason,
                        preferred_contact_method,
                        int(emergency_notifications_enabled),
                        now,
                        now,
                    ),
                )
        res = self.get_donor_profile_by_user_id(user_id)
        assert res is not None
        return res

    def update_donor_availability(
        self,
        *,
        user_id: str,
        availability_status: str,
        emergency_notifications_enabled: Optional[bool],
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        with self._connect() as conn:
            if emergency_notifications_enabled is None:
                conn.execute(
                    "UPDATE donor_profiles SET availability_status = ?, updated_at = ? WHERE user_id = ?",
                    (availability_status, now, user_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE donor_profiles
                    SET availability_status = ?, emergency_notifications_enabled = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (availability_status, int(emergency_notifications_enabled), now, user_id),
                )
        res = self.get_donor_profile_by_user_id(user_id)
        assert res is not None
        return res

    def update_donor_history(
        self, *, user_id: str, last_donation_date: Optional[str], cooldown_days: int = 90
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        frozen_until, freeze_reason = _compute_freeze_fields(last_donation_date, cooldown_days)
        with self._connect() as conn:
            if frozen_until:
                conn.execute(
                    """
                    UPDATE donor_profiles
                    SET last_donation_date = ?, donor_frozen_until = ?, donor_freeze_reason = ?,
                        availability_status = 'unavailable', updated_at = ?
                    WHERE user_id = ?
                    """,
                    (last_donation_date, frozen_until, freeze_reason, now, user_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE donor_profiles
                    SET last_donation_date = ?, donor_frozen_until = NULL, donor_freeze_reason = NULL,
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (last_donation_date, now, user_id),
                )
        res = self.get_donor_profile_by_user_id(user_id)
        assert res is not None
        return res

    def create_blood_request(
        self,
        *,
        requester_id: str,
        patient_reference_name: str,
        blood_group: str,
        units_requested: int,
        hospital_name: str,
        hospital_location: str,
        city: str,
        approximate_location: str,
        urgency: str,
        additional_information: Optional[str],
        requester_contact_preference: str,
        requested_for: str,
        expires_at: str,
        is_emergency_quick: bool = False,
        coordinator_contact_name: Optional[str] = None,
        coordinator_contact_relation: Optional[str] = None,
        hospital_id: Optional[str] = None,
        created_by_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        req_id = str(uuid.uuid4())

        with self._connect() as conn:
            dup = conn.execute(
                """
                SELECT id FROM blood_requests
                WHERE requester_id = ? AND blood_group = ? AND lower(city) = ?
                  AND status NOT IN ('fulfilled', 'unresolved', 'cancelled', 'expired')
                LIMIT 1
                """,
                (requester_id, blood_group, city.strip().lower()),
            ).fetchone()
            if dup is not None:
                raise ConflictError(
                    "You already have an active blood request for this blood group and city. "
                    "Please update or cancel the existing request instead of creating a duplicate."
                )

            conn.execute(
                """
                INSERT INTO blood_requests (
                    id, requester_id, created_by_user_id, patient_reference_name, blood_group, units_requested,
                    hospital_name, hospital_location, city, approximate_location, urgency,
                    additional_information, requester_contact_preference, consent_given,
                    status, escalation_stage, is_emergency_quick, coordinator_contact_name,
                    coordinator_contact_relation, hospital_id, requested_for, expires_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'created', 1, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    req_id,
                    requester_id,
                    created_by_user_id or requester_id,
                    patient_reference_name.strip(),
                    blood_group,
                    units_requested,
                    hospital_name.strip(),
                    hospital_location.strip(),
                    city.strip(),
                    approximate_location.strip(),
                    urgency,
                    additional_information.strip() if additional_information else None,
                    requester_contact_preference,
                    int(is_emergency_quick),
                    coordinator_contact_name.strip() if coordinator_contact_name else None,
                    coordinator_contact_relation.strip() if coordinator_contact_relation else None,
                    hospital_id,
                    requested_for,
                    expires_at,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO request_status_history (
                    id, request_id, previous_status, new_status, changed_by, notes, created_at
                ) VALUES (?, ?, NULL, 'created', ?, 'Blood request created by requester.', ?)
                """,
                (str(uuid.uuid4()), req_id, requester_id, now),
            )
        req = self.get_blood_request(req_id)
        assert req is not None
        return req

    def expire_stale_requests(self) -> int:
        now = _utc_now_iso()
        with self._connect() as conn:
            stale_rows = conn.execute(
                """
                SELECT id, status, requester_id, blood_group, hospital_name FROM blood_requests
                WHERE expires_at <= ?
                  AND status NOT IN ('fulfilled', 'unresolved', 'cancelled', 'expired')
                """,
                (now,),
            ).fetchall()
            for row in stale_rows:
                conn.execute(
                    "UPDATE blood_requests SET status = 'expired', updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                conn.execute(
                    """
                    INSERT INTO request_status_history (
                        id, request_id, previous_status, new_status, changed_by, notes, created_at
                    ) VALUES (?, ?, ?, 'expired', NULL, 'Request expired automatically after configured window.', ?)
                    """,
                    (str(uuid.uuid4()), row["id"], row["status"], now),
                )
                conn.execute(
                    """
                    INSERT INTO notifications (
                        id, user_id, notification_type, title, message, related_request_id,
                        delivery_status, created_at
                    ) VALUES (?, ?, 'request_expired', 'Blood Request Expired',
                              'Your blood request has expired and alerts have been stopped.', ?, 'saved', ?)
                    """,
                    (str(uuid.uuid4()), row["requester_id"], row["id"], now),
                )
                self._close_request_side_effects_sqlite(
                    conn,
                    request_id=row["id"],
                    blood_group=row["blood_group"],
                    hospital_name=row["hospital_name"],
                    notification_type="request_expired",
                    title="Blood Request Expired — Alert Closed",
                    message=(
                        f"The {row['blood_group']} request at {row['hospital_name']} has expired. "
                        "No further action is needed."
                    ),
                    new_match_status="expired",
                )
                self._write_audit_log(
                    conn,
                    actor_id=row["requester_id"],
                    action="request_expired",
                    target_type="blood_request",
                    target_id=row["id"],
                )
            return len(stale_rows)

    def list_requests_for_user(self, requester_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM blood_requests WHERE requester_id = ? ORDER BY created_at DESC",
                (requester_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_blood_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM blood_requests WHERE id = ? LIMIT 1", (request_id,)
            ).fetchone()
        return dict(row) if row else None

    def is_donor_matched_to_request(self, user_id: str, request_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM donor_matches dm
                JOIN donor_profiles dp ON dp.id = dm.donor_id
                WHERE dm.request_id = ? AND dp.user_id = ? LIMIT 1
                """,
                (request_id, user_id),
            ).fetchone()
        return row is not None

    def update_blood_request(
        self, *, request_id: str, changed_by: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        allowed = {
            "units_requested",
            "hospital_name",
            "hospital_location",
            "approximate_location",
            "urgency",
            "additional_information",
        }
        filtered: Dict[str, Any] = {}
        for k, v in updates.items():
            if k in allowed and v is not None:
                filtered[k] = v.strip() if isinstance(v, str) else v
        if not filtered:
            req = self.get_blood_request(request_id)
            assert req is not None
            return req

        now = _utc_now_iso()
        filtered["updated_at"] = now
        assignments = ", ".join(f"{col} = ?" for col in filtered)
        values = list(filtered.values()) + [request_id]
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT status FROM blood_requests WHERE id = ?", (request_id,)
            ).fetchone()
            conn.execute(f"UPDATE blood_requests SET {assignments} WHERE id = ?", values)
            conn.execute(
                """
                INSERT INTO request_status_history (
                    id, request_id, previous_status, new_status, changed_by, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, 'Request details updated by requester.', ?)
                """,
                (
                    str(uuid.uuid4()),
                    request_id,
                    existing["status"] if existing else None,
                    existing["status"] if existing else "created",
                    changed_by,
                    now,
                ),
            )
        req = self.get_blood_request(request_id)
        assert req is not None
        return req

    def cancel_blood_request(self, *, request_id: str, changed_by: str, reason: str) -> Dict[str, Any]:
        now = _utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT status, blood_group, hospital_name FROM blood_requests WHERE id = ?", (request_id,)
            ).fetchone()
            prev = existing["status"] if existing else None
            conn.execute(
                "UPDATE blood_requests SET status = 'cancelled', cancellation_reason = ?, updated_at = ? WHERE id = ?",
                (reason, now, request_id),
            )
            conn.execute(
                """
                INSERT INTO request_status_history (
                    id, request_id, previous_status, new_status, changed_by, notes, created_at
                ) VALUES (?, ?, ?, 'cancelled', ?, ?, ?)
                """,
                (str(uuid.uuid4()), request_id, prev, changed_by, reason, now),
            )
            if existing:
                self._close_request_side_effects_sqlite(
                    conn,
                    request_id=request_id,
                    blood_group=existing["blood_group"],
                    hospital_name=existing["hospital_name"],
                    notification_type="request_cancelled",
                    title="Blood Request Cancelled",
                    message=(
                        f"The {existing['blood_group']} request at {existing['hospital_name']} has been cancelled "
                        f"({reason}). Thank you for your readiness."
                    ),
                    new_match_status="skipped",
                )
                self._write_audit_log(
                    conn,
                    actor_id=changed_by,
                    action="request_cancelled",
                    target_type="blood_request",
                    target_id=request_id,
                    metadata_json=reason,
                )
        req = self.get_blood_request(request_id)
        assert req is not None
        return req

    def get_request_status_history(self, request_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM request_status_history WHERE request_id = ? ORDER BY created_at ASC",
                (request_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Phase 3: Matching, Escalation, Responses & Notifications (SQLite) ---

    def _create_notification(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str,
        notification_type: str,
        title: str,
        message: str,
        related_request_id: Optional[str],
    ) -> None:
        conn.execute(
            """
            INSERT INTO notifications (
                id, user_id, notification_type, title, message, related_request_id,
                delivery_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'saved', ?)
            """,
            (str(uuid.uuid4()), user_id, notification_type, title, message, related_request_id, _utc_now_iso()),
        )

    def run_matching_for_request(
        self,
        *,
        request_row: Dict[str, Any],
        actor_id: str,
        stage: int,
        max_new_notifications: int,
        review_interval_days: int,
    ) -> Dict[str, Any]:
        from backend.app.services.matching import score_candidate

        request_id = str(request_row["id"])
        allow_wider = stage >= 3
        now = _utc_now_iso()

        with self._connect() as conn:
            existing_rows = conn.execute(
                "SELECT donor_id FROM donor_matches WHERE request_id = ?", (request_id,)
            ).fetchall()
            already_matched = {r["donor_id"] for r in existing_rows}

            blocked_rows = conn.execute(
                "SELECT blocker_id, blocked_user_id FROM user_blocks WHERE blocker_id = ? OR blocked_user_id = ?",
                (request_row["requester_id"], request_row["requester_id"]),
            ).fetchall()
            blocked_user_ids = {
                r["blocked_user_id"] if r["blocker_id"] == request_row["requester_id"] else r["blocker_id"]
                for r in blocked_rows
            }

            donor_rows = conn.execute(
                """
                SELECT dp.*, p.full_name, p.city, p.approximate_location, p.account_status
                FROM donor_profiles dp
                JOIN profiles p ON p.id = dp.user_id
                """
            ).fetchall()

            scored: List[tuple[float, Dict[str, Any], str]] = []
            for d_row in donor_rows:
                d = dict(d_row)
                d["emergency_notifications_enabled"] = bool(d["emergency_notifications_enabled"])
                self._enrich_donor_row_with_calendar_sqlite(conn, d)
                if d["id"] in already_matched or d["user_id"] in blocked_user_ids:
                    continue
                eligible, score, reason = score_candidate(
                    request_row=request_row,
                    donor_row=d,
                    allow_wider_city=allow_wider,
                    review_interval_days=review_interval_days,
                )
                if eligible:
                    scored.append((score, d, reason))

            scored.sort(key=lambda item: item[0], reverse=True)
            selected = scored[:max_new_notifications]

            for score, donor_d, reason in selected:
                conn.execute(
                    """
                    INSERT INTO donor_matches (
                        id, request_id, donor_id, priority_score, match_reason,
                        match_status, escalation_stage, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'notified', ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), request_id, donor_d["id"], score, reason, stage, now, now),
                )
                self._create_notification(
                    conn,
                    user_id=donor_d["user_id"],
                    notification_type="new_request_alert",
                    title=f"{request_row['blood_group']} Blood Request ({request_row['urgency'].upper()})",
                    message=(
                        f"{request_row['units_requested']} unit(s) needed at {request_row['hospital_name']}, "
                        f"{request_row['city']} ({request_row['approximate_location']})."
                    ),
                    related_request_id=request_id,
                )

            total_candidates = len(already_matched) + len(selected)
            prev_status = request_row["status"]
            if len(selected) > 0:
                new_status = "escalation_in_progress" if stage >= 3 else "donors_notified"
                note = f"Stage {stage}: Notified {len(selected)} potential donor candidate(s)."
                new_stage = stage
            elif total_candidates == 0:
                new_status = "blood_bank_assistance"
                new_stage = 4
                note = "No matching available donors found; escalated to Stage 4 Blood-Bank Assistance."
                self._create_notification(
                    conn,
                    user_id=request_row["requester_id"],
                    notification_type="blood_bank_fallback",
                    title="No Nearby Donors Found — Blood-Bank Assistance",
                    message=(
                        "No matching available donors were found right now. Please check the Blood-Bank "
                        "Directory and contact the treating hospital's transfusion service immediately."
                    ),
                    related_request_id=request_id,
                )
            else:
                new_status = "escalation_in_progress" if stage >= 3 else prev_status
                new_stage = stage
                note = f"Stage {stage} escalation ran; no additional unnotified candidates found."

            conn.execute(
                "UPDATE blood_requests SET status = ?, escalation_stage = ?, updated_at = ? WHERE id = ?",
                (new_status, new_stage, now, request_id),
            )
            conn.execute(
                """
                INSERT INTO request_status_history (
                    id, request_id, previous_status, new_status, changed_by, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), request_id, prev_status, new_status, actor_id, note, now),
            )

        return {
            "request_id": request_id,
            "request_status": new_status,
            "escalation_stage": new_stage,
            "newly_notified_count": len(selected),
            "total_candidates_count": total_candidates,
            "candidates": self.list_matches_for_request(request_id),
            "message": note,
        }

    def escalate_to_fallback_stage(
        self, *, request_row: Dict[str, Any], actor_id: str, target_stage: int
    ) -> Dict[str, Any]:
        request_id = str(request_row["id"])
        now = _utc_now_iso()
        prev_status = request_row["status"]
        if target_stage == 4:
            new_status = "blood_bank_assistance"
            note = "Stage 4: Blood-Bank Assistance activated. Contact verified facilities or e-RaktKosh."
            notif_title = "Stage 4: Blood-Bank Assistance Activated"
            notif_msg = "Check the Blood-Bank Directory and official resources while coordinating with your hospital."
            notif_type = "blood_bank_fallback"
        else:
            new_status = "escalation_in_progress"
            note = (
                "Stage 5: Hospital-coordinated wider search. Contact the treating hospital's blood bank "
                "immediately; request remains open/unresolved until a genuine outcome is recorded."
            )
            notif_title = "Stage 5: Hospital-Coordinated Wider Search"
            notif_msg = note
            notif_type = "escalation_update"

        with self._connect() as conn:
            conn.execute(
                "UPDATE blood_requests SET status = ?, escalation_stage = ?, updated_at = ? WHERE id = ?",
                (new_status, target_stage, now, request_id),
            )
            conn.execute(
                """
                INSERT INTO request_status_history (
                    id, request_id, previous_status, new_status, changed_by, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), request_id, prev_status, new_status, actor_id, note, now),
            )
            self._create_notification(
                conn,
                user_id=request_row["requester_id"],
                notification_type=notif_type,
                title=notif_title,
                message=notif_msg,
                related_request_id=request_id,
            )

        candidates = self.list_matches_for_request(request_id)
        return {
            "request_id": request_id,
            "request_status": new_status,
            "escalation_stage": target_stage,
            "newly_notified_count": 0,
            "total_candidates_count": len(candidates),
            "candidates": candidates,
            "message": note,
        }

    def list_matches_for_request(self, request_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT dm.*, dp.blood_group, dp.availability_status, dp.verification_status,
                       p.full_name, p.city, p.approximate_location
                FROM donor_matches dm
                JOIN donor_profiles dp ON dp.id = dm.donor_id
                JOIN profiles p ON p.id = dp.user_id
                WHERE dm.request_id = ?
                ORDER BY dm.priority_score DESC, dm.created_at ASC
                """,
                (request_id,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "request_id": r["request_id"],
                "donor_id": r["donor_id"],
                "donor_display_name": mask_display_name(r["full_name"]),
                "blood_group": r["blood_group"],
                "city": r["city"],
                "approximate_location": r["approximate_location"],
                "availability_status": r["availability_status"],
                "verification_status": r["verification_status"],
                "priority_score": float(r["priority_score"]),
                "match_reason": r["match_reason"],
                "match_status": r["match_status"],
                "escalation_stage": int(r["escalation_stage"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def list_incoming_requests_for_donor(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            donor = conn.execute(
                "SELECT id FROM donor_profiles WHERE user_id = ? LIMIT 1", (user_id,)
            ).fetchone()
            if not donor:
                return []
            rows = conn.execute(
                """
                SELECT dm.id AS match_id, dm.match_status, dm.priority_score, dm.match_reason,
                       br.id AS request_id, br.blood_group, br.units_requested, br.hospital_name,
                       br.hospital_location, br.city, br.approximate_location, br.urgency,
                       br.status AS request_status, br.expires_at,
                       dr.response AS my_response,
                       c.id AS conversation_id
                FROM donor_matches dm
                JOIN blood_requests br ON br.id = dm.request_id
                LEFT JOIN donor_responses dr ON dr.request_id = br.id AND dr.donor_id = dm.donor_id
                LEFT JOIN conversations c ON c.request_id = br.id AND c.donor_id = ?
                WHERE dm.donor_id = ?
                ORDER BY dm.created_at DESC
                """,
                (user_id, donor["id"]),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_donor_response(
        self,
        *,
        request_row: Dict[str, Any],
        donor_profile: Dict[str, Any],
        donor_user: Dict[str, Any],
        response_value: str,
    ) -> Dict[str, Any]:
        request_id = str(request_row["id"])
        donor_id = str(donor_profile["id"])
        now = _utc_now_iso()
        conv_id: Optional[str] = None

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM donor_responses WHERE request_id = ? AND donor_id = ? LIMIT 1",
                (request_id, donor_id),
            ).fetchone()
            if existing:
                resp_id = existing["id"]
                conn.execute(
                    "UPDATE donor_responses SET response = ?, responded_at = ? WHERE id = ?",
                    (response_value, now, resp_id),
                )
            else:
                resp_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO donor_responses (id, request_id, donor_id, response, responded_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (resp_id, request_id, donor_id, response_value, now),
                )

            conn.execute(
                "UPDATE donor_matches SET match_status = ?, updated_at = ? WHERE request_id = ? AND donor_id = ?",
                (response_value, now, request_id, donor_id),
            )

            prev_status = request_row["status"]
            if response_value == "accepted":
                new_status = "connection_in_progress"
                conv_row = conn.execute(
                    "SELECT id FROM conversations WHERE request_id = ? AND requester_id = ? AND donor_id = ?",
                    (request_id, request_row["requester_id"], donor_user["id"]),
                ).fetchone()
                if conv_row:
                    conv_id = conv_row["id"]
                else:
                    conv_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO conversations (id, request_id, requester_id, donor_id, status, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 'active', ?, ?)
                        """,
                        (conv_id, request_id, request_row["requester_id"], donor_user["id"], now, now),
                    )
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO contact_sharing_consents (
                            id, request_id, requester_id, donor_id, requester_consent, donor_consent,
                            status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, 0, 0, 'pending', ?, ?)
                        """,
                        (str(uuid.uuid4()), request_id, request_row["requester_id"], donor_user["id"], now, now),
                    )
                self._create_notification(
                    conn,
                    user_id=request_row["requester_id"],
                    notification_type="donor_accepted",
                    title="A Potential Donor Accepted Your Request",
                    message=(
                        f"{mask_display_name(donor_user['full_name'])} ({donor_profile['blood_group']}) "
                        "selected 'I CAN HELP'. Private in-app chat is now open."
                    ),
                    related_request_id=request_id,
                )
                note = "Donor accepted; private communication authorized (not yet fulfilled)."
            else:
                new_status = (
                    "responses_received"
                    if prev_status in ("created", "matching", "donors_notified")
                    else prev_status
                )
                self._create_notification(
                    conn,
                    user_id=request_row["requester_id"],
                    notification_type="donor_declined",
                    title="Donor Unavailable Response Recorded",
                    message="A notified candidate marked themselves not available for this request.",
                    related_request_id=request_id,
                )
                note = "Donor declined ('NOT AVAILABLE')."

            conn.execute(
                "UPDATE blood_requests SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, request_id),
            )
            conn.execute(
                """
                INSERT INTO request_status_history (
                    id, request_id, previous_status, new_status, changed_by, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), request_id, prev_status, new_status, donor_user["id"], note, now),
            )

        return {
            "id": resp_id,
            "request_id": request_id,
            "donor_id": donor_id,
            "donor_display_name": mask_display_name(donor_user["full_name"]),
            "blood_group": donor_profile["blood_group"],
            "response": response_value,
            "responded_at": now,
            "conversation_id": conv_id,
        }

    def list_responses_for_request(self, request_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT dr.*, dp.blood_group, dp.user_id AS donor_user_id, p.full_name,
                       c.id AS conversation_id
                FROM donor_responses dr
                JOIN donor_profiles dp ON dp.id = dr.donor_id
                JOIN profiles p ON p.id = dp.user_id
                LEFT JOIN conversations c ON c.request_id = dr.request_id AND c.donor_id = dp.user_id
                WHERE dr.request_id = ?
                ORDER BY dr.responded_at DESC
                """,
                (request_id,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "request_id": r["request_id"],
                "donor_id": r["donor_id"],
                "donor_display_name": mask_display_name(r["full_name"]),
                "blood_group": r["blood_group"],
                "response": r["response"],
                "responded_at": r["responded_at"],
                "conversation_id": r["conversation_id"],
            }
            for r in rows
        ]

    def list_notifications(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 100",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_notification_read(self, notification_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE notifications SET read_at = COALESCE(read_at, ?) WHERE id = ? AND user_id = ?",
                (now, notification_id, user_id),
            )
            row = conn.execute(
                "SELECT * FROM notifications WHERE id = ? AND user_id = ? LIMIT 1",
                (notification_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def mark_all_notifications_read(self, user_id: str) -> int:
        now = _utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
                (now, user_id),
            )
            return cur.rowcount

    # --- Phase 4: Private Communication, Contact Consent & Reports (SQLite) ---

    def _hydrate_conversation(
        self, conn: sqlite3.Connection, row: sqlite3.Row, current_user_id: str
    ) -> Dict[str, Any]:
        is_requester = row["requester_id"] == current_user_id
        is_donor = row["donor_id"] == current_user_id
        counterpart_id = row["donor_id"] if (is_requester or not is_donor) else row["requester_id"]
        counterpart = conn.execute(
            "SELECT full_name FROM profiles WHERE id = ? LIMIT 1", (counterpart_id,)
        ).fetchone()
        req = conn.execute(
            "SELECT blood_group, hospital_name, city FROM blood_requests WHERE id = ? LIMIT 1",
            (row["request_id"],),
        ).fetchone()
        unread = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND sender_id != ? AND read_at IS NULL",
            (row["id"], current_user_id),
        ).fetchone()[0]
        return {
            "id": row["id"],
            "request_id": row["request_id"],
            "blood_group": req["blood_group"] if req else "",
            "hospital_name": req["hospital_name"] if req else "",
            "city": req["city"] if req else "",
            "counterpart_user_id": counterpart_id,
            "counterpart_display_name": mask_display_name(counterpart["full_name"]) if counterpart else "Participant",
            "my_role": "requester" if is_requester else ("donor" if is_donor else "coordinator"),
            "status": row["status"],
            "unread_count": unread,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_conversations_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT c.*
                FROM conversations c
                LEFT JOIN request_coordinators rc
                    ON rc.request_id = c.request_id
                   AND rc.coordinator_user_id = ?
                   AND rc.status = 'active'
                   AND rc.can_chat = 1
                WHERE c.requester_id = ? OR c.donor_id = ? OR rc.id IS NOT NULL
                ORDER BY c.updated_at DESC
                """,
                (user_id, user_id, user_id),
            ).fetchall()
            return [self._hydrate_conversation(conn, r, user_id) for r in rows]

    def get_conversation_for_participant(self, conversation_id: str, user_id: str) -> Any:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ? LIMIT 1", (conversation_id,)
            ).fetchone()
            if not row:
                return None
            if row["requester_id"] != user_id and row["donor_id"] != user_id:
                coord = conn.execute(
                    """
                    SELECT 1 FROM request_coordinators
                    WHERE request_id = ? AND coordinator_user_id = ? AND status = 'active' AND can_chat = 1
                    LIMIT 1
                    """,
                    (row["request_id"], user_id),
                ).fetchone()
                if not coord:
                    return "FORBIDDEN"
            return self._hydrate_conversation(conn, row, user_id)

    def list_messages(self, conversation_id: str, current_user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.*, p.full_name AS sender_name
                FROM messages m
                JOIN profiles p ON p.id = m.sender_id
                WHERE m.conversation_id = ?
                ORDER BY m.created_at ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "conversation_id": r["conversation_id"],
                "sender_id": r["sender_id"],
                "sender_display_name": mask_display_name(r["sender_name"]),
                "is_mine": r["sender_id"] == current_user_id,
                "message_text": r["message_text"],
                "created_at": r["created_at"],
                "read_at": r["read_at"],
            }
            for r in rows
        ]

    def create_message(
        self,
        *,
        conversation_id: str,
        sender_id: str,
        counterpart_id: str,
        request_id: str,
        message_text: str,
        sender_full_name: str,
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        msg_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, sender_id, message_text, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (msg_id, conversation_id, sender_id, message_text, now),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
            self._create_notification(
                conn,
                user_id=counterpart_id,
                notification_type="new_message",
                title="New Private Chat Message",
                message=f"{mask_display_name(sender_full_name)} sent a message regarding your blood request.",
                related_request_id=request_id,
            )
        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "sender_display_name": mask_display_name(sender_full_name),
            "is_mine": True,
            "message_text": message_text,
            "created_at": now,
            "read_at": None,
        }

    def mark_messages_read(self, conversation_id: str, current_user_id: str) -> int:
        now = _utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE messages SET read_at = ?
                WHERE conversation_id = ? AND sender_id != ? AND read_at IS NULL
                """,
                (now, conversation_id, current_user_id),
            )
            return cur.rowcount

    def _resolve_consent_row(
        self, conn: sqlite3.Connection, request_id: str, current_user_id: str, donor_user_id: Optional[str]
    ) -> Any:
        if donor_user_id:
            row = conn.execute(
                "SELECT * FROM contact_sharing_consents WHERE request_id = ? AND donor_id = ? LIMIT 1",
                (request_id, donor_user_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM contact_sharing_consents
                WHERE request_id = ? AND (requester_id = ? OR donor_id = ?)
                LIMIT 1
                """,
                (request_id, current_user_id, current_user_id),
            ).fetchone()
        if not row:
            return None
        if row["requester_id"] != current_user_id and row["donor_id"] != current_user_id:
            return "FORBIDDEN"
        return row

    def _format_consent_out(self, conn: sqlite3.Connection, row: sqlite3.Row, current_user_id: str) -> Dict[str, Any]:
        req_c = bool(row["requester_consent"])
        don_c = bool(row["donor_consent"])
        both = req_c and don_c and row["status"] == "both_consented"
        counterpart_phone = None
        if both:
            other_id = row["donor_id"] if row["requester_id"] == current_user_id else row["requester_id"]
            other = conn.execute("SELECT phone_number FROM profiles WHERE id = ? LIMIT 1", (other_id,)).fetchone()
            counterpart_phone = other["phone_number"] if other else None
        return {
            "request_id": row["request_id"],
            "requester_consent": req_c,
            "donor_consent": don_c,
            "requester_consent_at": row["requester_consent_at"],
            "donor_consent_at": row["donor_consent_at"],
            "status": row["status"],
            "counterpart_phone_number": counterpart_phone,
        }

    def get_contact_sharing_status(
        self, *, request_id: str, current_user_id: str, donor_user_id: Optional[str]
    ) -> Any:
        with self._connect() as conn:
            row = self._resolve_consent_row(conn, request_id, current_user_id, donor_user_id)
            if row in (None, "FORBIDDEN"):
                return row
            return self._format_consent_out(conn, row, current_user_id)

    def update_contact_sharing_consent(
        self, *, request_id: str, current_user_id: str, donor_user_id: Optional[str], grant: bool
    ) -> Any:
        now = _utc_now_iso()
        with self._connect() as conn:
            row = self._resolve_consent_row(conn, request_id, current_user_id, donor_user_id)
            if row in (None, "FORBIDDEN"):
                return row
            is_requester = row["requester_id"] == current_user_id
            req_c = bool(row["requester_consent"])
            don_c = bool(row["donor_consent"])
            req_at = row["requester_consent_at"]
            don_at = row["donor_consent_at"]

            if grant:
                if is_requester:
                    req_c = True
                    req_at = now
                else:
                    don_c = True
                    don_at = now
                new_status = "both_consented" if (req_c and don_c) else "pending"
            else:
                if is_requester:
                    req_c = False
                else:
                    don_c = False
                new_status = "withdrawn"

            conn.execute(
                """
                UPDATE contact_sharing_consents
                SET requester_consent = ?, donor_consent = ?, requester_consent_at = ?,
                    donor_consent_at = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (int(req_c), int(don_c), req_at, don_at, new_status, now, row["id"]),
            )
            updated = conn.execute(
                "SELECT * FROM contact_sharing_consents WHERE id = ?", (row["id"],)
            ).fetchone()
            return self._format_consent_out(conn, updated, current_user_id)

    def create_report(
        self,
        *,
        reporter_id: str,
        reported_user_id: Optional[str],
        request_id: Optional[str],
        reason: str,
        description: Optional[str],
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        rep_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reports (
                    id, reporter_id, reported_user_id, request_id, reason, description,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (rep_id, reporter_id, reported_user_id, request_id, reason.strip(), description, now, now),
            )
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (rep_id,)).fetchone()
        return dict(row)

    def block_user(
        self,
        *,
        blocker_id: str,
        blocked_user_id: str,
        conversation_id: Optional[str],
        reason: str,
    ) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO user_blocks (id, blocker_id, blocked_user_id, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), blocker_id, blocked_user_id, reason, now),
            )
            if conversation_id:
                conn.execute(
                    """
                    UPDATE conversations SET status = 'blocked', updated_at = ?
                    WHERE id = ? AND (requester_id = ? OR donor_id = ?)
                    """,
                    (now, conversation_id, blocker_id, blocker_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE conversations SET status = 'blocked', updated_at = ?
                    WHERE (requester_id = ? AND donor_id = ?) OR (requester_id = ? AND donor_id = ?)
                    """,
                    (now, blocker_id, blocked_user_id, blocked_user_id, blocker_id),
                )

    # --- Phase 5: Rule-Based LifeLink Assistant Sessions (SQLite) ---

    def get_or_create_chatbot_session(self, user_id: str, session_id: Optional[str]) -> str:
        now = _utc_now_iso()
        with self._connect() as conn:
            if session_id:
                row = conn.execute(
                    "SELECT id FROM chatbot_sessions WHERE id = ? AND user_id = ? LIMIT 1",
                    (session_id, user_id),
                ).fetchone()
                if row:
                    return row["id"]
            latest = conn.execute(
                "SELECT id FROM chatbot_sessions WHERE user_id = ? AND session_status = 'active' ORDER BY updated_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if latest:
                return latest["id"]
            new_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO chatbot_sessions (id, user_id, session_status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
                (new_id, user_id, now, now),
            )
            return new_id

    def append_chatbot_message(self, session_id: str, sender_type: str, message_text: str) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chatbot_messages (id, session_id, sender_type, message_text, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), session_id, sender_type, message_text, now),
            )
            conn.execute("UPDATE chatbot_sessions SET updated_at = ? WHERE id = ?", (now, session_id))

    def get_chatbot_history(self, user_id: str, session_id: Optional[str]) -> Dict[str, Any]:
        sid = self.get_or_create_chatbot_session(user_id, session_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chatbot_messages WHERE session_id = ? ORDER BY created_at ASC", (sid,)
            ).fetchall()
        return {"session_id": sid, "messages": [dict(r) for r in rows]}

    # --- Phase 6: Blood-Bank Fallback & Request Outcomes (SQLite) ---

    def get_blood_bank_by_id(self, blood_bank_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM blood_banks WHERE id = ? LIMIT 1", (blood_bank_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["availability_label"] = AVAILABILITY_LABELS.get(item["availability_status"], "Contact required")
        return item

    def record_blood_bank_contact_attempt(
        self,
        *,
        request_id: str,
        blood_bank_id: str,
        recorded_by: str,
        outcome: str,
        notes: Optional[str],
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        att_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO blood_bank_contact_attempts (
                    id, request_id, blood_bank_id, recorded_by, outcome, notes, attempted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (att_id, request_id, blood_bank_id, recorded_by, outcome, notes, now),
            )
            if outcome == "confirmed_available":
                conn.execute(
                    """
                    UPDATE blood_banks
                    SET availability_status = 'availability_confirmed_by_facility',
                        last_verified_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, blood_bank_id),
                )
            elif outcome == "unavailable":
                conn.execute(
                    """
                    UPDATE blood_banks
                    SET availability_status = 'availability_unavailable',
                        last_verified_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, blood_bank_id),
                )
            row = conn.execute(
                """
                SELECT a.*, b.facility_name, b.city
                FROM blood_bank_contact_attempts a
                JOIN blood_banks b ON b.id = a.blood_bank_id
                WHERE a.id = ?
                """,
                (att_id,),
            ).fetchone()
        return dict(row)

    def list_blood_bank_contact_attempts(self, request_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT a.*, b.facility_name, b.city, b.phone
                FROM blood_bank_contact_attempts a
                JOIN blood_banks b ON b.id = a.blood_bank_id
                WHERE a.request_id = ?
                ORDER BY a.attempted_at DESC
                """,
                (request_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_request_outcome(
        self,
        *,
        request_row: Dict[str, Any],
        changed_by: str,
        outcome: str,
        donated_by_donor_id: Optional[str] = None,
        notes: Optional[str],
        cooldown_days: int = 90,
    ) -> Dict[str, Any]:
        request_id = str(request_row["id"])
        prev_status = request_row["status"]
        now = _utc_now_iso()
        today_str = datetime.now().date().isoformat()
        note_text = notes or f"Request outcome recorded as {outcome}."

        with self._connect() as conn:
            conn.execute(
                "UPDATE blood_requests SET status = ?, updated_at = ? WHERE id = ?",
                (outcome, now, request_id),
            )
            conn.execute(
                """
                INSERT INTO request_status_history (
                    id, request_id, previous_status, new_status, changed_by, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), request_id, prev_status, outcome, changed_by, note_text, now),
            )
            if outcome == "fulfilled" and donated_by_donor_id:
                donor_row = conn.execute(
                    "SELECT id, user_id FROM donor_profiles WHERE id = ? LIMIT 1",
                    (donated_by_donor_id,),
                ).fetchone()
                if donor_row:
                    frozen_until, freeze_reason = _compute_freeze_fields(today_str, cooldown_days)
                    conn.execute(
                        """
                        UPDATE donor_profiles
                        SET last_donation_date = ?, donor_frozen_until = ?, donor_freeze_reason = ?,
                            availability_status = 'unavailable', updated_at = ?
                        WHERE id = ?
                        """,
                        (today_str, frozen_until, freeze_reason, now, donor_row["id"]),
                    )
                    self._create_notification(
                        conn,
                        user_id=donor_row["user_id"],
                        notification_type="request_status_update",
                        title="Thank You for Donating — 3-Month Cooldown Active",
                        message=(
                            f"Your successful donation has been recorded. Your donor profile is frozen until "
                            f"{frozen_until} (90 days) for safety and recovery."
                        ),
                        related_request_id=request_id,
                    )
            matched_users = conn.execute(
                """
                SELECT DISTINCT dp.user_id
                FROM donor_matches dm
                JOIN donor_profiles dp ON dp.id = dm.donor_id
                WHERE dm.request_id = ?
                """,
                (request_id,),
            ).fetchall()
            for u in matched_users:
                self._create_notification(
                    conn,
                    user_id=u["user_id"],
                    notification_type="request_status_update",
                    title=f"Blood Request Marked {outcome.title()}",
                    message=f"The blood request for {request_row['blood_group']} at {request_row['hospital_name']} has been updated to '{outcome}'.",
                    related_request_id=request_id,
                )
        updated = self.get_blood_request(request_id)
        assert updated is not None
        return updated

    # --- Phase 7: Donor Documents, Admin Moderation, Blood-Bank CRUD & Analytics (SQLite) ---

    def _write_audit_log(
        self,
        conn: sqlite3.Connection,
        *,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: Optional[str],
        metadata_json: str = "{}",
    ) -> None:
        conn.execute(
            """
            INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), actor_id, action, target_type, target_id, metadata_json, _utc_now_iso()),
        )

    def submit_donor_document(
        self, *, donor_id: str, document_type: str, storage_path: str
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        doc_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO donor_documents (
                    id, donor_id, storage_path, document_type, review_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending_review', ?, ?)
                """,
                (doc_id, donor_id, storage_path.strip(), document_type.strip(), now, now),
            )
            conn.execute(
                "UPDATE donor_profiles SET verification_status = 'pending_review', updated_at = ? WHERE id = ?",
                (now, donor_id),
            )
            row = conn.execute("SELECT * FROM donor_documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row)

    def list_donor_documents(self, donor_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM donor_documents WHERE donor_id = ? ORDER BY created_at DESC", (donor_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_donor_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM donor_documents WHERE id = ? LIMIT 1", (doc_id,)).fetchone()
        return dict(row) if row else None

    def get_face_profile_status(self, donor_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT enrolled_at, updated_at FROM donor_face_profiles WHERE donor_id = ? LIMIT 1",
                (donor_id,),
            ).fetchone()
            logs = conn.execute(
                """
                SELECT id, request_id, similarity_score, verified, reason, verified_at
                FROM face_verification_logs
                WHERE donor_id = ?
                ORDER BY verified_at DESC LIMIT 10
                """,
                (donor_id,),
            ).fetchall()
        return {
            "enrolled": row is not None,
            "enrolled_at": row["enrolled_at"] if row else None,
            "updated_at": row["updated_at"] if row else None,
            "recent_verifications": [
                {**dict(l), "verified": bool(l["verified"])} for l in logs
            ],
        }

    def upsert_face_descriptor(self, donor_id: str, descriptor: List[float]) -> Dict[str, Any]:
        import json

        now = _utc_now_iso()
        desc_str = json.dumps(descriptor)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM donor_face_profiles WHERE donor_id = ? LIMIT 1", (donor_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE donor_face_profiles SET descriptor_json = ?, updated_at = ? WHERE donor_id = ?",
                    (desc_str, now, donor_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO donor_face_profiles (id, donor_id, descriptor_json, consent_given, enrolled_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (str(uuid.uuid4()), donor_id, desc_str, now, now),
                )
        return self.get_face_profile_status(donor_id)

    def get_face_descriptor(self, donor_id: str) -> Optional[List[float]]:
        import json

        with self._connect() as conn:
            row = conn.execute(
                "SELECT descriptor_json FROM donor_face_profiles WHERE donor_id = ? LIMIT 1", (donor_id,)
            ).fetchone()
        if not row:
            return None
        return json.loads(row["descriptor_json"])

    def log_face_verification(
        self,
        *,
        donor_id: str,
        request_id: Optional[str],
        similarity_score: float,
        verified: bool,
        reason: str,
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        log_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO face_verification_logs (
                    id, donor_id, request_id, similarity_score, verified, reason, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (log_id, donor_id, request_id, similarity_score, int(verified), reason, now),
            )
        return {
            "id": log_id,
            "request_id": request_id,
            "similarity_score": similarity_score,
            "verified": verified,
            "reason": reason,
            "verified_at": now,
        }

    def upsert_donor_tracking(
        self,
        *,
        request_id: str,
        donor_id: str,
        zone_lat: float,
        zone_lon: float,
        radius_meters: int,
        tracking_status: str,
        distance_band: str,
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM donor_location_tracking WHERE request_id = ? AND donor_id = ? LIMIT 1",
                (request_id, donor_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE donor_location_tracking
                    SET zone_lat = ?, zone_lon = ?, radius_meters = ?, tracking_status = ?,
                        distance_band = ?, is_active = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (zone_lat, zone_lon, radius_meters, tracking_status, distance_band, now, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO donor_location_tracking (
                        id, request_id, donor_id, zone_lat, zone_lon, radius_meters,
                        tracking_status, distance_band, is_active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        request_id,
                        donor_id,
                        zone_lat,
                        zone_lon,
                        radius_meters,
                        tracking_status,
                        distance_band,
                        now,
                        now,
                    ),
                )
        rows = self.list_tracking_for_request(request_id)
        return next(r for r in rows if r["donor_id"] == donor_id)

    def stop_donor_tracking(self, *, request_id: str, donor_id: str) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE donor_location_tracking
                SET tracking_status = 'stopped', is_active = 0, updated_at = ?
                WHERE request_id = ? AND donor_id = ?
                """,
                (now, request_id, donor_id),
            )

    def list_tracking_for_request(self, request_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT t.*, p.full_name
                FROM donor_location_tracking t
                JOIN donor_profiles dp ON dp.id = t.donor_id
                JOIN profiles p ON p.id = dp.user_id
                WHERE t.request_id = ?
                ORDER BY t.updated_at DESC
                """,
                (request_id,),
            ).fetchall()
        return [
            {
                "request_id": r["request_id"],
                "donor_id": r["donor_id"],
                "donor_display_name": mask_display_name(r["full_name"]),
                "zone_lat": float(r["zone_lat"]),
                "zone_lon": float(r["zone_lon"]),
                "radius_meters": int(r["radius_meters"]),
                "tracking_status": r["tracking_status"],
                "distance_band": r["distance_band"],
                "is_active": bool(r["is_active"]),
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def has_verified_face_for_request(self, donor_id: str, request_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM face_verification_logs
                WHERE donor_id = ? AND request_id = ? AND verified = 1
                LIMIT 1
                """,
                (donor_id, request_id),
            ).fetchone()
        return row is not None

    def store_donor_document_bytes(
        self,
        *,
        donor_id: str,
        safe_filename: str,
        content_bytes: bytes,
        content_type: str,
        settings: Settings,
    ) -> str:
        if settings.is_google_drive_upload_enabled:
            from backend.app.services.google_drive import upload_bytes_to_drive_folder

            try:
                file_id = upload_bytes_to_drive_folder(
                    service_account_file=settings.google_drive_service_account_file,
                    folder_id=settings.resolved_google_drive_folder_id,
                    filename=f"{donor_id}_{safe_filename}",
                    content_bytes=content_bytes,
                    content_type=content_type,
                )
                return f"gdrive:{file_id}"
            except Exception as exc:
                raise DatabaseUnavailableError(f"Google Drive upload failed: {exc}") from exc

        target_dir = Path(settings.upload_dir) / donor_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = (target_dir / safe_filename).resolve()
        target_file.write_bytes(content_bytes)
        return str(Path(donor_id) / safe_filename).replace("\\", "/")

    def read_donor_document_bytes(self, storage_path: str, settings: Settings) -> Optional[bytes]:
        if storage_path.startswith("gdrive:") and settings.is_google_drive_upload_enabled:
            from backend.app.services.google_drive import download_bytes_from_drive

            file_id = storage_path.split("gdrive:", 1)[1]
            return download_bytes_from_drive(
                service_account_file=settings.google_drive_service_account_file,
                file_id=file_id,
            )
        base = Path(settings.upload_dir).resolve()
        candidate = (base / storage_path).resolve()
        if base not in candidate.parents or not candidate.is_file():
            return None
        return candidate.read_bytes()

    def admin_update_user_status(
        self, *, user_id: str, account_status: str, admin_id: str, reason: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        now = _utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE profiles SET account_status = ?, updated_at = ? WHERE id = ?",
                (account_status, now, user_id),
            )
            if cur.rowcount == 0:
                return None
            self._write_audit_log(
                conn,
                actor_id=admin_id,
                action=f"user_{account_status}",
                target_type="profile",
                target_id=user_id,
                metadata_json=reason or "{}",
            )
        return self.get_profile_by_id(user_id)

    def admin_list_donor_documents(self, review_status: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = """
            SELECT dd.*, dp.blood_group, p.full_name, p.city
            FROM donor_documents dd
            JOIN donor_profiles dp ON dp.id = dd.donor_id
            JOIN profiles p ON p.id = dp.user_id
            WHERE 1=1
        """
        params: List[Any] = []
        if review_status:
            sql += " AND dd.review_status = ?"
            params.append(review_status)
        sql += " ORDER BY dd.created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def admin_review_donor_document(
        self, *, doc_id: str, review_status: str, admin_id: str, notes: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        now = _utc_now_iso()
        with self._connect() as conn:
            doc = conn.execute("SELECT * FROM donor_documents WHERE id = ? LIMIT 1", (doc_id,)).fetchone()
            if not doc:
                return None
            conn.execute(
                "UPDATE donor_documents SET review_status = ?, reviewed_by = ?, updated_at = ? WHERE id = ?",
                (review_status, admin_id, now, doc_id),
            )
            conn.execute(
                "UPDATE donor_profiles SET verification_status = ?, updated_at = ? WHERE id = ?",
                (review_status, now, doc["donor_id"]),
            )
            self._write_audit_log(
                conn,
                actor_id=admin_id,
                action=f"document_{review_status}",
                target_type="donor_document",
                target_id=doc_id,
                metadata_json=notes or "{}",
            )
            updated = conn.execute("SELECT * FROM donor_documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(updated)

    def admin_list_requests(
        self,
        *,
        status_filter: Optional[str] = None,
        blood_group: Optional[str] = None,
        city: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT br.*, p.full_name AS requester_name
            FROM blood_requests br
            JOIN profiles p ON p.id = br.requester_id
            WHERE 1=1
        """
        params: List[Any] = []
        if status_filter:
            sql += " AND br.status = ?"
            params.append(status_filter)
        if blood_group:
            sql += " AND br.blood_group = ?"
            params.append(blood_group)
        if city:
            sql += " AND lower(br.city) LIKE ?"
            params.append(f"%{city.strip().lower()}%")
        sql += " ORDER BY br.created_at DESC LIMIT 100"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def admin_moderate_request(
        self, *, request_row: Dict[str, Any], new_status: str, notes: str, admin_id: str
    ) -> Dict[str, Any]:
        request_id = str(request_row["id"])
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE blood_requests SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, request_id),
            )
            conn.execute(
                """
                INSERT INTO request_status_history (
                    id, request_id, previous_status, new_status, changed_by, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), request_id, request_row["status"], new_status, admin_id, f"[Admin] {notes}", now),
            )
            self._write_audit_log(
                conn,
                actor_id=admin_id,
                action=f"request_moderated_{new_status}",
                target_type="blood_request",
                target_id=request_id,
                metadata_json=notes,
            )
        updated = self.get_blood_request(request_id)
        assert updated is not None
        return updated

    def admin_list_reports(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM reports WHERE 1=1"
        params: List[Any] = []
        if status_filter:
            sql += " AND status = ?"
            params.append(status_filter)
        sql += " ORDER BY created_at DESC LIMIT 100"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def admin_update_report(self, *, report_id: str, status_value: str, admin_id: str) -> Optional[Dict[str, Any]]:
        now = _utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE reports SET status = ?, reviewed_by = ?, updated_at = ? WHERE id = ?",
                (status_value, admin_id, now, report_id),
            )
            if cur.rowcount == 0:
                return None
            self._write_audit_log(
                conn,
                actor_id=admin_id,
                action=f"report_{status_value}",
                target_type="report",
                target_id=report_id,
            )
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        return dict(row)

    def admin_create_blood_bank(self, data: Dict[str, Any], admin_id: str) -> Dict[str, Any]:
        now = _utc_now_iso()
        bank_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO blood_banks (
                    id, facility_name, address, city, phone, website, latitude, longitude,
                    verification_status, availability_status, source, last_verified_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bank_id,
                    data["facility_name"].strip(),
                    data["address"].strip(),
                    data["city"].strip(),
                    data["phone"].strip(),
                    data.get("website"),
                    data.get("latitude"),
                    data.get("longitude"),
                    data["verification_status"],
                    data["availability_status"],
                    data["source"].strip(),
                    now,
                    now,
                    now,
                ),
            )
            self._write_audit_log(
                conn, actor_id=admin_id, action="blood_bank_created", target_type="blood_bank", target_id=bank_id
            )
        bank = self.get_blood_bank_by_id(bank_id)
        assert bank is not None
        return bank

    def admin_update_blood_bank(self, bank_id: str, data: Dict[str, Any], admin_id: str) -> Optional[Dict[str, Any]]:
        now = _utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE blood_banks
                SET facility_name = ?, address = ?, city = ?, phone = ?, website = ?,
                    latitude = ?, longitude = ?, verification_status = ?, availability_status = ?,
                    source = ?, last_verified_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    data["facility_name"].strip(),
                    data["address"].strip(),
                    data["city"].strip(),
                    data["phone"].strip(),
                    data.get("website"),
                    data.get("latitude"),
                    data.get("longitude"),
                    data["verification_status"],
                    data["availability_status"],
                    data["source"].strip(),
                    now,
                    now,
                    bank_id,
                ),
            )
            if cur.rowcount == 0:
                return None
            self._write_audit_log(
                conn, actor_id=admin_id, action="blood_bank_updated", target_type="blood_bank", target_id=bank_id
            )
        return self.get_blood_bank_by_id(bank_id)

    def admin_delete_blood_bank(self, bank_id: str, admin_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM blood_banks WHERE id = ?", (bank_id,))
            if cur.rowcount == 0:
                return False
            self._write_audit_log(
                conn, actor_id=admin_id, action="blood_bank_deleted", target_type="blood_bank", target_id=bank_id
            )
        return True

    def admin_get_analytics(self) -> Dict[str, Any]:
        with self._connect() as conn:
            by_status = {
                r["status"]: r["cnt"]
                for r in conn.execute("SELECT status, COUNT(*) AS cnt FROM blood_requests GROUP BY status").fetchall()
            }
            by_group = {
                r["blood_group"]: r["cnt"]
                for r in conn.execute("SELECT blood_group, COUNT(*) AS cnt FROM blood_requests GROUP BY blood_group").fetchall()
            }
            by_city = {
                r["city"]: r["cnt"]
                for r in conn.execute("SELECT city, COUNT(*) AS cnt FROM blood_requests GROUP BY city").fetchall()
            }
            by_resp = {
                r["response"]: r["cnt"]
                for r in conn.execute("SELECT response, COUNT(*) AS cnt FROM donor_responses GROUP BY response").fetchall()
            }
        return {
            "requests_by_status": by_status,
            "requests_by_blood_group": by_group,
            "requests_by_city": by_city,
            "donor_responses_by_type": by_resp,
            "disclaimer": "Platform operational records only, not clinical outcomes.",
        }

    def admin_list_audit_logs(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 100").fetchall()
        return [dict(r) for r in rows]


class SupabaseRepository(Phase1SupabaseMixin, Phase2SupabaseMixin, Phase3SupabaseMixin):
    """Supabase-backed repository using service-role client solely on the server."""

    def __init__(self, settings: Settings) -> None:
        try:
            from supabase import create_client
        except ImportError as exc:
            raise DatabaseUnavailableError("Supabase client package is not installed.") from exc

        self.settings = settings
        self.client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        self.anon_client = create_client(settings.supabase_url, settings.supabase_anon_key)

    def is_aadhaar_registered(self, aadhaar_hash: str) -> bool:
        try:
            res = self.client.table("profiles").select("id").eq("aadhaar_hash", aadhaar_hash).limit(1).execute()
            return bool(res.data)
        except Exception as exc:
            raise DatabaseUnavailableError(f"Unable to check Aadhaar uniqueness: {exc}") from exc

    def create_user(
        self,
        *,
        full_name: str,
        email: str,
        phone_number: str,
        password: str,
        city: str,
        approximate_location: str,
        date_of_birth: Optional[str],
        role_preference: str,
        blood_group: Optional[str],
        aadhaar_last4: str = "0000",
        aadhaar_hash: Optional[str] = None,
        aadhaar_verified: bool = False,
    ) -> Dict[str, Any]:
        if role_preference not in ("requester", "donor", "hospital"):
            raise ValueError("Public registration only allows 'requester', 'donor', or 'hospital' roles.")

        normalized_phone = normalize_phone(phone_number)
        normalized_email = email.strip().lower()

        auth_user_id: Optional[str] = None
        try:
            existing_prof = (
                self.client.table("profiles")
                .select("id")
                .or_(f"email.eq.{normalized_email},phone_number.eq.{normalized_phone}")
                .limit(1)
                .execute()
            )
            if existing_prof.data:
                raise ConflictError("An account with this email or phone number already exists.")

            try:
                auth_res = self.anon_client.auth.sign_up(
                    {"email": normalized_email, "password": password}
                )
            except Exception as auth_exc:
                amsg = str(auth_exc).lower()
                if "already" in amsg or "registered" in amsg:
                    raise ConflictError("An account with this email or phone number already exists.") from auth_exc
                if "weak" in amsg or "password" in amsg:
                    raise ValueError(
                        "Password is too weak or common. Use at least 8 mixed characters (letters, numbers, symbol)."
                    ) from auth_exc
                if "rate limit" in amsg or "too many" in amsg or "429" in amsg:
                    # Fallback via service_role admin create_user so signup isn't blocked by public 2/hr email quota
                    try:
                        auth_res = self.client.auth.admin.create_user(
                            {"email": normalized_email, "password": password, "email_confirm": True}
                        )
                    except Exception as admin_exc:
                        adm_msg = str(admin_exc).lower()
                        if "already" in adm_msg or "registered" in adm_msg:
                            raise ConflictError("An account with this email or phone number already exists.") from admin_exc
                        raise ValueError(f"Registration failed: {admin_exc}") from admin_exc
                elif "invalid" in amsg or "email" in amsg:
                    raise ValueError(f"Invalid registration details: {auth_exc}") from auth_exc
                else:
                    raise ValueError(f"Authentication provider rejected signup: {auth_exc}") from auth_exc

            if not auth_res.user:
                raise ConflictError("Could not register user with Supabase Auth.")
            auth_user_id = str(auth_res.user.id)

            profile_payload = {
                "auth_user_id": auth_user_id,
                "full_name": full_name.strip(),
                "email": normalized_email,
                "phone_number": normalized_phone,
                "role": role_preference,
                "city": city.strip(),
                "approximate_location": approximate_location.strip(),
                "date_of_birth": date_of_birth,
                "account_status": "active",
                "phone_verified": False,
                "aadhaar_last4": aadhaar_last4,
                "aadhaar_hash": aadhaar_hash,
                "aadhaar_verified": aadhaar_verified,
            }
            if aadhaar_hash is None:
                profile_payload.pop("aadhaar_hash", None)
            res = self.client.table("profiles").insert(profile_payload).execute()
            profile = res.data[0]

            if role_preference == "donor" and blood_group:
                self.client.table("donor_profiles").insert(
                    {
                        "user_id": profile["id"],
                        "blood_group": blood_group,
                        "availability_status": "unavailable",
                        "verification_status": "not_submitted",
                        "emergency_notifications_enabled": True,
                        "profile_completed": True,
                    }
                ).execute()
            return profile
        except (ConflictError, ValueError):
            if auth_user_id:
                try:
                    self.client.auth.admin.delete_user(auth_user_id)
                except Exception:
                    pass
            raise
        except Exception as exc:
            if auth_user_id:
                try:
                    self.client.auth.admin.delete_user(auth_user_id)
                except Exception:
                    pass
            msg = str(exc).lower()
            if "already" in msg or "duplicate" in msg or "unique" in msg:
                raise ConflictError("An account with this email or phone number already exists.") from exc
            raise DatabaseUnavailableError(f"Supabase error during registration: {exc}") from exc

    def save_user_aadhaar_verification(
        self, *, profile_id: str, aadhaar_last4: str, aadhaar_hash: str
    ) -> Optional[Dict[str, Any]]:
        existing = (
            self.client.table("profiles")
            .select("id")
            .eq("aadhaar_hash", aadhaar_hash)
            .neq("id", profile_id)
            .limit(1)
            .execute()
        ).data or []
        if existing:
            raise ConflictError("An account with this Aadhaar number is already registered.")
        res = (
            self.client.table("profiles")
            .update(
                {
                    "aadhaar_last4": aadhaar_last4,
                    "aadhaar_hash": aadhaar_hash,
                    "aadhaar_verified": True,
                    "aadhaar_consent_at": _utc_now_iso(),
                }
            )
            .eq("id", profile_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def authenticate_supabase(self, email: str, password: str) -> Dict[str, Any]:
        try:
            res = self.anon_client.auth.sign_in_with_password(
                {"email": email.strip().lower(), "password": password}
            )
            if not res.user or not res.session:
                raise AuthenticationError("Invalid credentials.")
            profile = self.get_profile_by_auth_user_id(str(res.user.id))
            if not profile:
                raise AuthenticationError("Profile record not found for authenticated account.")
            if profile["account_status"] != "active":
                raise AuthenticationError("This account has been suspended or deactivated.")
            return {"access_token": res.session.access_token, "profile": profile}
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError("Invalid email or password.") from exc

    def set_recovery_hashes(self, profile_id: str, hashes: List[str]) -> None:
        profile = self.get_profile_by_id(profile_id) or {}
        raw = profile.get("accessibility_prefs")
        a11y: Dict[str, Any] = {"text_size": "normal", "high_contrast": False}
        if isinstance(raw, dict):
            a11y.update(raw)
        a11y["recovery_hashes"] = list(hashes)
        self.client.table("profiles").update({"accessibility_prefs": a11y}).eq("id", profile_id).execute()

    def get_recovery_hashes(self, profile_id: str) -> List[str]:
        profile = self.get_profile_by_id(profile_id) or {}
        raw = profile.get("accessibility_prefs")
        if isinstance(raw, dict):
            return [str(x) for x in (raw.get("recovery_hashes") or [])]
        return []

    def recover_password_with_code(
        self, *, identifier: str, code_hash: str, new_password: str
    ) -> Tuple[Dict[str, Any], int]:
        cleaned = identifier.strip()
        if "@" in cleaned:
            rows = (
                self.client.table("profiles").select("*").eq("email", cleaned.lower()).limit(1).execute()
            ).data or []
        else:
            rows = (
                self.client.table("profiles")
                .select("*")
                .eq("phone_number", normalize_phone(cleaned))
                .limit(1)
                .execute()
            ).data or []
        if not rows or rows[0].get("account_status") != "active":
            raise AuthenticationError("Invalid account or recovery code.")

        profile = rows[0]
        profile_id = str(profile["id"])
        hashes = self.get_recovery_hashes(profile_id)
        matched_idx = -1
        for idx, stored in enumerate(hashes):
            if hmac.compare_digest(str(stored), str(code_hash)):
                matched_idx = idx
                break
        if matched_idx < 0:
            raise AuthenticationError("Invalid or already-used recovery code.")

        auth_user_id = str(profile.get("auth_user_id") or "")
        if not auth_user_id:
            raise AuthenticationError("Account authentication linkage is missing.")

        try:
            self.client.auth.admin.update_user_by_id(auth_user_id, {"password": new_password})
        except Exception as exc:
            raise DatabaseUnavailableError(f"Failed to update password in Supabase Auth: {exc}") from exc

        remaining = [h for idx, h in enumerate(hashes) if idx != matched_idx]
        self.set_recovery_hashes(profile_id, remaining)
        return profile, len(remaining)

    def send_password_reset_email(self, email: str) -> None:
        self.anon_client.auth.reset_password_for_email(email.strip().lower())

    def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        try:
            res = self.client.table("profiles").select("*").eq("id", profile_id).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception as exc:
            raise DatabaseUnavailableError(f"Unable to reach Supabase: {exc}") from exc

    def get_profile_by_auth_user_id(self, auth_user_id: str) -> Optional[Dict[str, Any]]:
        try:
            res = (
                self.client.table("profiles")
                .select("*")
                .eq("auth_user_id", auth_user_id)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as exc:
            raise DatabaseUnavailableError(f"Unable to reach Supabase: {exc}") from exc

    def get_user_from_jwt(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            res = self.client.auth.get_user(token)
            if not res or not res.user:
                return None
            return self.get_profile_by_auth_user_id(str(res.user.id))
        except Exception:
            return None

    def update_profile(self, profile_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"full_name", "city", "approximate_location"}
        filtered = {k: v.strip() for k, v in updates.items() if k in allowed and v is not None}
        if not filtered:
            return self.get_profile_by_id(profile_id)
        try:
            res = self.client.table("profiles").update(filtered).eq("id", profile_id).execute()
            return res.data[0] if res.data else None
        except Exception as exc:
            raise DatabaseUnavailableError(f"Unable to update profile: {exc}") from exc

    def search_public_donors(
        self, blood_group: Optional[str] = None, city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        try:
            query = (
                self.client.table("donor_profiles")
                .select(
                    "id, blood_group, availability_status, verification_status, donor_frozen_until, "
                    "profiles!inner(full_name, city, approximate_location, account_status)"
                )
                .neq("availability_status", "unavailable")
            )
            if blood_group:
                query = query.eq("blood_group", blood_group)
            res = query.limit(50).execute()
            today_str = datetime.now().date().isoformat()
            items: List[Dict[str, Any]] = []
            for row in res.data or []:
                if row.get("donor_frozen_until") and str(row["donor_frozen_until"])[:10] > today_str:
                    continue
                prof = row.get("profiles") or {}
                if prof.get("account_status") != "active":
                    continue
                if city and city.strip().lower() not in (prof.get("city") or "").lower():
                    continue
                items.append(
                    {
                        "donor_id": row["id"],
                        "display_name": mask_display_name(prof.get("full_name", "")),
                        "blood_group": row["blood_group"],
                        "city": prof.get("city", ""),
                        "approximate_location": prof.get("approximate_location", ""),
                        "availability_status": row["availability_status"],
                        "verification_status": row["verification_status"],
                        "match_label": "Potential match (medical eligibility determined by blood bank)",
                    }
                )
            return items
        except Exception as exc:
            raise DatabaseUnavailableError(f"Unable to search donors: {exc}") from exc

    def search_blood_banks(
        self, city: Optional[str] = None, query_text: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        try:
            query = self.client.table("blood_banks").select("*")
            if city:
                query = query.ilike("city", f"%{city.strip()}%")
            res = query.order("facility_name").limit(50).execute()
            items = []
            for row in res.data or []:
                if query_text:
                    qt = query_text.strip().lower()
                    if qt not in row["facility_name"].lower() and qt not in row["address"].lower():
                        continue
                row["availability_label"] = AVAILABILITY_LABELS.get(
                    row.get("availability_status", "contact_required"), "Contact required"
                )
                items.append(row)
            return items
        except Exception as exc:
            raise DatabaseUnavailableError(f"Unable to query blood banks: {exc}") from exc

    def get_admin_overview(self) -> Dict[str, Any]:
        try:
            def _count(table: str, filters: Optional[Dict[str, Any]] = None) -> int:
                q = self.client.table(table).select("id", count="exact")
                for col, val in (filters or {}).items():
                    q = q.eq(col, val)
                res = q.execute()
                return res.count or 0

            return {
                "total_users": _count("profiles"),
                "total_donors": _count("donor_profiles"),
                "verified_donors": _count("donor_profiles", {"verification_status": "verified"}),
                "active_requests": len(
                    (
                        self.client.table("blood_requests")
                        .select("id")
                        .not_.in_("status", ["fulfilled", "unresolved", "cancelled", "expired"])
                        .execute()
                    ).data
                    or []
                ),
                "fulfilled_requests": _count("blood_requests", {"status": "fulfilled"}),
                "unresolved_requests": _count("blood_requests", {"status": "unresolved"}),
                "pending_document_reviews": _count("donor_documents", {"review_status": "pending_review"}),
                "open_reports": len(
                    (
                        self.client.table("reports")
                        .select("id")
                        .in_("status", ["open", "under_review"])
                        .execute()
                    ).data
                    or []
                ),
                "blood_banks_count": _count("blood_banks"),
                "disclaimer": "Platform operational records only, not clinical outcomes.",
            }
        except Exception as exc:
            raise DatabaseUnavailableError(f"Unable to load admin metrics: {exc}") from exc

    def list_users_for_admin(
        self, role: Optional[str] = None, search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        try:
            query = self.client.table("profiles").select(
                "id, full_name, email, phone_number, role, city, approximate_location, "
                "account_status, phone_verified, aadhaar_last4, aadhaar_verified, created_at"
            )
            if role:
                query = query.eq("role", role)
            res = query.order("created_at", desc=True).limit(100).execute()
            rows = res.data or []
            for r in rows:
                last4 = r.pop("aadhaar_last4", "0000") or "0000"
                r["aadhaar_masked"] = f"XXXX-XXXX-{last4}"
            if search:
                q = search.strip().lower()
                rows = [
                    r
                    for r in rows
                    if q in (r.get("full_name") or "").lower()
                    or q in (r.get("email") or "").lower()
                    or q in (r.get("city") or "").lower()
                ]
            return rows
        except Exception as exc:
            raise DatabaseUnavailableError(f"Unable to list users: {exc}") from exc

    # --- Phase 2: Donor & Request Methods (Supabase) ---

    def get_donor_profile_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        res = self.client.table("donor_profiles").select("*").eq("user_id", user_id).limit(1).execute()
        return res.data[0] if res.data else None

    def upsert_donor_profile(
        self,
        *,
        user_id: str,
        blood_group: str,
        availability_status: str,
        last_donation_date: Optional[str],
        preferred_contact_method: str,
        emergency_notifications_enabled: bool,
        cooldown_days: int = 90,
    ) -> Dict[str, Any]:
        existing = self.get_donor_profile_by_user_id(user_id)
        frozen_until, freeze_reason = _compute_freeze_fields(last_donation_date, cooldown_days)
        payload = {
            "blood_group": blood_group,
            "availability_status": "unavailable" if frozen_until else availability_status,
            "last_donation_date": last_donation_date,
            "donor_frozen_until": frozen_until,
            "donor_freeze_reason": freeze_reason,
            "preferred_contact_method": preferred_contact_method,
            "emergency_notifications_enabled": emergency_notifications_enabled,
            "profile_completed": True,
        }
        if existing:
            res = self.client.table("donor_profiles").update(payload).eq("user_id", user_id).execute()
        else:
            payload["user_id"] = user_id
            payload["verification_status"] = "not_submitted"
            res = self.client.table("donor_profiles").insert(payload).execute()
        return res.data[0]

    def update_donor_availability(
        self,
        *,
        user_id: str,
        availability_status: str,
        emergency_notifications_enabled: Optional[bool],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"availability_status": availability_status}
        if emergency_notifications_enabled is not None:
            payload["emergency_notifications_enabled"] = emergency_notifications_enabled
        res = self.client.table("donor_profiles").update(payload).eq("user_id", user_id).execute()
        return res.data[0]

    def update_donor_history(
        self, *, user_id: str, last_donation_date: Optional[str], cooldown_days: int = 90
    ) -> Dict[str, Any]:
        frozen_until, freeze_reason = _compute_freeze_fields(last_donation_date, cooldown_days)
        updates: Dict[str, Any] = {
            "last_donation_date": last_donation_date,
            "donor_frozen_until": frozen_until,
            "donor_freeze_reason": freeze_reason,
        }
        if frozen_until:
            updates["availability_status"] = "unavailable"
        res = (
            self.client.table("donor_profiles")
            .update(updates)
            .eq("user_id", user_id)
            .execute()
        )
        return res.data[0]

    def create_blood_request(
        self,
        *,
        requester_id: str,
        patient_reference_name: str,
        blood_group: str,
        units_requested: int,
        hospital_name: str,
        hospital_location: str,
        city: str,
        approximate_location: str,
        urgency: str,
        additional_information: Optional[str],
        requester_contact_preference: str,
        requested_for: str,
        expires_at: str,
        is_emergency_quick: bool = False,
        coordinator_contact_name: Optional[str] = None,
        coordinator_contact_relation: Optional[str] = None,
        hospital_id: Optional[str] = None,
        created_by_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = (
            self.client.table("blood_requests")
            .select("id")
            .eq("requester_id", requester_id)
            .eq("blood_group", blood_group)
            .ilike("city", city.strip())
            .not_.in_("status", ["fulfilled", "unresolved", "cancelled", "expired"])
            .limit(1)
            .execute()
        )
        if existing.data:
            raise ConflictError(
                "You already have an active blood request for this blood group and city."
            )
        insert_data: Dict[str, Any] = {
            "requester_id": requester_id,
            "created_by_user_id": created_by_user_id or requester_id,
            "patient_reference_name": patient_reference_name.strip(),
            "blood_group": blood_group,
            "units_requested": units_requested,
            "hospital_name": hospital_name.strip(),
            "hospital_location": hospital_location.strip(),
            "city": city.strip(),
            "approximate_location": approximate_location.strip(),
            "urgency": urgency,
            "additional_information": additional_information.strip() if additional_information else None,
            "requester_contact_preference": requester_contact_preference,
            "consent_given": True,
            "status": "created",
            "escalation_stage": 1,
            "is_emergency_quick": is_emergency_quick,
            "coordinator_contact_name": coordinator_contact_name.strip() if coordinator_contact_name else None,
            "coordinator_contact_relation": coordinator_contact_relation.strip() if coordinator_contact_relation else None,
            "requested_for": requested_for,
            "expires_at": expires_at,
        }
        if hospital_id:
            insert_data["hospital_id"] = hospital_id
        res = self.client.table("blood_requests").insert(insert_data).execute()
        req = res.data[0]
        self.client.table("request_status_history").insert(
            {
                "request_id": req["id"],
                "previous_status": None,
                "new_status": "created",
                "changed_by": requester_id,
                "notes": "Blood request created by requester.",
            }
        ).execute()
        return req

    def expire_stale_requests(self) -> int:
        now = _utc_now_iso()
        stale = (
            self.client.table("blood_requests")
            .select("id, status, requester_id, blood_group, hospital_name")
            .lte("expires_at", now)
            .not_.in_("status", ["fulfilled", "unresolved", "cancelled", "expired"])
            .execute()
        ).data or []
        for row in stale:
            self.client.table("blood_requests").update({"status": "expired"}).eq("id", row["id"]).execute()
            self.client.table("request_status_history").insert(
                {
                    "request_id": row["id"],
                    "previous_status": row["status"],
                    "new_status": "expired",
                    "notes": "Request expired automatically after configured window.",
                }
            ).execute()
            self.client.table("notifications").insert(
                {
                    "user_id": row["requester_id"],
                    "notification_type": "request_expired",
                    "title": "Blood Request Expired",
                    "message": "Your blood request has expired and alerts have been stopped.",
                    "related_request_id": row["id"],
                    "delivery_status": "saved",
                }
            ).execute()
            self._close_request_side_effects_supabase(
                request_id=row["id"],
                notification_type="request_expired",
                title="Blood Request Expired — Alert Closed",
                message=f"The {row['blood_group']} request at {row['hospital_name']} has expired.",
                new_match_status="expired",
            )
        return len(stale)

    def list_requests_for_user(self, requester_id: str) -> List[Dict[str, Any]]:
        res = (
            self.client.table("blood_requests")
            .select("*")
            .eq("requester_id", requester_id)
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []

    def get_blood_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        res = self.client.table("blood_requests").select("*").eq("id", request_id).limit(1).execute()
        return res.data[0] if res.data else None

    def is_donor_matched_to_request(self, user_id: str, request_id: str) -> bool:
        donor = self.get_donor_profile_by_user_id(user_id)
        if not donor:
            return False
        res = (
            self.client.table("donor_matches")
            .select("id")
            .eq("request_id", request_id)
            .eq("donor_id", donor["id"])
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def update_blood_request(
        self, *, request_id: str, changed_by: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        req = self.get_blood_request(request_id)
        res = self.client.table("blood_requests").update(updates).eq("id", request_id).execute()
        self.client.table("request_status_history").insert(
            {
                "request_id": request_id,
                "previous_status": req["status"] if req else None,
                "new_status": req["status"] if req else "created",
                "changed_by": changed_by,
                "notes": "Request details updated by requester.",
            }
        ).execute()
        return res.data[0]

    def cancel_blood_request(self, *, request_id: str, changed_by: str, reason: str) -> Dict[str, Any]:
        req = self.get_blood_request(request_id)
        res = (
            self.client.table("blood_requests")
            .update({"status": "cancelled", "cancellation_reason": reason})
            .eq("id", request_id)
            .execute()
        )
        self.client.table("request_status_history").insert(
            {
                "request_id": request_id,
                "previous_status": req["status"] if req else None,
                "new_status": "cancelled",
                "changed_by": changed_by,
                "notes": reason,
            }
        ).execute()
        if req:
            self._close_request_side_effects_supabase(
                request_id=request_id,
                notification_type="request_cancelled",
                title="Blood Request Cancelled",
                message=f"The {req['blood_group']} request at {req['hospital_name']} has been cancelled ({reason}).",
                new_match_status="skipped",
            )
        return res.data[0]

    def get_request_status_history(self, request_id: str) -> List[Dict[str, Any]]:
        res = (
            self.client.table("request_status_history")
            .select("*")
            .eq("request_id", request_id)
            .order("created_at")
            .execute()
        )
        return res.data or []

    # --- Phase 3: Matching, Escalation, Responses & Notifications (Supabase) ---

    def run_matching_for_request(
        self,
        *,
        request_row: Dict[str, Any],
        actor_id: str,
        stage: int,
        max_new_notifications: int,
        review_interval_days: int,
    ) -> Dict[str, Any]:
        from backend.app.services.matching import score_candidate

        request_id = str(request_row["id"])
        allow_wider = stage >= 3
        existing = (
            self.client.table("donor_matches").select("donor_id").eq("request_id", request_id).execute()
        ).data or []
        already_matched = {r["donor_id"] for r in existing}

        donors = (
            self.client.table("donor_profiles")
            .select("*, profiles!inner(full_name, city, approximate_location, account_status)")
            .execute()
        ).data or []

        scored: List[tuple[float, Dict[str, Any], str]] = []
        for d in donors:
            prof = d.get("profiles") or {}
            merged = {**d, **prof}
            if d["id"] in already_matched:
                continue
            eligible, score, reason = score_candidate(
                request_row=request_row,
                donor_row=merged,
                allow_wider_city=allow_wider,
                review_interval_days=review_interval_days,
            )
            if eligible:
                scored.append((score, merged, reason))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = scored[:max_new_notifications]

        for score, donor_d, reason in selected:
            self.client.table("donor_matches").insert(
                {
                    "request_id": request_id,
                    "donor_id": donor_d["id"],
                    "priority_score": score,
                    "match_reason": reason,
                    "match_status": "notified",
                    "escalation_stage": stage,
                }
            ).execute()
            self.client.table("notifications").insert(
                {
                    "user_id": donor_d["user_id"],
                    "notification_type": "new_request_alert",
                    "title": f"{request_row['blood_group']} Blood Request ({request_row['urgency'].upper()})",
                    "message": f"{request_row['units_requested']} unit(s) needed at {request_row['hospital_name']}, {request_row['city']}.",
                    "related_request_id": request_id,
                    "delivery_status": "saved",
                }
            ).execute()

        total_candidates = len(already_matched) + len(selected)
        prev_status = request_row["status"]
        if selected:
            new_status = "escalation_in_progress" if stage >= 3 else "donors_notified"
            new_stage = stage
            note = f"Stage {stage}: Notified {len(selected)} potential donor candidate(s)."
        elif total_candidates == 0:
            new_status = "blood_bank_assistance"
            new_stage = 4
            note = "No matching available donors found; escalated to Stage 4 Blood-Bank Assistance."
        else:
            new_status = "escalation_in_progress" if stage >= 3 else prev_status
            new_stage = stage
            note = f"Stage {stage} escalation ran; no additional unnotified candidates found."

        self.client.table("blood_requests").update(
            {"status": new_status, "escalation_stage": new_stage}
        ).eq("id", request_id).execute()
        self.client.table("request_status_history").insert(
            {
                "request_id": request_id,
                "previous_status": prev_status,
                "new_status": new_status,
                "changed_by": actor_id,
                "notes": note,
            }
        ).execute()

        return {
            "request_id": request_id,
            "request_status": new_status,
            "escalation_stage": new_stage,
            "newly_notified_count": len(selected),
            "total_candidates_count": total_candidates,
            "candidates": self.list_matches_for_request(request_id),
            "message": note,
        }

    def escalate_to_fallback_stage(
        self, *, request_row: Dict[str, Any], actor_id: str, target_stage: int
    ) -> Dict[str, Any]:
        request_id = str(request_row["id"])
        prev_status = request_row["status"]
        new_status = "blood_bank_assistance" if target_stage == 4 else "escalation_in_progress"
        note = (
            "Stage 4: Blood-Bank Assistance activated."
            if target_stage == 4
            else "Stage 5: Hospital-coordinated wider search."
        )
        self.client.table("blood_requests").update(
            {"status": new_status, "escalation_stage": target_stage}
        ).eq("id", request_id).execute()
        self.client.table("request_status_history").insert(
            {
                "request_id": request_id,
                "previous_status": prev_status,
                "new_status": new_status,
                "changed_by": actor_id,
                "notes": note,
            }
        ).execute()
        candidates = self.list_matches_for_request(request_id)
        return {
            "request_id": request_id,
            "request_status": new_status,
            "escalation_stage": target_stage,
            "newly_notified_count": 0,
            "total_candidates_count": len(candidates),
            "candidates": candidates,
            "message": note,
        }

    def list_matches_for_request(self, request_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.client.table("donor_matches")
            .select(
                "*, donor_profiles!inner(blood_group, availability_status, verification_status, "
                "profiles!inner(full_name, city, approximate_location))"
            )
            .eq("request_id", request_id)
            .order("priority_score", desc=True)
            .execute()
        ).data or []
        out = []
        for r in rows:
            dp = r.get("donor_profiles") or {}
            prof = dp.get("profiles") or {}
            out.append(
                {
                    "id": r["id"],
                    "request_id": r["request_id"],
                    "donor_id": r["donor_id"],
                    "donor_display_name": mask_display_name(prof.get("full_name", "")),
                    "blood_group": dp.get("blood_group", ""),
                    "city": prof.get("city", ""),
                    "approximate_location": prof.get("approximate_location", ""),
                    "availability_status": dp.get("availability_status", ""),
                    "verification_status": dp.get("verification_status", ""),
                    "priority_score": float(r["priority_score"]),
                    "match_reason": r["match_reason"],
                    "match_status": r["match_status"],
                    "escalation_stage": int(r["escalation_stage"]),
                    "created_at": str(r["created_at"]),
                }
            )
        return out

    def list_incoming_requests_for_donor(self, user_id: str) -> List[Dict[str, Any]]:
        donor = self.get_donor_profile_by_user_id(user_id)
        if not donor:
            return []
        rows = (
            self.client.table("donor_matches")
            .select("*, blood_requests!inner(*)")
            .eq("donor_id", donor["id"])
            .order("created_at", desc=True)
            .execute()
        ).data or []
        out = []
        for r in rows:
            br = r.get("blood_requests") or {}
            resp = (
                self.client.table("donor_responses")
                .select("response")
                .eq("request_id", br["id"])
                .eq("donor_id", donor["id"])
                .limit(1)
                .execute()
            ).data
            conv = (
                self.client.table("conversations")
                .select("id")
                .eq("request_id", br["id"])
                .eq("donor_id", user_id)
                .limit(1)
                .execute()
            ).data
            out.append(
                {
                    "match_id": r["id"],
                    "request_id": br["id"],
                    "blood_group": br["blood_group"],
                    "units_requested": br["units_requested"],
                    "hospital_name": br["hospital_name"],
                    "hospital_location": br["hospital_location"],
                    "city": br["city"],
                    "approximate_location": br["approximate_location"],
                    "urgency": br["urgency"],
                    "request_status": br["status"],
                    "match_status": r["match_status"],
                    "priority_score": float(r["priority_score"]),
                    "match_reason": r["match_reason"],
                    "expires_at": str(br["expires_at"]),
                    "my_response": resp[0]["response"] if resp else None,
                    "conversation_id": conv[0]["id"] if conv else None,
                }
            )
        return out

    def record_donor_response(
        self,
        *,
        request_row: Dict[str, Any],
        donor_profile: Dict[str, Any],
        donor_user: Dict[str, Any],
        response_value: str,
    ) -> Dict[str, Any]:
        request_id = str(request_row["id"])
        donor_id = str(donor_profile["id"])
        res = (
            self.client.table("donor_responses")
            .upsert(
                {"request_id": request_id, "donor_id": donor_id, "response": response_value},
                on_conflict="request_id,donor_id",
            )
            .execute()
        ).data[0]
        self.client.table("donor_matches").update({"match_status": response_value}).eq(
            "request_id", request_id
        ).eq("donor_id", donor_id).execute()

        conv_id = None
        if response_value == "accepted":
            conv_existing = (
                self.client.table("conversations")
                .select("id")
                .eq("request_id", request_id)
                .eq("requester_id", request_row["requester_id"])
                .eq("donor_id", donor_user["id"])
                .limit(1)
                .execute()
            ).data
            if conv_existing:
                conv_id = conv_existing[0]["id"]
            else:
                conv_id = (
                    self.client.table("conversations")
                    .insert(
                        {
                            "request_id": request_id,
                            "requester_id": request_row["requester_id"],
                            "donor_id": donor_user["id"],
                            "status": "active",
                        }
                    )
                    .execute()
                ).data[0]["id"]
                self.client.table("contact_sharing_consents").insert(
                    {
                        "request_id": request_id,
                        "requester_id": request_row["requester_id"],
                        "donor_id": donor_user["id"],
                        "status": "pending",
                    }
                ).execute()
            self.client.table("blood_requests").update({"status": "connection_in_progress"}).eq(
                "id", request_id
            ).execute()
        else:
            self.client.table("blood_requests").update({"status": "responses_received"}).eq(
                "id", request_id
            ).execute()

        return {
            "id": res["id"],
            "request_id": request_id,
            "donor_id": donor_id,
            "donor_display_name": mask_display_name(donor_user["full_name"]),
            "blood_group": donor_profile["blood_group"],
            "response": response_value,
            "responded_at": str(res["responded_at"]),
            "conversation_id": conv_id,
        }

    def list_responses_for_request(self, request_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.client.table("donor_responses")
            .select("*, donor_profiles!inner(blood_group, user_id, profiles!inner(full_name))")
            .eq("request_id", request_id)
            .execute()
        ).data or []
        out = []
        for r in rows:
            dp = r.get("donor_profiles") or {}
            prof = dp.get("profiles") or {}
            out.append(
                {
                    "id": r["id"],
                    "request_id": r["request_id"],
                    "donor_id": r["donor_id"],
                    "donor_display_name": mask_display_name(prof.get("full_name", "")),
                    "blood_group": dp.get("blood_group", ""),
                    "response": r["response"],
                    "responded_at": str(r["responded_at"]),
                    "conversation_id": None,
                }
            )
        return out

    def list_notifications(self, user_id: str) -> List[Dict[str, Any]]:
        res = (
            self.client.table("notifications")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        return res.data or []

    def mark_notification_read(self, notification_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        res = (
            self.client.table("notifications")
            .update({"read_at": _utc_now_iso()})
            .eq("id", notification_id)
            .eq("user_id", user_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def mark_all_notifications_read(self, user_id: str) -> int:
        res = (
            self.client.table("notifications")
            .update({"read_at": _utc_now_iso()})
            .eq("user_id", user_id)
            .is_("read_at", "null")
            .execute()
        )
        return len(res.data or [])

    # --- Phase 4: Private Communication, Contact Consent & Reports (Supabase) ---

    def _hydrate_supabase_conv(self, row: Dict[str, Any], current_user_id: str) -> Dict[str, Any]:
        is_req = row["requester_id"] == current_user_id
        is_don = row["donor_id"] == current_user_id
        other_id = row["donor_id"] if (is_req or not is_don) else row["requester_id"]
        other = self.get_profile_by_id(other_id)
        req = self.get_blood_request(row["request_id"])
        unread_rows = (
            self.client.table("messages")
            .select("id")
            .eq("conversation_id", row["id"])
            .neq("sender_id", current_user_id)
            .is_("read_at", "null")
            .execute()
        ).data or []
        return {
            "id": row["id"],
            "request_id": row["request_id"],
            "blood_group": req["blood_group"] if req else "",
            "hospital_name": req["hospital_name"] if req else "",
            "city": req["city"] if req else "",
            "counterpart_user_id": other_id,
            "counterpart_display_name": mask_display_name(other["full_name"]) if other else "Participant",
            "my_role": "requester" if is_req else ("donor" if is_don else "coordinator"),
            "status": row["status"],
            "unread_count": len(unread_rows),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def list_conversations_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.client.table("conversations")
            .select("*")
            .or_(f"requester_id.eq.{user_id},donor_id.eq.{user_id}")
            .order("updated_at", desc=True)
            .execute()
        ).data or []
        coord_reqs = (
            self.client.table("request_coordinators")
            .select("request_id")
            .eq("coordinator_user_id", user_id)
            .eq("status", "active")
            .eq("can_chat", True)
            .execute()
        ).data or []
        coord_ids = [r["request_id"] for r in coord_reqs]
        if coord_ids:
            seen = {r["id"] for r in rows}
            extra = (
                self.client.table("conversations")
                .select("*")
                .in_("request_id", coord_ids)
                .execute()
            ).data or []
            for e in extra:
                if e["id"] not in seen:
                    rows.append(e)
        return [self._hydrate_supabase_conv(r, user_id) for r in rows]

    def get_conversation_for_participant(self, conversation_id: str, user_id: str) -> Any:
        rows = (
            self.client.table("conversations").select("*").eq("id", conversation_id).limit(1).execute()
        ).data or []
        if not rows:
            return None
        row = rows[0]
        if row["requester_id"] != user_id and row["donor_id"] != user_id:
            if not self.is_active_coordinator_for_request(user_id, row["request_id"], "can_chat"):
                return "FORBIDDEN"
        return self._hydrate_supabase_conv(row, user_id)

    def list_messages(self, conversation_id: str, current_user_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.client.table("messages")
            .select("*, profiles!inner(full_name)")
            .eq("conversation_id", conversation_id)
            .order("created_at")
            .execute()
        ).data or []
        return [
            {
                "id": r["id"],
                "conversation_id": r["conversation_id"],
                "sender_id": r["sender_id"],
                "sender_display_name": mask_display_name((r.get("profiles") or {}).get("full_name", "")),
                "is_mine": r["sender_id"] == current_user_id,
                "message_text": r["message_text"],
                "created_at": str(r["created_at"]),
                "read_at": r.get("read_at"),
            }
            for r in rows
        ]

    def create_message(
        self,
        *,
        conversation_id: str,
        sender_id: str,
        counterpart_id: str,
        request_id: str,
        message_text: str,
        sender_full_name: str,
    ) -> Dict[str, Any]:
        row = (
            self.client.table("messages")
            .insert({"conversation_id": conversation_id, "sender_id": sender_id, "message_text": message_text})
            .execute()
        ).data[0]
        self.client.table("notifications").insert(
            {
                "user_id": counterpart_id,
                "notification_type": "new_message",
                "title": "New Private Chat Message",
                "message": f"{mask_display_name(sender_full_name)} sent a message regarding your blood request.",
                "related_request_id": request_id,
                "delivery_status": "saved",
            }
        ).execute()
        return {
            "id": row["id"],
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "sender_display_name": mask_display_name(sender_full_name),
            "is_mine": True,
            "message_text": message_text,
            "created_at": str(row["created_at"]),
            "read_at": None,
        }

    def mark_messages_read(self, conversation_id: str, current_user_id: str) -> int:
        res = (
            self.client.table("messages")
            .update({"read_at": _utc_now_iso()})
            .eq("conversation_id", conversation_id)
            .neq("sender_id", current_user_id)
            .is_("read_at", "null")
            .execute()
        )
        return len(res.data or [])

    def get_contact_sharing_status(
        self, *, request_id: str, current_user_id: str, donor_user_id: Optional[str]
    ) -> Any:
        q = self.client.table("contact_sharing_consents").select("*").eq("request_id", request_id)
        if donor_user_id:
            q = q.eq("donor_id", donor_user_id)
        rows = q.execute().data or []
        match = next((r for r in rows if r["requester_id"] == current_user_id or r["donor_id"] == current_user_id), None)
        if not match:
            return "FORBIDDEN" if rows else None
        both = bool(match["requester_consent"]) and bool(match["donor_consent"]) and match["status"] == "both_consented"
        phone = None
        if both:
            other_id = match["donor_id"] if match["requester_id"] == current_user_id else match["requester_id"]
            other = self.get_profile_by_id(other_id)
            phone = other["phone_number"] if other else None
        return {
            "request_id": match["request_id"],
            "requester_consent": bool(match["requester_consent"]),
            "donor_consent": bool(match["donor_consent"]),
            "requester_consent_at": match.get("requester_consent_at"),
            "donor_consent_at": match.get("donor_consent_at"),
            "status": match["status"],
            "counterpart_phone_number": phone,
        }

    def update_contact_sharing_consent(
        self, *, request_id: str, current_user_id: str, donor_user_id: Optional[str], grant: bool
    ) -> Any:
        cur = self.get_contact_sharing_status(
            request_id=request_id, current_user_id=current_user_id, donor_user_id=donor_user_id
        )
        if cur in (None, "FORBIDDEN"):
            return cur
        q = self.client.table("contact_sharing_consents").select("*").eq("request_id", request_id)
        if donor_user_id:
            q = q.eq("donor_id", donor_user_id)
        rows = q.execute().data or []
        row = next(r for r in rows if r["requester_id"] == current_user_id or r["donor_id"] == current_user_id)
        is_req = row["requester_id"] == current_user_id
        req_c = bool(row["requester_consent"])
        don_c = bool(row["donor_consent"])
        now = _utc_now_iso()
        updates: Dict[str, Any] = {}
        if grant:
            if is_req:
                req_c = True
                updates.update({"requester_consent": True, "requester_consent_at": now})
            else:
                don_c = True
                updates.update({"donor_consent": True, "donor_consent_at": now})
            updates["status"] = "both_consented" if (req_c and don_c) else "pending"
        else:
            if is_req:
                updates["requester_consent"] = False
            else:
                updates["donor_consent"] = False
            updates["status"] = "withdrawn"
        self.client.table("contact_sharing_consents").update(updates).eq("id", row["id"]).execute()
        return self.get_contact_sharing_status(
            request_id=request_id, current_user_id=current_user_id, donor_user_id=donor_user_id
        )

    def create_report(
        self,
        *,
        reporter_id: str,
        reported_user_id: Optional[str],
        request_id: Optional[str],
        reason: str,
        description: Optional[str],
    ) -> Dict[str, Any]:
        return (
            self.client.table("reports")
            .insert(
                {
                    "reporter_id": reporter_id,
                    "reported_user_id": reported_user_id,
                    "request_id": request_id,
                    "reason": reason.strip(),
                    "description": description,
                    "status": "open",
                }
            )
            .execute()
        ).data[0]

    def block_user(
        self,
        *,
        blocker_id: str,
        blocked_user_id: str,
        conversation_id: Optional[str],
        reason: str,
    ) -> None:
        self.client.table("user_blocks").upsert(
            {"blocker_id": blocker_id, "blocked_user_id": blocked_user_id, "reason": reason},
            on_conflict="blocker_id,blocked_user_id",
        ).execute()
        if conversation_id:
            self.client.table("conversations").update({"status": "blocked"}).eq("id", conversation_id).execute()

    # --- Phase 5: Rule-Based LifeLink Assistant Sessions (Supabase) ---

    def get_or_create_chatbot_session(self, user_id: str, session_id: Optional[str]) -> str:
        if session_id:
            res = (
                self.client.table("chatbot_sessions")
                .select("id")
                .eq("id", session_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            ).data
            if res:
                return res[0]["id"]
        latest = (
            self.client.table("chatbot_sessions")
            .select("id")
            .eq("user_id", user_id)
            .eq("session_status", "active")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        ).data
        if latest:
            return latest[0]["id"]
        created = self.client.table("chatbot_sessions").insert({"user_id": user_id, "session_status": "active"}).execute()
        return created.data[0]["id"]

    def append_chatbot_message(self, session_id: str, sender_type: str, message_text: str) -> None:
        self.client.table("chatbot_messages").insert(
            {"session_id": session_id, "sender_type": sender_type, "message_text": message_text}
        ).execute()

    def get_chatbot_history(self, user_id: str, session_id: Optional[str]) -> Dict[str, Any]:
        sid = self.get_or_create_chatbot_session(user_id, session_id)
        rows = (
            self.client.table("chatbot_messages")
            .select("*")
            .eq("session_id", sid)
            .order("created_at")
            .execute()
        ).data or []
        return {"session_id": sid, "messages": rows}

    # --- Phase 6: Blood-Bank Fallback & Request Outcomes (Supabase) ---

    def get_blood_bank_by_id(self, blood_bank_id: str) -> Optional[Dict[str, Any]]:
        rows = (
            self.client.table("blood_banks").select("*").eq("id", blood_bank_id).limit(1).execute()
        ).data or []
        if not rows:
            return None
        row = rows[0]
        row["availability_label"] = AVAILABILITY_LABELS.get(
            row.get("availability_status", "contact_required"), "Contact required"
        )
        return row

    def record_blood_bank_contact_attempt(
        self,
        *,
        request_id: str,
        blood_bank_id: str,
        recorded_by: str,
        outcome: str,
        notes: Optional[str],
    ) -> Dict[str, Any]:
        row = (
            self.client.table("blood_bank_contact_attempts")
            .insert(
                {
                    "request_id": request_id,
                    "blood_bank_id": blood_bank_id,
                    "recorded_by": recorded_by,
                    "outcome": outcome,
                    "notes": notes,
                }
            )
            .execute()
        ).data[0]
        now = _utc_now_iso()
        if outcome == "confirmed_available":
            self.client.table("blood_banks").update(
                {"availability_status": "availability_confirmed_by_facility", "last_verified_at": now}
            ).eq("id", blood_bank_id).execute()
        elif outcome == "unavailable":
            self.client.table("blood_banks").update(
                {"availability_status": "availability_unavailable", "last_verified_at": now}
            ).eq("id", blood_bank_id).execute()
        return row

    def list_blood_bank_contact_attempts(self, request_id: str) -> List[Dict[str, Any]]:
        return (
            self.client.table("blood_bank_contact_attempts")
            .select("*, blood_banks(facility_name, city, phone)")
            .eq("request_id", request_id)
            .order("attempted_at", desc=True)
            .execute()
        ).data or []

    def record_request_outcome(
        self,
        *,
        request_row: Dict[str, Any],
        changed_by: str,
        outcome: str,
        donated_by_donor_id: Optional[str] = None,
        notes: Optional[str],
        cooldown_days: int = 90,
    ) -> Dict[str, Any]:
        request_id = str(request_row["id"])
        self.client.table("blood_requests").update({"status": outcome}).eq("id", request_id).execute()
        self.client.table("request_status_history").insert(
            {
                "request_id": request_id,
                "previous_status": request_row["status"],
                "new_status": outcome,
                "changed_by": changed_by,
                "notes": notes or f"Request outcome recorded as {outcome}.",
            }
        ).execute()
        if outcome == "fulfilled" and donated_by_donor_id:
            today_str = datetime.now().date().isoformat()
            frozen_until, freeze_reason = _compute_freeze_fields(today_str, cooldown_days)
            self.client.table("donor_profiles").update(
                {
                    "last_donation_date": today_str,
                    "donor_frozen_until": frozen_until,
                    "donor_freeze_reason": freeze_reason,
                    "availability_status": "unavailable",
                }
            ).eq("id", donated_by_donor_id).execute()
        updated = self.get_blood_request(request_id)
        assert updated is not None
        return updated

    # --- Phase 7: Donor Documents, Admin Moderation, Blood-Bank CRUD & Analytics (Supabase) ---

    def _write_audit_log(self, actor_id: str, action: str, target_type: str, target_id: Optional[str], notes: str = "") -> None:
        self.client.table("audit_logs").insert(
            {
                "actor_id": actor_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "metadata": {"notes": notes} if notes else {},
            }
        ).execute()

    def submit_donor_document(self, *, donor_id: str, document_type: str, storage_path: str) -> Dict[str, Any]:
        doc = (
            self.client.table("donor_documents")
            .insert(
                {
                    "donor_id": donor_id,
                    "document_type": document_type.strip(),
                    "storage_path": storage_path.strip(),
                    "review_status": "pending_review",
                }
            )
            .execute()
        ).data[0]
        self.client.table("donor_profiles").update({"verification_status": "pending_review"}).eq("id", donor_id).execute()
        return doc

    def list_donor_documents(self, donor_id: str) -> List[Dict[str, Any]]:
        return (
            self.client.table("donor_documents")
            .select("*")
            .eq("donor_id", donor_id)
            .order("created_at", desc=True)
            .execute()
        ).data or []

    def get_donor_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        rows = (
            self.client.table("donor_documents").select("*").eq("id", doc_id).limit(1).execute()
        ).data or []
        return rows[0] if rows else None

    def get_face_profile_status(self, donor_id: str) -> Dict[str, Any]:
        rows = (
            self.client.table("donor_face_profiles")
            .select("enrolled_at, updated_at")
            .eq("donor_id", donor_id)
            .limit(1)
            .execute()
        ).data or []
        logs = (
            self.client.table("face_verification_logs")
            .select("id, request_id, similarity_score, verified, reason, verified_at")
            .eq("donor_id", donor_id)
            .order("verified_at", desc=True)
            .limit(10)
            .execute()
        ).data or []
        return {
            "enrolled": bool(rows),
            "enrolled_at": str(rows[0]["enrolled_at"]) if rows else None,
            "updated_at": str(rows[0]["updated_at"]) if rows else None,
            "recent_verifications": logs,
        }

    def upsert_face_descriptor(self, donor_id: str, descriptor: List[float]) -> Dict[str, Any]:
        self.client.table("donor_face_profiles").upsert(
            {"donor_id": donor_id, "descriptor_json": descriptor, "consent_given": True},
            on_conflict="donor_id",
        ).execute()
        return self.get_face_profile_status(donor_id)

    def get_face_descriptor(self, donor_id: str) -> Optional[List[float]]:
        rows = (
            self.client.table("donor_face_profiles")
            .select("descriptor_json")
            .eq("donor_id", donor_id)
            .limit(1)
            .execute()
        ).data or []
        return rows[0]["descriptor_json"] if rows else None

    def log_face_verification(
        self,
        *,
        donor_id: str,
        request_id: Optional[str],
        similarity_score: float,
        verified: bool,
        reason: str,
    ) -> Dict[str, Any]:
        res = (
            self.client.table("face_verification_logs")
            .insert(
                {
                    "donor_id": donor_id,
                    "request_id": request_id,
                    "similarity_score": similarity_score,
                    "verified": verified,
                    "reason": reason,
                }
            )
            .execute()
        )
        return res.data[0]

    def has_verified_face_for_request(self, donor_id: str, request_id: str) -> bool:
        rows = (
            self.client.table("face_verification_logs")
            .select("id")
            .eq("donor_id", donor_id)
            .eq("request_id", request_id)
            .eq("verified", True)
            .limit(1)
            .execute()
        ).data or []
        return bool(rows)

    def upsert_donor_tracking(
        self,
        *,
        request_id: str,
        donor_id: str,
        zone_lat: float,
        zone_lon: float,
        radius_meters: int,
        tracking_status: str,
        distance_band: str,
    ) -> Dict[str, Any]:
        self.client.table("donor_location_tracking").upsert(
            {
                "request_id": request_id,
                "donor_id": donor_id,
                "zone_lat": zone_lat,
                "zone_lon": zone_lon,
                "radius_meters": radius_meters,
                "tracking_status": tracking_status,
                "distance_band": distance_band,
                "is_active": True,
            },
            on_conflict="request_id,donor_id",
        ).execute()
        rows = self.list_tracking_for_request(request_id)
        return next(r for r in rows if r["donor_id"] == donor_id)

    def stop_donor_tracking(self, *, request_id: str, donor_id: str) -> None:
        self.client.table("donor_location_tracking").update(
            {"tracking_status": "stopped", "is_active": False}
        ).eq("request_id", request_id).eq("donor_id", donor_id).execute()

    def list_tracking_for_request(self, request_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.client.table("donor_location_tracking")
            .select("*, donor_profiles!inner(profiles!inner(full_name))")
            .eq("request_id", request_id)
            .order("updated_at", desc=True)
            .execute()
        ).data or []
        out = []
        for r in rows:
            dp = r.get("donor_profiles") or {}
            prof = dp.get("profiles") or {}
            out.append(
                {
                    "request_id": r["request_id"],
                    "donor_id": r["donor_id"],
                    "donor_display_name": mask_display_name(prof.get("full_name", "")),
                    "zone_lat": float(r["zone_lat"]),
                    "zone_lon": float(r["zone_lon"]),
                    "radius_meters": int(r["radius_meters"]),
                    "tracking_status": r["tracking_status"],
                    "distance_band": r["distance_band"],
                    "is_active": bool(r["is_active"]),
                    "updated_at": str(r["updated_at"]),
                }
            )
        return out

    def store_donor_document_bytes(
        self,
        *,
        donor_id: str,
        safe_filename: str,
        content_bytes: bytes,
        content_type: str,
        settings: Settings,
    ) -> str:
        if settings.is_google_drive_upload_enabled:
            from backend.app.services.google_drive import upload_bytes_to_drive_folder

            try:
                file_id = upload_bytes_to_drive_folder(
                    service_account_file=settings.google_drive_service_account_file,
                    folder_id=settings.resolved_google_drive_folder_id,
                    filename=f"{donor_id}_{safe_filename}",
                    content_bytes=content_bytes,
                    content_type=content_type,
                )
                return f"gdrive:{file_id}"
            except Exception as exc:
                raise DatabaseUnavailableError(f"Google Drive upload failed: {exc}") from exc

        storage_path = f"{donor_id}/{safe_filename}"
        try:
            self.client.storage.from_("donor-documents").upload(
                storage_path, content_bytes, {"content-type": content_type}
            )
            return storage_path
        except Exception as exc:
            raise DatabaseUnavailableError(f"Supabase Storage upload failed: {exc}") from exc

    def read_donor_document_bytes(self, storage_path: str, settings: Settings) -> Optional[bytes]:
        if storage_path.startswith("gdrive:") and settings.is_google_drive_upload_enabled:
            from backend.app.services.google_drive import download_bytes_from_drive

            file_id = storage_path.split("gdrive:", 1)[1]
            return download_bytes_from_drive(
                service_account_file=settings.google_drive_service_account_file,
                file_id=file_id,
            )
        try:
            return self.client.storage.from_("donor-documents").download(storage_path)
        except Exception:
            return None

    def admin_update_user_status(
        self, *, user_id: str, account_status: str, admin_id: str, reason: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        res = self.client.table("profiles").update({"account_status": account_status}).eq("id", user_id).execute()
        if not res.data:
            return None
        self._write_audit_log(admin_id, f"user_{account_status}", "profile", user_id, reason or "")
        return res.data[0]

    def admin_list_donor_documents(self, review_status: Optional[str] = None) -> List[Dict[str, Any]]:
        q = self.client.table("donor_documents").select("*, donor_profiles(blood_group, profiles(full_name, city))")
        if review_status:
            q = q.eq("review_status", review_status)
        return q.order("created_at", desc=True).execute().data or []

    def admin_review_donor_document(
        self, *, doc_id: str, review_status: str, admin_id: str, notes: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        res = (
            self.client.table("donor_documents")
            .update({"review_status": review_status, "reviewed_by": admin_id})
            .eq("id", doc_id)
            .execute()
        )
        if not res.data:
            return None
        doc = res.data[0]
        self.client.table("donor_profiles").update({"verification_status": review_status}).eq("id", doc["donor_id"]).execute()
        self._write_audit_log(admin_id, f"document_{review_status}", "donor_document", doc_id, notes or "")
        return doc

    def admin_list_requests(
        self, *, status_filter: Optional[str] = None, blood_group: Optional[str] = None, city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        q = self.client.table("blood_requests").select("*")
        if status_filter:
            q = q.eq("status", status_filter)
        if blood_group:
            q = q.eq("blood_group", blood_group)
        if city:
            q = q.ilike("city", f"%{city.strip()}%")
        return q.order("created_at", desc=True).limit(100).execute().data or []

    def admin_moderate_request(
        self, *, request_row: Dict[str, Any], new_status: str, notes: str, admin_id: str
    ) -> Dict[str, Any]:
        request_id = str(request_row["id"])
        self.client.table("blood_requests").update({"status": new_status}).eq("id", request_id).execute()
        self.client.table("request_status_history").insert(
            {
                "request_id": request_id,
                "previous_status": request_row["status"],
                "new_status": new_status,
                "changed_by": admin_id,
                "notes": f"[Admin] {notes}",
            }
        ).execute()
        self._write_audit_log(admin_id, f"request_moderated_{new_status}", "blood_request", request_id, notes)
        updated = self.get_blood_request(request_id)
        assert updated is not None
        return updated

    def admin_list_reports(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        q = self.client.table("reports").select("*")
        if status_filter:
            q = q.eq("status", status_filter)
        return q.order("created_at", desc=True).limit(100).execute().data or []

    def admin_update_report(self, *, report_id: str, status_value: str, admin_id: str) -> Optional[Dict[str, Any]]:
        res = (
            self.client.table("reports")
            .update({"status": status_value, "reviewed_by": admin_id})
            .eq("id", report_id)
            .execute()
        )
        if not res.data:
            return None
        self._write_audit_log(admin_id, f"report_{status_value}", "report", report_id)
        return res.data[0]

    def admin_create_blood_bank(self, data: Dict[str, Any], admin_id: str) -> Dict[str, Any]:
        payload = {**data, "last_verified_at": _utc_now_iso()}
        created = self.client.table("blood_banks").insert(payload).execute().data[0]
        self._write_audit_log(admin_id, "blood_bank_created", "blood_bank", created["id"])
        created["availability_label"] = AVAILABILITY_LABELS.get(created["availability_status"], "Contact required")
        return created

    def admin_update_blood_bank(self, bank_id: str, data: Dict[str, Any], admin_id: str) -> Optional[Dict[str, Any]]:
        payload = {**data, "last_verified_at": _utc_now_iso()}
        res = self.client.table("blood_banks").update(payload).eq("id", bank_id).execute()
        if not res.data:
            return None
        self._write_audit_log(admin_id, "blood_bank_updated", "blood_bank", bank_id)
        row = res.data[0]
        row["availability_label"] = AVAILABILITY_LABELS.get(row["availability_status"], "Contact required")
        return row

    def admin_delete_blood_bank(self, bank_id: str, admin_id: str) -> bool:
        res = self.client.table("blood_banks").delete().eq("id", bank_id).execute()
        if not res.data:
            return False
        self._write_audit_log(admin_id, "blood_bank_deleted", "blood_bank", bank_id)
        return True

    def admin_get_analytics(self) -> Dict[str, Any]:
        reqs = self.client.table("blood_requests").select("status, blood_group, city").execute().data or []
        resps = self.client.table("donor_responses").select("response").execute().data or []
        by_status: Dict[str, int] = {}
        by_group: Dict[str, int] = {}
        by_city: Dict[str, int] = {}
        by_resp: Dict[str, int] = {}
        for r in reqs:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            by_group[r["blood_group"]] = by_group.get(r["blood_group"], 0) + 1
            by_city[r["city"]] = by_city.get(r["city"], 0) + 1
        for r in resps:
            by_resp[r["response"]] = by_resp.get(r["response"], 0) + 1
        return {
            "requests_by_status": by_status,
            "requests_by_blood_group": by_group,
            "requests_by_city": by_city,
            "donor_responses_by_type": by_resp,
            "disclaimer": "Platform operational records only, not clinical outcomes.",
        }

    def admin_list_audit_logs(self) -> List[Dict[str, Any]]:
        return (
            self.client.table("audit_logs").select("*").order("created_at", desc=True).limit(100).execute().data
            or []
        )


_repo_instance: Optional[Any] = None
_repo_mode_key: Optional[str] = None


def get_repository(settings: Optional[Settings] = None) -> Any:
    """Return the active database repository (Supabase when configured, else LocalDevSQLite)."""
    global _repo_instance, _repo_mode_key
    cfg = settings or get_settings()
    mode_key = f"{cfg.storage_mode}:{cfg.dev_db_path}:{cfg.supabase_url}"
    if _repo_instance is not None and _repo_mode_key == mode_key:
        return _repo_instance

    if cfg.is_supabase_configured:
        _repo_instance = SupabaseRepository(cfg)
    elif cfg.dev_auth_mode:
        _repo_instance = LocalDevSQLiteRepository(cfg.dev_db_path)
    else:
        raise DatabaseUnavailableError(
            "Supabase is not configured and DEV_AUTH_MODE is disabled."
        )

    _repo_mode_key = mode_key
    return _repo_instance


def reset_repository_cache() -> None:
    """Helper for tests when overriding settings/database paths."""
    global _repo_instance, _repo_mode_key
    _repo_instance = None
    _repo_mode_key = None
