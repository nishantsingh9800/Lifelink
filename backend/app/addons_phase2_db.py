"""Phase 2 Add-On Repository Mixins (SQLite + Supabase): Preferences, Calendar, Family Accounts & Share Links."""

import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.utils.security import mask_display_name


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Phase2SQLiteMixin:
    """SQLite implementations for Phase 2 add-on features."""

    def _init_phase2_schema(self, conn: sqlite3.Connection) -> None:
        # Upgrade donor_profiles CHECK constraint safely if 'available_selected_dates' is missing
        dp_tbl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='donor_profiles'"
        ).fetchone()
        if dp_tbl and "available_selected_dates" not in (dp_tbl["sql"] or ""):
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.executescript(
                """
                CREATE TABLE donor_profiles_new (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
                    blood_group TEXT NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
                    availability_status TEXT NOT NULL DEFAULT 'unavailable'
                        CHECK (availability_status IN ('available_now', 'available_today', 'available_selected_dates', 'unavailable', 'emergency_only')),
                    last_donation_date TEXT,
                    donor_frozen_until TEXT,
                    donor_freeze_reason TEXT,
                    preferred_contact_method TEXT NOT NULL DEFAULT 'in_app_chat',
                    verification_status TEXT NOT NULL DEFAULT 'not_submitted'
                        CHECK (verification_status IN ('not_submitted', 'pending_review', 'verified', 'rejected')),
                    emergency_notifications_enabled INTEGER NOT NULL DEFAULT 1,
                    profile_completed INTEGER NOT NULL DEFAULT 0,
                    last_availability_updated_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO donor_profiles_new (
                    id, user_id, blood_group, availability_status, last_donation_date,
                    donor_frozen_until, donor_freeze_reason, preferred_contact_method,
                    verification_status, emergency_notifications_enabled, profile_completed,
                    created_at, updated_at
                )
                SELECT id, user_id, blood_group, availability_status, last_donation_date,
                    donor_frozen_until, donor_freeze_reason, preferred_contact_method,
                    verification_status, emergency_notifications_enabled, profile_completed,
                    created_at, updated_at
                FROM donor_profiles;
                DROP TABLE donor_profiles;
                ALTER TABLE donor_profiles_new RENAME TO donor_profiles;
                """
            )
            conn.execute("PRAGMA foreign_keys = ON;")

        p_cols = {r["name"] for r in conn.execute("PRAGMA table_info(profiles)").fetchall()}
        if "preferred_language" not in p_cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN preferred_language TEXT NOT NULL DEFAULT 'en'")
        if "accessibility_prefs" not in p_cols:
            conn.execute(
                'ALTER TABLE profiles ADD COLUMN accessibility_prefs TEXT NOT NULL DEFAULT \'{"text_size": "normal", "high_contrast": false}\''
            )

        dp_cols = {r["name"] for r in conn.execute("PRAGMA table_info(donor_profiles)").fetchall()}
        if "last_availability_updated_at" not in dp_cols:
            conn.execute("ALTER TABLE donor_profiles ADD COLUMN last_availability_updated_at TEXT")

        br_cols = {r["name"] for r in conn.execute("PRAGMA table_info(blood_requests)").fetchall()}
        if "created_by_user_id" not in br_cols:
            conn.execute("ALTER TABLE blood_requests ADD COLUMN created_by_user_id TEXT REFERENCES profiles(id)")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS donor_availability (
                id TEXT PRIMARY KEY,
                donor_id TEXT NOT NULL UNIQUE REFERENCES donor_profiles(id) ON DELETE CASCADE,
                available_dates TEXT NOT NULL DEFAULT '[]',
                preferred_distance_km INTEGER NOT NULL DEFAULT 25,
                quiet_hours_start TEXT,
                quiet_hours_end TEXT,
                paused_until TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_notification_preferences (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
                in_app_enabled INTEGER NOT NULL DEFAULT 1,
                quiet_hours_enabled INTEGER NOT NULL DEFAULT 1,
                emergency_override_quiet_hours INTEGER NOT NULL DEFAULT 1,
                reminder_frequency_days INTEGER NOT NULL DEFAULT 30,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS emergency_contacts (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                member_user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                relationship TEXT NOT NULL,
                can_create_requests INTEGER NOT NULL DEFAULT 1,
                can_manage_requests INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'declined', 'revoked')),
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE (owner_user_id, member_user_id)
            );

            CREATE TABLE IF NOT EXISTS request_share_links (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE REFERENCES blood_requests(id) ON DELETE CASCADE,
                share_token TEXT NOT NULL UNIQUE,
                created_by TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ec_member_status ON emergency_contacts(member_user_id, status);
            CREATE INDEX IF NOT EXISTS idx_share_links_token ON request_share_links(share_token);
            """
        )

    # --- Language, Accessibility & Notification Preferences ---

    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            p = conn.execute(
                "SELECT preferred_language, accessibility_prefs FROM profiles WHERE id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
            np = conn.execute(
                "SELECT * FROM user_notification_preferences WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
        a11y = {"text_size": "normal", "high_contrast": False}
        if p and p["accessibility_prefs"]:
            try:
                a11y.update(json.loads(p["accessibility_prefs"]))
            except Exception:
                pass
        return {
            "preferred_language": p["preferred_language"] if p else "en",
            "text_size": a11y.get("text_size", "normal"),
            "high_contrast": bool(a11y.get("high_contrast", False)),
            "in_app_enabled": bool(np["in_app_enabled"]) if np else True,
            "quiet_hours_enabled": bool(np["quiet_hours_enabled"]) if np else True,
            "emergency_override_quiet_hours": bool(np["emergency_override_quiet_hours"]) if np else True,
            "reminder_frequency_days": int(np["reminder_frequency_days"]) if np else 30,
        }

    def update_user_preferences(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        cur = self.get_user_preferences(user_id)
        lang = payload.get("preferred_language") or cur["preferred_language"]
        a11y = {
            "text_size": payload.get("text_size") or cur["text_size"],
            "high_contrast": payload["high_contrast"] if "high_contrast" in payload else cur["high_contrast"],
        }
        in_app = payload["in_app_enabled"] if "in_app_enabled" in payload else cur["in_app_enabled"]
        qh_en = payload["quiet_hours_enabled"] if "quiet_hours_enabled" in payload else cur["quiet_hours_enabled"]
        em_ov = payload["emergency_override_quiet_hours"] if "emergency_override_quiet_hours" in payload else cur["emergency_override_quiet_hours"]
        rem_days = payload.get("reminder_frequency_days") or cur["reminder_frequency_days"]

        with self._connect() as conn:  # type: ignore[attr-defined]
            existing_row = conn.execute(
                "SELECT accessibility_prefs FROM profiles WHERE id = ? LIMIT 1", (user_id,)
            ).fetchone()
            if existing_row and existing_row["accessibility_prefs"]:
                try:
                    raw_a11y = json.loads(existing_row["accessibility_prefs"])
                    if isinstance(raw_a11y, dict) and "recovery_hashes" in raw_a11y:
                        a11y["recovery_hashes"] = raw_a11y["recovery_hashes"]
                except Exception:
                    pass
            conn.execute(
                "UPDATE profiles SET preferred_language = ?, accessibility_prefs = ?, updated_at = ? WHERE id = ?",
                (lang, json.dumps(a11y), now, user_id),
            )
            existing = conn.execute(
                "SELECT id FROM user_notification_preferences WHERE user_id = ? LIMIT 1", (user_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE user_notification_preferences
                    SET in_app_enabled = ?, quiet_hours_enabled = ?,
                        emergency_override_quiet_hours = ?, reminder_frequency_days = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (int(in_app), int(qh_en), int(em_ov), rem_days, now, user_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO user_notification_preferences (
                        id, user_id, in_app_enabled, quiet_hours_enabled,
                        emergency_override_quiet_hours, reminder_frequency_days, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), user_id, int(in_app), int(qh_en), int(em_ov), rem_days, now),
                )
        return self.get_user_preferences(user_id)

    # --- Donor Availability Calendar ---

    def get_donor_calendar(self, donor_id: str, user_id: str) -> Dict[str, Any]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            dp = conn.execute(
                "SELECT availability_status, emergency_notifications_enabled, last_availability_updated_at, updated_at FROM donor_profiles WHERE id = ? LIMIT 1",
                (donor_id,),
            ).fetchone()
            cal = conn.execute(
                "SELECT * FROM donor_availability WHERE donor_id = ? LIMIT 1",
                (donor_id,),
            ).fetchone()
            np = conn.execute(
                "SELECT * FROM user_notification_preferences WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
        dates = []
        if cal and cal["available_dates"]:
            try:
                dates = json.loads(cal["available_dates"])
            except Exception:
                dates = []
        return {
            "donor_id": donor_id,
            "availability_status": dp["availability_status"] if dp else "unavailable",
            "available_dates": dates,
            "preferred_distance_km": int(cal["preferred_distance_km"]) if cal else 25,
            "quiet_hours_start": cal["quiet_hours_start"] if cal else None,
            "quiet_hours_end": cal["quiet_hours_end"] if cal else None,
            "paused_until": cal["paused_until"] if cal else None,
            "emergency_notifications_enabled": bool(dp["emergency_notifications_enabled"]) if dp else True,
            "quiet_hours_enabled": bool(np["quiet_hours_enabled"]) if np else True,
            "emergency_override_quiet_hours": bool(np["emergency_override_quiet_hours"]) if np else True,
            "last_availability_updated_at": (dp["last_availability_updated_at"] or dp["updated_at"]) if dp else None,
            "disclaimer": "Availability is self-declared and does not determine medical donation eligibility.",
        }

    def upsert_donor_calendar(self, *, donor_id: str, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        cur = self.get_donor_calendar(donor_id, user_id)
        avail = payload.get("availability_status") or cur["availability_status"]
        dates = payload["available_dates"] if "available_dates" in payload and payload["available_dates"] is not None else cur["available_dates"]
        dist = payload.get("preferred_distance_km") or cur["preferred_distance_km"]
        q_start = payload["quiet_hours_start"] if "quiet_hours_start" in payload else cur["quiet_hours_start"]
        q_end = payload["quiet_hours_end"] if "quiet_hours_end" in payload else cur["quiet_hours_end"]
        paused = payload["paused_until"] if "paused_until" in payload else cur["paused_until"]
        notif = payload["emergency_notifications_enabled"] if "emergency_notifications_enabled" in payload and payload["emergency_notifications_enabled"] is not None else cur["emergency_notifications_enabled"]

        with self._connect() as conn:  # type: ignore[attr-defined]
            conn.execute(
                """
                UPDATE donor_profiles
                SET availability_status = ?, emergency_notifications_enabled = ?,
                    last_availability_updated_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (avail, int(notif), now, now, donor_id),
            )
            existing = conn.execute("SELECT id FROM donor_availability WHERE donor_id = ? LIMIT 1", (donor_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE donor_availability
                    SET available_dates = ?, preferred_distance_km = ?,
                        quiet_hours_start = ?, quiet_hours_end = ?, paused_until = ?, updated_at = ?
                    WHERE donor_id = ?
                    """,
                    (json.dumps(dates), dist, q_start, q_end, paused, now, donor_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO donor_availability (
                        id, donor_id, available_dates, preferred_distance_km,
                        quiet_hours_start, quiet_hours_end, paused_until, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), donor_id, json.dumps(dates), dist, q_start, q_end, paused, now, now),
                )
        return self.get_donor_calendar(donor_id, user_id)

    def _enrich_donor_row_with_calendar_sqlite(self, conn: sqlite3.Connection, d: Dict[str, Any]) -> Dict[str, Any]:
        cal = conn.execute(
            "SELECT * FROM donor_availability WHERE donor_id = ? LIMIT 1", (d["id"],)
        ).fetchone()
        np = conn.execute(
            "SELECT * FROM user_notification_preferences WHERE user_id = ? LIMIT 1", (d["user_id"],)
        ).fetchone()
        if cal:
            try:
                d["available_dates"] = json.loads(cal["available_dates"] or "[]")
            except Exception:
                d["available_dates"] = []
            d["preferred_distance_km"] = cal["preferred_distance_km"]
            d["quiet_hours_start"] = cal["quiet_hours_start"]
            d["quiet_hours_end"] = cal["quiet_hours_end"]
            d["paused_until"] = cal["paused_until"]
        if np:
            d["quiet_hours_enabled"] = bool(np["quiet_hours_enabled"])
            d["emergency_override_quiet_hours"] = bool(np["emergency_override_quiet_hours"])
        return d

    # --- Family Emergency Account ---

    def invite_family_contact(
        self,
        *,
        owner_user_id: str,
        member_identifier: str,
        relationship: str,
        can_create_requests: bool,
        can_manage_requests: bool,
    ) -> Optional[Dict[str, Any]]:
        ident = member_identifier.strip()
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            target = conn.execute(
                "SELECT * FROM profiles WHERE lower(email) = lower(?) OR phone_number = ? LIMIT 1",
                (ident, ident),
            ).fetchone()
            if not target or target["account_status"] != "active":
                return None
            if target["id"] == owner_user_id:
                raise ValueError("Cannot add yourself as a delegated family member.")
            existing = conn.execute(
                "SELECT id FROM emergency_contacts WHERE owner_user_id = ? AND member_user_id = ? LIMIT 1",
                (owner_user_id, target["id"]),
            ).fetchone()
            if existing:
                cid = existing["id"]
                conn.execute(
                    """
                    UPDATE emergency_contacts
                    SET relationship = ?, can_create_requests = ?, can_manage_requests = ?,
                        status = 'pending', revoked_at = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (relationship.strip(), int(can_create_requests), int(can_manage_requests), now, cid),
                )
            else:
                cid = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO emergency_contacts (
                        id, owner_user_id, member_user_id, relationship,
                        can_create_requests, can_manage_requests, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (cid, owner_user_id, target["id"], relationship.strip(), int(can_create_requests), int(can_manage_requests), now, now),
                )
            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=target["id"],
                notification_type="admin_notice",
                title="Family Emergency Account Authorization",
                message=f"You have been listed as a trusted family emergency contact ({relationship}). Review on your Dashboard.",
                related_request_id=None,
            )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=owner_user_id,
                action="family_contact_invited",
                target_type="emergency_contact",
                target_id=cid,
                metadata_json=json.dumps({"member_user_id": target["id"], "relationship": relationship}),
            )
        return self.get_family_contact(cid)

    def get_family_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT ec.*, op.full_name AS owner_name, mp.full_name AS member_name
                FROM emergency_contacts ec
                JOIN profiles op ON op.id = ec.owner_user_id
                JOIN profiles mp ON mp.id = ec.member_user_id
                WHERE ec.id = ? LIMIT 1
                """,
                (contact_id,),
            ).fetchone()
        return self._format_family_row(row) if row else None

    @staticmethod
    def _format_family_row(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "owner_user_id": row["owner_user_id"],
            "owner_display_name": mask_display_name(row["owner_name"]),
            "member_user_id": row["member_user_id"],
            "member_display_name": mask_display_name(row["member_name"]),
            "relationship": row["relationship"],
            "can_create_requests": bool(row["can_create_requests"]),
            "can_manage_requests": bool(row["can_manage_requests"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "revoked_at": row["revoked_at"],
        }

    def list_family_contacts_for_user(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            granted = conn.execute(
                """
                SELECT ec.*, op.full_name AS owner_name, mp.full_name AS member_name
                FROM emergency_contacts ec
                JOIN profiles op ON op.id = ec.owner_user_id
                JOIN profiles mp ON mp.id = ec.member_user_id
                WHERE ec.owner_user_id = ?
                ORDER BY ec.created_at DESC
                """,
                (user_id,),
            ).fetchall()
            received = conn.execute(
                """
                SELECT ec.*, op.full_name AS owner_name, mp.full_name AS member_name
                FROM emergency_contacts ec
                JOIN profiles op ON op.id = ec.owner_user_id
                JOIN profiles mp ON mp.id = ec.member_user_id
                WHERE ec.member_user_id = ?
                ORDER BY ec.created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return {
            "granted_by_me": [self._format_family_row(r) for r in granted],
            "authorized_for": [self._format_family_row(r) for r in received],
        }

    def respond_family_contact(self, *, contact_id: str, member_user_id: str, accept: bool) -> Any:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute("SELECT * FROM emergency_contacts WHERE id = ? LIMIT 1", (contact_id,)).fetchone()
            if not row:
                return None
            if row["member_user_id"] != member_user_id:
                return "FORBIDDEN"
            if row["status"] == "revoked":
                return "REVOKED"
            new_st = "active" if accept else "declined"
            conn.execute(
                "UPDATE emergency_contacts SET status = ?, updated_at = ? WHERE id = ?",
                (new_st, now, contact_id),
            )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=member_user_id,
                action=f"family_contact_{new_st}",
                target_type="emergency_contact",
                target_id=contact_id,
            )
        return self.get_family_contact(contact_id)

    def revoke_family_contact(self, *, contact_id: str, actor_id: str, is_admin: bool) -> Any:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute("SELECT * FROM emergency_contacts WHERE id = ? LIMIT 1", (contact_id,)).fetchone()
            if not row:
                return None
            if not is_admin and row["owner_user_id"] != actor_id:
                return "FORBIDDEN"
            conn.execute(
                "UPDATE emergency_contacts SET status = 'revoked', revoked_at = ?, updated_at = ? WHERE id = ?",
                (now, now, contact_id),
            )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=actor_id,
                action="family_contact_revoked",
                target_type="emergency_contact",
                target_id=contact_id,
            )
        return self.get_family_contact(contact_id)

    def has_active_family_permission(self, *, owner_user_id: str, member_user_id: str, permission: str) -> bool:
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                "SELECT * FROM emergency_contacts WHERE owner_user_id = ? AND member_user_id = ? AND status = 'active' LIMIT 1",
                (owner_user_id, member_user_id),
            ).fetchone()
        return bool(row and row[permission])

    # --- Public Sanitized Request Sharing ---

    def create_or_get_share_link(self, *, request_id: str, actor_id: str) -> Dict[str, Any]:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            existing = conn.execute(
                "SELECT * FROM request_share_links WHERE request_id = ? LIMIT 1", (request_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE request_share_links SET is_active = 1, updated_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
                row = conn.execute("SELECT * FROM request_share_links WHERE id = ?", (existing["id"],)).fetchone()
            else:
                token = secrets.token_urlsafe(16)
                lid = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO request_share_links (id, request_id, share_token, created_by, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (lid, request_id, token, actor_id, now, now),
                )
                row = conn.execute("SELECT * FROM request_share_links WHERE id = ?", (lid,)).fetchone()
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=actor_id,
                action="share_link_activated",
                target_type="blood_request",
                target_id=request_id,
            )
        return {**dict(row), "is_active": bool(row["is_active"])}

    def disable_share_link(self, *, request_id: str, actor_id: str) -> Optional[Dict[str, Any]]:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            cur = conn.execute(
                "UPDATE request_share_links SET is_active = 0, updated_at = ? WHERE request_id = ?",
                (now, request_id),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute("SELECT * FROM request_share_links WHERE request_id = ? LIMIT 1", (request_id,)).fetchone()
        return {**dict(row), "is_active": False}

    def get_public_shared_request_by_token(self, token: str) -> Any:
        with self._connect() as conn:  # type: ignore[attr-defined]
            link = conn.execute(
                "SELECT * FROM request_share_links WHERE share_token = ? LIMIT 1", (token,)
            ).fetchone()
            if not link:
                return None
            req = conn.execute(
                "SELECT * FROM blood_requests WHERE id = ? LIMIT 1", (link["request_id"],)
            ).fetchone()
            if not req:
                return None
        is_closed = req["status"] in ("fulfilled", "cancelled", "expired")
        if not bool(link["is_active"]) or is_closed:
            return {"expired_or_disabled": True, "status": req["status"], "request_id": req["id"]}
        # Strictly return only public-safe fields (NO names, phone, docs, or chat)
        return {
            "expired_or_disabled": False,
            "request_id": req["id"],
            "blood_group": req["blood_group"],
            "units_requested": int(req["units_requested"]),
            "hospital_name": req["hospital_name"],
            "hospital_location": req["hospital_location"],
            "city": req["city"],
            "approximate_location": req["approximate_location"],
            "urgency": req["urgency"],
            "status": req["status"],
            "hospital_verification_status": req["hospital_verification_status"] if "hospital_verification_status" in req.keys() else "unconfirmed",
            "expires_at": req["expires_at"],
            "safety_notice": "Shared LifeLink request status. Private phone numbers and documents remain protected.",
        }

    def report_shared_request_by_token(
        self, *, token: str, reporter_id: Optional[str], reason: str, description: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            link = conn.execute("SELECT * FROM request_share_links WHERE share_token = ? LIMIT 1", (token,)).fetchone()
            if not link:
                return None
            # If anonymous public report, attribute to link creator? Better: lookup any reporter_id or fall back gracefully
            eff_reporter = reporter_id or link["created_by"]
            return self.create_report(  # type: ignore[attr-defined]
                reporter_id=eff_reporter,
                reported_user_id=None,
                request_id=link["request_id"],
                reason=f"[Shared Link Report] {reason}",
                description=description,
            )


class Phase2SupabaseMixin:
    """Supabase implementations for Phase 2 add-on features."""

    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        p = self.get_profile_by_id(user_id) or {}  # type: ignore[attr-defined]
        a11y = p.get("accessibility_prefs") or {}
        np_rows = (
            self.client.table("user_notification_preferences").select("*").eq("user_id", user_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        np = np_rows[0] if np_rows else {}
        return {
            "preferred_language": p.get("preferred_language", "en"),
            "text_size": a11y.get("text_size", "normal"),
            "high_contrast": bool(a11y.get("high_contrast", False)),
            "in_app_enabled": bool(np.get("in_app_enabled", True)),
            "quiet_hours_enabled": bool(np.get("quiet_hours_enabled", True)),
            "emergency_override_quiet_hours": bool(np.get("emergency_override_quiet_hours", True)),
            "reminder_frequency_days": int(np.get("reminder_frequency_days", 30)),
        }

    def update_user_preferences(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        cur = self.get_user_preferences(user_id)
        lang = payload.get("preferred_language") or cur["preferred_language"]
        a11y = {
            "text_size": payload.get("text_size") or cur["text_size"],
            "high_contrast": payload["high_contrast"] if "high_contrast" in payload else cur["high_contrast"],
        }
        p = self.get_profile_by_id(user_id) or {}  # type: ignore[attr-defined]
        existing_a11y = p.get("accessibility_prefs") or {}
        if isinstance(existing_a11y, dict) and "recovery_hashes" in existing_a11y:
            a11y["recovery_hashes"] = existing_a11y["recovery_hashes"]
        self.client.table("profiles").update(  # type: ignore[attr-defined]
            {"preferred_language": lang, "accessibility_prefs": a11y}
        ).eq("id", user_id).execute()
        self.client.table("user_notification_preferences").upsert(  # type: ignore[attr-defined]
            {
                "user_id": user_id,
                "in_app_enabled": payload.get("in_app_enabled", cur["in_app_enabled"]),
                "quiet_hours_enabled": payload.get("quiet_hours_enabled", cur["quiet_hours_enabled"]),
                "emergency_override_quiet_hours": payload.get(
                    "emergency_override_quiet_hours", cur["emergency_override_quiet_hours"]
                ),
                "reminder_frequency_days": payload.get("reminder_frequency_days", cur["reminder_frequency_days"]),
            },
            on_conflict="user_id",
        ).execute()
        return self.get_user_preferences(user_id)

    def get_donor_calendar(self, donor_id: str, user_id: str) -> Dict[str, Any]:
        dp_rows = (
            self.client.table("donor_profiles").select("*").eq("id", donor_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        dp = dp_rows[0] if dp_rows else {}
        cal_rows = (
            self.client.table("donor_availability").select("*").eq("donor_id", donor_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        cal = cal_rows[0] if cal_rows else {}
        prefs = self.get_user_preferences(user_id)
        return {
            "donor_id": donor_id,
            "availability_status": dp.get("availability_status", "unavailable"),
            "available_dates": cal.get("available_dates") or [],
            "preferred_distance_km": int(cal.get("preferred_distance_km", 25)),
            "quiet_hours_start": cal.get("quiet_hours_start"),
            "quiet_hours_end": cal.get("quiet_hours_end"),
            "paused_until": cal.get("paused_until"),
            "emergency_notifications_enabled": bool(dp.get("emergency_notifications_enabled", True)),
            "quiet_hours_enabled": prefs["quiet_hours_enabled"],
            "emergency_override_quiet_hours": prefs["emergency_override_quiet_hours"],
            "last_availability_updated_at": dp.get("last_availability_updated_at") or dp.get("updated_at"),
            "disclaimer": "Availability is self-declared and does not determine medical donation eligibility.",
        }

    def upsert_donor_calendar(self, *, donor_id: str, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        cur = self.get_donor_calendar(donor_id, user_id)
        avail = payload.get("availability_status") or cur["availability_status"]
        notif = payload.get("emergency_notifications_enabled", cur["emergency_notifications_enabled"])
        self.client.table("donor_profiles").update(  # type: ignore[attr-defined]
            {
                "availability_status": avail,
                "emergency_notifications_enabled": notif,
                "last_availability_updated_at": now,
            }
        ).eq("id", donor_id).execute()
        self.client.table("donor_availability").upsert(  # type: ignore[attr-defined]
            {
                "donor_id": donor_id,
                "available_dates": payload.get("available_dates") if payload.get("available_dates") is not None else cur["available_dates"],
                "preferred_distance_km": payload.get("preferred_distance_km") or cur["preferred_distance_km"],
                "quiet_hours_start": payload.get("quiet_hours_start", cur["quiet_hours_start"]),
                "quiet_hours_end": payload.get("quiet_hours_end", cur["quiet_hours_end"]),
                "paused_until": payload.get("paused_until", cur["paused_until"]),
            },
            on_conflict="donor_id",
        ).execute()
        return self.get_donor_calendar(donor_id, user_id)

    def invite_family_contact(
        self,
        *,
        owner_user_id: str,
        member_identifier: str,
        relationship: str,
        can_create_requests: bool,
        can_manage_requests: bool,
    ) -> Optional[Dict[str, Any]]:
        ident = member_identifier.strip()
        rows = (
            self.client.table("profiles")  # type: ignore[attr-defined]
            .select("*")
            .or_(f"email.eq.{ident.lower()},phone_number.eq.{ident}")
            .limit(1)
            .execute()
        ).data or []
        if not rows or rows[0]["account_status"] != "active":
            return None
        target = rows[0]
        if target["id"] == owner_user_id:
            raise ValueError("Cannot add yourself as a delegated family member.")
        res = (
            self.client.table("emergency_contacts")  # type: ignore[attr-defined]
            .upsert(
                {
                    "owner_user_id": owner_user_id,
                    "member_user_id": target["id"],
                    "relationship": relationship.strip(),
                    "can_create_requests": can_create_requests,
                    "can_manage_requests": can_manage_requests,
                    "status": "pending",
                    "revoked_at": None,
                },
                on_conflict="owner_user_id,member_user_id",
            )
            .execute()
        )
        return self.get_family_contact(res.data[0]["id"])

    def _format_family_supa(self, r: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": r["id"],
            "owner_user_id": r["owner_user_id"],
            "owner_display_name": mask_display_name((r.get("owner") or {}).get("full_name", "Family Member")),
            "member_user_id": r["member_user_id"],
            "member_display_name": mask_display_name((r.get("member") or {}).get("full_name", "Member")),
            "relationship": r["relationship"],
            "can_create_requests": bool(r["can_create_requests"]),
            "can_manage_requests": bool(r["can_manage_requests"]),
            "status": r["status"],
            "created_at": str(r["created_at"]),
            "revoked_at": str(r["revoked_at"]) if r.get("revoked_at") else None,
        }

    def get_family_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        rows = (
            self.client.table("emergency_contacts")  # type: ignore[attr-defined]
            .select("*, owner:profiles!emergency_contacts_owner_user_id_fkey(full_name), member:profiles!emergency_contacts_member_user_id_fkey(full_name)")
            .eq("id", contact_id)
            .limit(1)
            .execute()
        ).data or []
        return self._format_family_supa(rows[0]) if rows else None

    def list_family_contacts_for_user(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        sel = "*, owner:profiles!emergency_contacts_owner_user_id_fkey(full_name), member:profiles!emergency_contacts_member_user_id_fkey(full_name)"
        granted = (
            self.client.table("emergency_contacts").select(sel).eq("owner_user_id", user_id).execute()  # type: ignore[attr-defined]
        ).data or []
        received = (
            self.client.table("emergency_contacts").select(sel).eq("member_user_id", user_id).execute()  # type: ignore[attr-defined]
        ).data or []
        return {
            "granted_by_me": [self._format_family_supa(r) for r in granted],
            "authorized_for": [self._format_family_supa(r) for r in received],
        }

    def respond_family_contact(self, *, contact_id: str, member_user_id: str, accept: bool) -> Any:
        rows = (
            self.client.table("emergency_contacts").select("*").eq("id", contact_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        if not rows:
            return None
        row = rows[0]
        if row["member_user_id"] != member_user_id:
            return "FORBIDDEN"
        if row["status"] == "revoked":
            return "REVOKED"
        self.client.table("emergency_contacts").update(  # type: ignore[attr-defined]
            {"status": "active" if accept else "declined"}
        ).eq("id", contact_id).execute()
        return self.get_family_contact(contact_id)

    def revoke_family_contact(self, *, contact_id: str, actor_id: str, is_admin: bool) -> Any:
        rows = (
            self.client.table("emergency_contacts").select("*").eq("id", contact_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        if not rows:
            return None
        row = rows[0]
        if not is_admin and row["owner_user_id"] != actor_id:
            return "FORBIDDEN"
        self.client.table("emergency_contacts").update(  # type: ignore[attr-defined]
            {"status": "revoked", "revoked_at": _now_iso()}
        ).eq("id", contact_id).execute()
        return self.get_family_contact(contact_id)

    def has_active_family_permission(self, *, owner_user_id: str, member_user_id: str, permission: str) -> bool:
        rows = (
            self.client.table("emergency_contacts")  # type: ignore[attr-defined]
            .select("*")
            .eq("owner_user_id", owner_user_id)
            .eq("member_user_id", member_user_id)
            .eq("status", "active")
            .limit(1)
            .execute()
        ).data or []
        return bool(rows and rows[0].get(permission))

    def create_or_get_share_link(self, *, request_id: str, actor_id: str) -> Dict[str, Any]:
        rows = (
            self.client.table("request_share_links").select("*").eq("request_id", request_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        if rows:
            res = (
                self.client.table("request_share_links")  # type: ignore[attr-defined]
                .update({"is_active": True})
                .eq("id", rows[0]["id"])
                .execute()
            )
            return res.data[0]
        token = secrets.token_urlsafe(16)
        res = (
            self.client.table("request_share_links")  # type: ignore[attr-defined]
            .insert({"request_id": request_id, "share_token": token, "created_by": actor_id, "is_active": True})
            .execute()
        )
        return res.data[0]

    def disable_share_link(self, *, request_id: str, actor_id: str) -> Optional[Dict[str, Any]]:
        res = (
            self.client.table("request_share_links")  # type: ignore[attr-defined]
            .update({"is_active": False})
            .eq("request_id", request_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def get_public_shared_request_by_token(self, token: str) -> Any:
        rows = (
            self.client.table("request_share_links").select("*").eq("share_token", token).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        if not rows:
            return None
        link = rows[0]
        req = self.get_blood_request(link["request_id"])  # type: ignore[attr-defined]
        if not req:
            return None
        is_closed = req["status"] in ("fulfilled", "cancelled", "expired")
        if not link.get("is_active") or is_closed:
            return {"expired_or_disabled": True, "status": req["status"], "request_id": req["id"]}
        return {
            "expired_or_disabled": False,
            "request_id": req["id"],
            "blood_group": req["blood_group"],
            "units_requested": int(req["units_requested"]),
            "hospital_name": req["hospital_name"],
            "hospital_location": req["hospital_location"],
            "city": req["city"],
            "approximate_location": req["approximate_location"],
            "urgency": req["urgency"],
            "status": req["status"],
            "hospital_verification_status": req.get("hospital_verification_status", "unconfirmed"),
            "expires_at": str(req["expires_at"]),
            "safety_notice": "Shared LifeLink request status. Private phone numbers and documents remain protected.",
        }

    def report_shared_request_by_token(
        self, *, token: str, reporter_id: Optional[str], reason: str, description: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        rows = (
            self.client.table("request_share_links").select("*").eq("share_token", token).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        if not rows:
            return None
        link = rows[0]
        return self.create_report(  # type: ignore[attr-defined]
            reporter_id=reporter_id or link["created_by"],
            reported_user_id=None,
            request_id=link["request_id"],
            reason=f"[Shared Link Report] {reason}",
            description=description,
        )
