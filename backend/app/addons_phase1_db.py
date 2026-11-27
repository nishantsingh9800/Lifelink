"""Phase 1 Add-On Repository Mixins (SQLite + Supabase) for Essential Usability & Coordination Core."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config import Settings
from backend.app.utils.security import mask_display_name

PHASE1_AVAILABILITY_LABELS = {
    "directory_listing_only": "Directory listing only",
    "availability_not_available": "Availability information not available",
    "contact_required": "Contact required",
    "availability_confirmed_by_facility": "Availability confirmed by facility",
    "availability_unavailable": "Availability unavailable",
    "information_outdated": "Information outdated",
    "confirmed_available": "Confirmed available",
    "reported_awaiting_confirmation": "Reported available — awaiting confirmation",
    "availability_unknown": "Availability unknown",
    "currently_unavailable": "Currently unavailable",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_live_tracking_summary(
    req: Dict[str, Any],
    history: List[Dict[str, Any]],
    matches: List[Dict[str, Any]],
    responses: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble an 8-step lifecycle timeline and non-PII aggregate counts for a blood request."""
    status = req["status"]
    escalation_stage = int(req.get("escalation_stage", 1))
    hosp_ver = req.get("hospital_verification_status") or "unconfirmed"

    notified_count = len(matches)
    accepted_count = sum(1 for r in responses if r.get("response") == "accepted")
    declined_count = sum(1 for r in responses if r.get("response") == "declined")
    responses_count = len(responses)

    ts_by_status: Dict[str, str] = {}
    for item in history:
        st = item.get("new_status")
        if st and st not in ts_by_status:
            ts_by_status[st] = str(item["created_at"])

    has_matching = notified_count > 0 or status != "created"
    has_notified = notified_count > 0 or status in {
        "donors_notified",
        "responses_received",
        "connection_in_progress",
        "blood_bank_assistance",
        "escalation_in_progress",
        "fulfilled",
    }
    has_responses = responses_count > 0 or status in {"responses_received", "connection_in_progress", "fulfilled"}
    has_connected = accepted_count > 0 or status in {"connection_in_progress", "fulfilled"}
    is_closed = status in {"fulfilled", "unresolved", "cancelled", "expired"}

    # Step 2 (Verification pending or completed)
    if hosp_ver == "confirmed_genuine":
        ver_state = "completed"
        ver_detail = f"Verified by hospital ({req.get('hospital_confirmed_at') or req['updated_at']})."
    elif hosp_ver == "hospital_updated":
        ver_state = "completed"
        ver_detail = "Reviewed and updated by verified hospital representative."
    elif hosp_ver == "flagged_invalid":
        ver_state = "terminal"
        ver_detail = "Flagged by verified hospital review."
    else:
        ver_state = "completed" if is_closed else "current"
        ver_detail = "Hospital verification pending — treat urgent requests with hospital blood bank directly."

    if status == "created":
        active_idx = 3 if ver_state == "current" else 3
    elif status == "matching":
        active_idx = 3
    elif status in ("donors_notified", "blood_bank_assistance", "escalation_in_progress"):
        active_idx = 4
    elif status == "responses_received":
        active_idx = 5
    elif status == "connection_in_progress":
        active_idx = 7
    elif is_closed:
        active_idx = 8
    else:
        active_idx = 4

    def _state(idx: int, done: bool) -> str:
        if is_closed and idx == 8:
            return "terminal" if status in ("cancelled", "expired", "unresolved") else "completed"
        if done and idx < active_idx:
            return "completed"
        if idx == active_idx and not is_closed:
            return "current"
        return "completed" if done else "pending"

    timeline = [
        {
            "step": 1,
            "key": "submitted",
            "label": "Request submitted",
            "state": "completed",
            "timestamp": str(req["created_at"]),
            "detail": f"Submitted for {req['blood_group']} ({req['units_requested']} unit(s)) at {req['hospital_name']}.",
        },
        {
            "step": 2,
            "key": "verification",
            "label": "Verification pending or completed",
            "state": ver_state,
            "timestamp": req.get("hospital_confirmed_at"),
            "detail": ver_detail,
        },
        {
            "step": 3,
            "key": "matching_started",
            "label": "Donor matching started",
            "state": _state(3, has_matching),
            "timestamp": ts_by_status.get("matching") or ts_by_status.get("donors_notified"),
            "detail": f"Rule-based compatibility & proximity scoring (Stage {escalation_stage} of 5).",
        },
        {
            "step": 4,
            "key": "donors_notified",
            "label": "Donors notified",
            "state": _state(4, has_notified),
            "timestamp": ts_by_status.get("donors_notified") or ts_by_status.get("escalation_in_progress"),
            "detail": (
                f"{notified_count} potential donor candidate(s) notified."
                if notified_count > 0
                else "No matching local donors notified yet."
            ),
        },
        {
            "step": 5,
            "key": "responses_received",
            "label": "Donor responses received",
            "state": _state(5, has_responses),
            "timestamp": ts_by_status.get("responses_received"),
            "detail": f"{responses_count} total response(s) recorded ({accepted_count} interested, {declined_count} declined).",
        },
        {
            "step": 6,
            "key": "donor_connected",
            "label": "Donor connected",
            "state": _state(6, has_connected),
            "timestamp": ts_by_status.get("connection_in_progress"),
            "detail": (
                f"{accepted_count} donor(s) accepted and private coordination opened."
                if has_connected
                else "Awaiting donor acceptance."
            ),
        },
        {
            "step": 7,
            "key": "coordination_in_progress",
            "label": "Donation coordination in progress",
            "state": _state(7, has_connected),
            "timestamp": ts_by_status.get("connection_in_progress"),
            "detail": "Coordinate arrival, hospital blood bank counter check, and safety screening.",
        },
        {
            "step": 8,
            "key": "closed_outcome",
            "label": "Request fulfilled, cancelled or expired",
            "state": _state(8, is_closed),
            "timestamp": ts_by_status.get(status) if is_closed else None,
            "detail": f"Closed as '{status}'." if is_closed else "Open until fulfilled, cancelled, or expired.",
        },
    ]

    next_steps: List[str] = []
    if is_closed:
        next_steps.append(f"This request is closed ({status}). No further donor outreach will be sent.")
    else:
        if hosp_ver == "unconfirmed":
            next_steps.append("Coordinate directly with the treating hospital blood bank; hospital verification is pending.")
        if notified_count == 0:
            next_steps.append("Run 'Find & Notify Donors' to alert compatible nearby donors, or check Blood Banks.")
        elif accepted_count == 0 and escalation_stage < 4:
            next_steps.append("If donors have not accepted yet, trigger 'Expand / Escalate Stage' to widen outreach or activate Blood-Bank Fallback.")
        elif escalation_stage >= 4 or status == "blood_bank_assistance":
            next_steps.append("Contact licensed blood banks listed in the Blood-Bank Directory / e-RaktKosh and record call outcomes.")
        if accepted_count > 0:
            next_steps.append("Open Messages to coordinate with accepting donor(s) and verify hospital transfusion arrival.")

    return {
        "request_id": str(req["id"]),
        "status": status,
        "urgency": req["urgency"],
        "blood_group": req["blood_group"],
        "units_requested": int(req["units_requested"]),
        "hospital_name": req["hospital_name"],
        "hospital_verification_status": hosp_ver,
        "escalation_stage": escalation_stage,
        "donors_notified": notified_count,
        "responses_received": responses_count,
        "donors_interested": accepted_count,
        "donors_declined": declined_count,
        "last_status_update": str(req["updated_at"]),
        "expires_at": str(req["expires_at"]),
        "timeline": timeline,
        "next_steps": next_steps,
    }


class Phase1SQLiteMixin:
    """SQLite implementations for Phase 1 add-on features."""

    def _init_phase1_schema(self, conn: sqlite3.Connection) -> None:
        # 1. Upgrade profiles role CHECK constraint safely if 'hospital' is missing
        tbl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='profiles'"
        ).fetchone()
        if tbl and "'hospital'" not in (tbl["sql"] or ""):
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.executescript(
                """
                CREATE TABLE profiles_new (
                    id TEXT PRIMARY KEY,
                    auth_user_id TEXT UNIQUE,
                    full_name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    phone_number TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'requester' CHECK (role IN ('requester', 'donor', 'hospital', 'admin')),
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
                INSERT INTO profiles_new SELECT
                    id, auth_user_id, full_name, email, phone_number, password_hash, role,
                    city, approximate_location, date_of_birth, account_status, phone_verified,
                    aadhaar_last4, aadhaar_hash, aadhaar_verified, aadhaar_consent_at,
                    terms_accepted_at, created_at, updated_at
                FROM profiles;
                DROP TABLE profiles;
                ALTER TABLE profiles_new RENAME TO profiles;
                """
            )
            conn.execute("PRAGMA foreign_keys = ON;")

        # 2. Phase 1 tables
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hospitals (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
                hospital_name TEXT NOT NULL,
                registration_number TEXT NOT NULL,
                address TEXT NOT NULL,
                city TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT '',
                official_phone TEXT NOT NULL,
                official_email TEXT,
                authorized_rep_name TEXT NOT NULL,
                authorized_rep_role TEXT NOT NULL,
                verification_status TEXT NOT NULL DEFAULT 'pending_verification'
                    CHECK (verification_status IN ('pending_verification', 'under_review', 'verified', 'rejected', 'suspended')),
                admin_notes TEXT,
                verified_by TEXT REFERENCES profiles(id),
                verified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hospital_verification_documents (
                id TEXT PRIMARY KEY,
                hospital_id TEXT NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
                document_type TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'pending_review',
                reviewed_by TEXT REFERENCES profiles(id),
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hospital_verification_history (
                id TEXT PRIMARY KEY,
                hospital_id TEXT NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
                previous_status TEXT,
                new_status TEXT NOT NULL,
                actor_id TEXT REFERENCES profiles(id),
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS request_coordinators (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL REFERENCES blood_requests(id) ON DELETE CASCADE,
                requester_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                coordinator_user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'invited'
                    CHECK (status IN ('invited', 'active', 'declined', 'revoked')),
                can_chat INTEGER NOT NULL DEFAULT 1,
                can_contact_blood_banks INTEGER NOT NULL DEFAULT 1,
                can_update_progress INTEGER NOT NULL DEFAULT 1,
                invited_at TEXT NOT NULL,
                responded_at TEXT,
                revoked_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (request_id, coordinator_user_id)
            );

            CREATE TABLE IF NOT EXISTS blood_bank_stock_updates (
                id TEXT PRIMARY KEY,
                blood_bank_id TEXT NOT NULL REFERENCES blood_banks(id) ON DELETE CASCADE,
                blood_group TEXT NOT NULL,
                availability_status TEXT NOT NULL,
                notes TEXT,
                updated_by TEXT REFERENCES profiles(id),
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_hospitals_status_city ON hospitals(verification_status, city);
            CREATE INDEX IF NOT EXISTS idx_rc_user_status ON request_coordinators(coordinator_user_id, status);
            CREATE INDEX IF NOT EXISTS idx_rc_req_status ON request_coordinators(request_id, status);
            CREATE INDEX IF NOT EXISTS idx_bbsu_bank ON blood_bank_stock_updates(blood_bank_id, updated_at);
            """
        )

        # 3. Phase 1 columns on blood_requests
        br_cols = {r["name"] for r in conn.execute("PRAGMA table_info(blood_requests)").fetchall()}
        if "is_emergency_quick" not in br_cols:
            conn.execute("ALTER TABLE blood_requests ADD COLUMN is_emergency_quick INTEGER NOT NULL DEFAULT 0")
        if "coordinator_contact_name" not in br_cols:
            conn.execute("ALTER TABLE blood_requests ADD COLUMN coordinator_contact_name TEXT")
        if "coordinator_contact_relation" not in br_cols:
            conn.execute("ALTER TABLE blood_requests ADD COLUMN coordinator_contact_relation TEXT")
        if "hospital_id" not in br_cols:
            conn.execute("ALTER TABLE blood_requests ADD COLUMN hospital_id TEXT REFERENCES hospitals(id)")
        if "hospital_verification_status" not in br_cols:
            conn.execute(
                "ALTER TABLE blood_requests ADD COLUMN hospital_verification_status TEXT NOT NULL DEFAULT 'unconfirmed'"
            )
        if "hospital_confirmed_by" not in br_cols:
            conn.execute("ALTER TABLE blood_requests ADD COLUMN hospital_confirmed_by TEXT REFERENCES profiles(id)")
        if "hospital_confirmed_at" not in br_cols:
            conn.execute("ALTER TABLE blood_requests ADD COLUMN hospital_confirmed_at TEXT")
        if "cancellation_reason" not in br_cols:
            conn.execute("ALTER TABLE blood_requests ADD COLUMN cancellation_reason TEXT")

    def _close_request_side_effects_sqlite(
        self,
        conn: sqlite3.Connection,
        *,
        request_id: str,
        blood_group: str,
        hospital_name: str,
        notification_type: str,
        title: str,
        message: str,
        new_match_status: str,
    ) -> None:
        now = _now_iso()
        # Notify all previously contacted or accepted donors
        matched = conn.execute(
            """
            SELECT DISTINCT dp.user_id
            FROM donor_matches dm
            JOIN donor_profiles dp ON dp.id = dm.donor_id
            WHERE dm.request_id = ? AND dm.match_status IN ('notified', 'accepted', 'candidate')
            """,
            (request_id,),
        ).fetchall()
        for row in matched:
            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=row["user_id"],
                notification_type=notification_type,
                title=title,
                message=message,
                related_request_id=request_id,
            )

        # Notify active coordinators as well
        coords = conn.execute(
            "SELECT coordinator_user_id FROM request_coordinators WHERE request_id = ? AND status = 'active'",
            (request_id,),
        ).fetchall()
        for c in coords:
            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=c["coordinator_user_id"],
                notification_type=notification_type,
                title=title,
                message=message,
                related_request_id=request_id,
            )

        conn.execute(
            """
            UPDATE donor_matches
            SET match_status = ?, updated_at = ?
            WHERE request_id = ? AND match_status IN ('candidate', 'notified')
            """,
            (new_match_status, now, request_id),
        )
        conn.execute(
            "UPDATE conversations SET status = 'closed', updated_at = ? WHERE request_id = ? AND status = 'active'",
            (now, request_id),
        )
        conn.execute(
            "UPDATE donor_location_tracking SET is_active = 0, tracking_status = 'stopped', updated_at = ? WHERE request_id = ?",
            (now, request_id),
        )
        conn.execute(
            "UPDATE request_share_links SET is_active = 0, updated_at = ? WHERE request_id = ?",
            (now, request_id),
        )

    def get_request_tracking_summary(self, request_id: str) -> Optional[Dict[str, Any]]:
        req = self.get_blood_request(request_id)  # type: ignore[attr-defined]
        if not req:
            return None
        history = self.get_request_status_history(request_id)  # type: ignore[attr-defined]
        matches = self.list_matches_for_request(request_id)  # type: ignore[attr-defined]
        responses = self.list_responses_for_request(request_id)  # type: ignore[attr-defined]
        return build_live_tracking_summary(req, history, matches, responses)

    # --- Coordinators ---

    def is_active_coordinator_for_request(self, user_id: str, request_id: str, permission: Optional[str] = None) -> bool:
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                "SELECT * FROM request_coordinators WHERE request_id = ? AND coordinator_user_id = ? AND status = 'active' LIMIT 1",
                (request_id, user_id),
            ).fetchone()
        if not row:
            return False
        if permission:
            return bool(row[permission])
        return True

    def invite_coordinator(
        self,
        *,
        request_row: Dict[str, Any],
        requester_id: str,
        coordinator_identifier: str,
        can_chat: bool,
        can_contact_blood_banks: bool,
        can_update_progress: bool,
    ) -> Optional[Dict[str, Any]]:
        ident = coordinator_identifier.strip()
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            target = conn.execute(
                """
                SELECT * FROM profiles
                WHERE lower(email) = lower(?) OR phone_number = ?
                LIMIT 1
                """,
                (ident, ident),
            ).fetchone()
            if not target or target["account_status"] != "active":
                return None
            if target["id"] == requester_id:
                raise ValueError("Requester already owns this request and does not need coordinator assignment.")

            existing = conn.execute(
                "SELECT * FROM request_coordinators WHERE request_id = ? AND coordinator_user_id = ? LIMIT 1",
                (request_row["id"], target["id"]),
            ).fetchone()
            if existing:
                assign_id = existing["id"]
                conn.execute(
                    """
                    UPDATE request_coordinators
                    SET status = 'invited', can_chat = ?, can_contact_blood_banks = ?,
                        can_update_progress = ?, invited_at = ?, responded_at = NULL,
                        revoked_at = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (int(can_chat), int(can_contact_blood_banks), int(can_update_progress), now, now, assign_id),
                )
            else:
                assign_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO request_coordinators (
                        id, request_id, requester_id, coordinator_user_id, status,
                        can_chat, can_contact_blood_banks, can_update_progress,
                        invited_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'invited', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        assign_id,
                        request_row["id"],
                        requester_id,
                        target["id"],
                        int(can_chat),
                        int(can_contact_blood_banks),
                        int(can_update_progress),
                        now,
                        now,
                        now,
                    ),
                )

            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=target["id"],
                notification_type="request_status_update",
                title="Emergency Coordinator Assignment Invite",
                message=(
                    f"You have been authorized to help coordinate {request_row['blood_group']} request "
                    f"at {request_row['hospital_name']}. Accept or decline from your Dashboard."
                ),
                related_request_id=request_row["id"],
            )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=requester_id,
                action="coordinator_invited",
                target_type="request_coordinator",
                target_id=assign_id,
                metadata_json=json.dumps({"request_id": request_row["id"], "coordinator_user_id": target["id"]}),
            )
        return self.get_coordinator_assignment(assign_id)

    def get_coordinator_assignment(self, assign_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT rc.*, p.full_name AS coordinator_name,
                       br.blood_group AS request_blood_group, br.hospital_name AS request_hospital_name, br.status AS request_status
                FROM request_coordinators rc
                JOIN profiles p ON p.id = rc.coordinator_user_id
                JOIN blood_requests br ON br.id = rc.request_id
                WHERE rc.id = ? LIMIT 1
                """,
                (assign_id,),
            ).fetchone()
        if not row:
            return None
        return self._format_coordinator_row(row)

    @staticmethod
    def _format_coordinator_row(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "request_id": row["request_id"],
            "requester_id": row["requester_id"],
            "coordinator_user_id": row["coordinator_user_id"],
            "coordinator_display_name": mask_display_name(row["coordinator_name"]),
            "request_blood_group": row["request_blood_group"],
            "request_hospital_name": row["request_hospital_name"],
            "request_status": row["request_status"],
            "status": row["status"],
            "can_chat": bool(row["can_chat"]),
            "can_contact_blood_banks": bool(row["can_contact_blood_banks"]),
            "can_update_progress": bool(row["can_update_progress"]),
            "invited_at": row["invited_at"],
            "responded_at": row["responded_at"],
            "revoked_at": row["revoked_at"],
        }

    def list_coordinators_for_request(self, request_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(
                """
                SELECT rc.*, p.full_name AS coordinator_name,
                       br.blood_group AS request_blood_group, br.hospital_name AS request_hospital_name, br.status AS request_status
                FROM request_coordinators rc
                JOIN profiles p ON p.id = rc.coordinator_user_id
                JOIN blood_requests br ON br.id = rc.request_id
                WHERE rc.request_id = ?
                ORDER BY rc.created_at DESC
                """,
                (request_id,),
            ).fetchall()
        return [self._format_coordinator_row(r) for r in rows]

    def list_my_coordinator_assignments(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(
                """
                SELECT rc.*, p.full_name AS coordinator_name,
                       br.blood_group AS request_blood_group, br.hospital_name AS request_hospital_name, br.status AS request_status
                FROM request_coordinators rc
                JOIN profiles p ON p.id = rc.coordinator_user_id
                JOIN blood_requests br ON br.id = rc.request_id
                WHERE rc.coordinator_user_id = ?
                ORDER BY rc.updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._format_coordinator_row(r) for r in rows]

    def respond_to_coordinator_invite(self, *, assign_id: str, coordinator_user_id: str, accept: bool) -> Any:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute("SELECT * FROM request_coordinators WHERE id = ? LIMIT 1", (assign_id,)).fetchone()
            if not row:
                return None
            if row["coordinator_user_id"] != coordinator_user_id:
                return "FORBIDDEN"
            if row["status"] == "revoked":
                return "REVOKED"
            new_status = "active" if accept else "declined"
            conn.execute(
                "UPDATE request_coordinators SET status = ?, responded_at = ?, updated_at = ? WHERE id = ?",
                (new_status, now, now, assign_id),
            )
            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=row["requester_id"],
                notification_type="request_status_update",
                title="Coordinator Response Recorded",
                message=f"Your invited emergency coordinator has {'accepted' if accept else 'declined'} the assignment.",
                related_request_id=row["request_id"],
            )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=coordinator_user_id,
                action=f"coordinator_{new_status}",
                target_type="request_coordinator",
                target_id=assign_id,
                metadata_json=json.dumps({"request_id": row["request_id"]}),
            )
        return self.get_coordinator_assignment(assign_id)

    def revoke_coordinator(self, *, assign_id: str, actor_id: str, is_admin: bool) -> Any:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute("SELECT * FROM request_coordinators WHERE id = ? LIMIT 1", (assign_id,)).fetchone()
            if not row:
                return None
            if not is_admin and row["requester_id"] != actor_id:
                return "FORBIDDEN"
            conn.execute(
                "UPDATE request_coordinators SET status = 'revoked', revoked_at = ?, updated_at = ? WHERE id = ?",
                (now, now, assign_id),
            )
            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=row["coordinator_user_id"],
                notification_type="request_status_update",
                title="Coordinator Access Revoked",
                message="Your emergency coordinator permissions for this blood request have been revoked.",
                related_request_id=row["request_id"],
            )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=actor_id,
                action="coordinator_revoked",
                target_type="request_coordinator",
                target_id=assign_id,
                metadata_json=json.dumps({"request_id": row["request_id"], "coordinator_user_id": row["coordinator_user_id"]}),
            )
        return self.get_coordinator_assignment(assign_id)

    def add_coordinator_progress_update(self, *, request_row: Dict[str, Any], actor_id: str, notes: str) -> Dict[str, Any]:
        now = _now_iso()
        request_id = str(request_row["id"])
        with self._connect() as conn:  # type: ignore[attr-defined]
            conn.execute(
                """
                INSERT INTO request_status_history (id, request_id, previous_status, new_status, changed_by, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), request_id, request_row["status"], request_row["status"], actor_id, f"[Coordinator Update] {notes}", now),
            )
            conn.execute("UPDATE blood_requests SET updated_at = ? WHERE id = ?", (now, request_id))
            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=str(request_row["requester_id"]),
                notification_type="request_status_update",
                title="Emergency Coordinator Update",
                message=f"Coordinator update for {request_row['hospital_name']}: {notes}",
                related_request_id=request_id,
            )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=actor_id,
                action="coordinator_progress_update",
                target_type="blood_request",
                target_id=request_id,
                metadata_json=json.dumps({"notes": notes}),
            )
        return self.get_blood_request(request_id)  # type: ignore[attr-defined]

    # --- Hospitals Verification & Verified Hospital Operations ---

    def upsert_hospital_profile(self, *, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            existing = conn.execute("SELECT * FROM hospitals WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
            if existing:
                prev_status = existing["verification_status"]
                new_status = "pending_verification" if prev_status in ("rejected", "suspended") else prev_status
                conn.execute(
                    """
                    UPDATE hospitals
                    SET hospital_name = ?, registration_number = ?, address = ?, city = ?, state = ?,
                        official_phone = ?, official_email = ?, authorized_rep_name = ?,
                        authorized_rep_role = ?, verification_status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload["hospital_name"],
                        payload["registration_number"],
                        payload["address"],
                        payload["city"],
                        payload.get("state", ""),
                        payload["official_phone"],
                        payload.get("official_email"),
                        payload["authorized_rep_name"],
                        payload["authorized_rep_role"],
                        new_status,
                        now,
                        existing["id"],
                    ),
                )
                hosp_id = existing["id"]
                if new_status != prev_status:
                    conn.execute(
                        """
                        INSERT INTO hospital_verification_history (id, hospital_id, previous_status, new_status, actor_id, notes, created_at)
                        VALUES (?, ?, ?, ?, ?, 'Hospital resubmitted registration details.', ?)
                        """,
                        (str(uuid.uuid4()), hosp_id, prev_status, new_status, user_id, now),
                    )
            else:
                hosp_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO hospitals (
                        id, user_id, hospital_name, registration_number, address, city, state,
                        official_phone, official_email, authorized_rep_name, authorized_rep_role,
                        verification_status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_verification', ?, ?)
                    """,
                    (
                        hosp_id,
                        user_id,
                        payload["hospital_name"],
                        payload["registration_number"],
                        payload["address"],
                        payload["city"],
                        payload.get("state", ""),
                        payload["official_phone"],
                        payload.get("official_email"),
                        payload["authorized_rep_name"],
                        payload["authorized_rep_role"],
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO hospital_verification_history (id, hospital_id, previous_status, new_status, actor_id, notes, created_at)
                    VALUES (?, ?, NULL, 'pending_verification', ?, 'Hospital registration submitted.', ?)
                    """,
                    (str(uuid.uuid4()), hosp_id, user_id, now),
                )
        row = self.get_hospital_by_id(hosp_id)
        assert row is not None
        return row

    def get_hospital_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute("SELECT * FROM hospitals WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_hospital_by_id(self, hospital_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute("SELECT * FROM hospitals WHERE id = ? LIMIT 1", (hospital_id,)).fetchone()
        return dict(row) if row else None

    def list_verified_hospitals(self, city: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM hospitals WHERE verification_status = 'verified'"
        params: List[Any] = []
        if city:
            sql += " AND lower(city) = lower(?)"
            params.append(city.strip())
        sql += " ORDER BY hospital_name ASC"
        with self._connect() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def store_hospital_document_bytes(
        self, *, hospital_id: str, safe_filename: str, content_bytes: bytes, settings: Settings
    ) -> str:
        target_dir = Path(settings.upload_dir) / "hospitals" / hospital_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = (target_dir / safe_filename).resolve()
        target_file.write_bytes(content_bytes)
        return str(Path("hospitals") / hospital_id / safe_filename).replace("\\", "/")

    def submit_hospital_document(self, *, hospital_id: str, document_type: str, storage_path: str) -> Dict[str, Any]:
        now = _now_iso()
        doc_id = str(uuid.uuid4())
        with self._connect() as conn:  # type: ignore[attr-defined]
            conn.execute(
                """
                INSERT INTO hospital_verification_documents (
                    id, hospital_id, document_type, storage_path, review_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending_review', ?, ?)
                """,
                (doc_id, hospital_id, document_type.strip(), storage_path, now, now),
            )
            row = conn.execute("SELECT * FROM hospital_verification_documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row)

    def list_hospital_documents(self, hospital_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(
                "SELECT * FROM hospital_verification_documents WHERE hospital_id = ? ORDER BY created_at DESC",
                (hospital_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_hospital_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                "SELECT * FROM hospital_verification_documents WHERE id = ? LIMIT 1", (doc_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_hospital_verification_history(self, hospital_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(
                "SELECT * FROM hospital_verification_history WHERE hospital_id = ? ORDER BY created_at ASC",
                (hospital_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def admin_list_hospitals(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM hospitals WHERE 1=1"
        params: List[Any] = []
        if status_filter:
            sql += " AND verification_status = ?"
            params.append(status_filter)
        sql += " ORDER BY created_at DESC"
        with self._connect() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(sql, params).fetchall()
        result: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            item["documents"] = self.list_hospital_documents(item["id"])
            result.append(item)
        return result

    def admin_review_hospital(
        self, *, hospital_id: str, verification_status: str, admin_id: str, notes: str
    ) -> Optional[Dict[str, Any]]:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            existing = conn.execute("SELECT * FROM hospitals WHERE id = ? LIMIT 1", (hospital_id,)).fetchone()
            if not existing:
                return None
            prev = existing["verification_status"]
            verified_at = now if verification_status == "verified" else existing["verified_at"]
            verified_by = admin_id if verification_status == "verified" else existing["verified_by"]
            conn.execute(
                """
                UPDATE hospitals
                SET verification_status = ?, admin_notes = ?, verified_by = ?, verified_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (verification_status, notes, verified_by, verified_at, now, hospital_id),
            )
            if verification_status in ("verified", "rejected"):
                doc_status = "verified" if verification_status == "verified" else "rejected"
                conn.execute(
                    """
                    UPDATE hospital_verification_documents
                    SET review_status = ?, reviewed_by = ?, notes = ?, updated_at = ?
                    WHERE hospital_id = ? AND review_status = 'pending_review'
                    """,
                    (doc_status, admin_id, notes, now, hospital_id),
                )
            conn.execute(
                """
                INSERT INTO hospital_verification_history (id, hospital_id, previous_status, new_status, actor_id, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), hospital_id, prev, verification_status, admin_id, notes, now),
            )
            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=existing["user_id"],
                notification_type="admin_notice",
                title=f"Hospital Verification: {verification_status.replace('_', ' ').title()}",
                message=f"Administrator reviewed {existing['hospital_name']}: {notes}",
                related_request_id=None,
            )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=admin_id,
                action=f"hospital_{verification_status}",
                target_type="hospital",
                target_id=hospital_id,
                metadata_json=json.dumps({"notes": notes, "previous_status": prev}),
            )
        return self.get_hospital_by_id(hospital_id)

    def hospital_list_requests(self, hospital_row: Dict[str, Any]) -> List[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(
                """
                SELECT * FROM blood_requests
                WHERE hospital_id = ?
                   OR lower(city) = lower(?)
                ORDER BY created_at DESC
                """,
                (hospital_row["id"], hospital_row["city"]),
            ).fetchall()
        return [dict(r) for r in rows]

    def hospital_can_manage_request(self, hospital_row: Dict[str, Any], req: Dict[str, Any]) -> bool:
        if req.get("hospital_id") and str(req["hospital_id"]) == str(hospital_row["id"]):
            return True
        if req.get("city", "").strip().lower() != hospital_row.get("city", "").strip().lower():
            return False
        # Require either hospital_id match or hospital_name substring overlap when hospital_id is unset
        h_name = hospital_row["hospital_name"].strip().lower()
        r_name = req.get("hospital_name", "").strip().lower()
        return h_name in r_name or r_name in h_name

    def hospital_confirm_or_update_request(
        self,
        *,
        hospital_row: Dict[str, Any],
        req: Dict[str, Any],
        actor_id: str,
        decision: str,
        still_required: bool,
        units_requested: Optional[int],
        additional_information: Optional[str],
        notes: Optional[str],
    ) -> Dict[str, Any]:
        now = _now_iso()
        request_id = str(req["id"])
        fields: List[str] = [
            "hospital_id = ?",
            "hospital_verification_status = ?",
            "hospital_confirmed_by = ?",
            "hospital_confirmed_at = ?",
            "updated_at = ?",
        ]
        params: List[Any] = [hospital_row["id"], decision, actor_id, now, now]
        if units_requested is not None:
            fields.append("units_requested = ?")
            params.append(units_requested)
        if additional_information is not None:
            fields.append("additional_information = ?")
            params.append(additional_information)
        if not still_required:
            fields.append("status = 'cancelled'")
            fields.append("cancellation_reason = ?")
            params.append(notes or "Hospital confirmed blood is no longer required.")
        params.append(request_id)

        note_text = notes or f"Hospital '{hospital_row['hospital_name']}' marked request as {decision}."
        with self._connect() as conn:  # type: ignore[attr-defined]
            conn.execute(f"UPDATE blood_requests SET {', '.join(fields)} WHERE id = ?", params)
            new_st = "cancelled" if not still_required else req["status"]
            conn.execute(
                """
                INSERT INTO request_status_history (id, request_id, previous_status, new_status, changed_by, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), request_id, req["status"], new_st, actor_id, note_text, now),
            )
            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=str(req["requester_id"]),
                notification_type="request_status_update",
                title="Hospital Request Confirmation Update",
                message=f"{hospital_row['hospital_name']}: {note_text}",
                related_request_id=request_id,
            )
            if not still_required:
                self._close_request_side_effects_sqlite(
                    conn,
                    request_id=request_id,
                    blood_group=req["blood_group"],
                    hospital_name=req["hospital_name"],
                    notification_type="request_cancelled",
                    title="Blood Request Closed by Hospital",
                    message=f"Verified hospital closed request for {req['blood_group']} at {req['hospital_name']}: {note_text}",
                    new_match_status="skipped",
                )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=actor_id,
                action="hospital_confirm_request",
                target_type="blood_request",
                target_id=request_id,
                metadata_json=json.dumps({"hospital_id": hospital_row["id"], "decision": decision}),
            )
        updated = self.get_blood_request(request_id)  # type: ignore[attr-defined]
        assert updated is not None
        return updated

    def hospital_close_request(
        self,
        *,
        hospital_row: Dict[str, Any],
        req: Dict[str, Any],
        actor_id: str,
        target_status: str,
        reason: str,
    ) -> Dict[str, Any]:
        now = _now_iso()
        request_id = str(req["id"])
        note_text = f"[{hospital_row['hospital_name']}] {reason}"
        with self._connect() as conn:  # type: ignore[attr-defined]
            conn.execute(
                """
                UPDATE blood_requests
                SET status = ?, hospital_id = ?, cancellation_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (target_status, hospital_row["id"], reason if target_status == "cancelled" else None, now, request_id),
            )
            conn.execute(
                """
                INSERT INTO request_status_history (id, request_id, previous_status, new_status, changed_by, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), request_id, req["status"], target_status, actor_id, note_text, now),
            )
            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=str(req["requester_id"]),
                notification_type="request_cancelled" if target_status == "cancelled" else "request_status_update",
                title=f"Request Marked {target_status.title()} by Hospital",
                message=note_text,
                related_request_id=request_id,
            )
            self._close_request_side_effects_sqlite(
                conn,
                request_id=request_id,
                blood_group=req["blood_group"],
                hospital_name=req["hospital_name"],
                notification_type="request_cancelled" if target_status == "cancelled" else "request_status_update",
                title=f"Blood Request {target_status.title()}",
                message=f"The request for {req['blood_group']} at {req['hospital_name']} was marked {target_status} by the verified hospital.",
                new_match_status="skipped",
            )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=actor_id,
                action=f"hospital_close_{target_status}",
                target_type="blood_request",
                target_id=request_id,
                metadata_json=json.dumps({"reason": reason, "hospital_id": hospital_row["id"]}),
            )
        updated = self.get_blood_request(request_id)  # type: ignore[attr-defined]
        assert updated is not None
        return updated

    # --- Blood Bank Stock Updates ---

    def record_blood_bank_stock_update(
        self,
        *,
        blood_bank_id: str,
        blood_group: str,
        availability_status: str,
        notes: Optional[str],
        actor_id: str,
    ) -> Dict[str, Any]:
        now = _now_iso()
        upd_id = str(uuid.uuid4())
        with self._connect() as conn:  # type: ignore[attr-defined]
            conn.execute(
                """
                INSERT INTO blood_bank_stock_updates (id, blood_bank_id, blood_group, availability_status, notes, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (upd_id, blood_bank_id, blood_group, availability_status, notes, actor_id, now),
            )
            conn.execute(
                "UPDATE blood_banks SET availability_status = ?, last_verified_at = ?, updated_at = ? WHERE id = ?",
                (availability_status, now, now, blood_bank_id),
            )
            self._write_audit_log(  # type: ignore[attr-defined]
                conn,
                actor_id=actor_id,
                action="blood_bank_stock_update",
                target_type="blood_bank",
                target_id=blood_bank_id,
                metadata_json=json.dumps({"blood_group": blood_group, "availability_status": availability_status}),
            )
            row = conn.execute("SELECT * FROM blood_bank_stock_updates WHERE id = ?", (upd_id,)).fetchone()
        data = dict(row)
        data["availability_label"] = PHASE1_AVAILABILITY_LABELS.get(data["availability_status"], "Availability unknown")
        return data

    def list_blood_bank_stock_updates(self, blood_bank_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(
                "SELECT * FROM blood_bank_stock_updates WHERE blood_bank_id = ? ORDER BY updated_at DESC LIMIT 20",
                (blood_bank_id,),
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["availability_label"] = PHASE1_AVAILABILITY_LABELS.get(item["availability_status"], "Availability unknown")
            out.append(item)
        return out


class Phase1SupabaseMixin:
    """Supabase PostgREST implementations for Phase 1 add-on features."""

    def get_request_tracking_summary(self, request_id: str) -> Optional[Dict[str, Any]]:
        req = self.get_blood_request(request_id)  # type: ignore[attr-defined]
        if not req:
            return None
        history = self.get_request_status_history(request_id)  # type: ignore[attr-defined]
        matches = self.list_matches_for_request(request_id)  # type: ignore[attr-defined]
        responses = self.list_responses_for_request(request_id)  # type: ignore[attr-defined]
        return build_live_tracking_summary(req, history, matches, responses)

    def _close_request_side_effects_supabase(
        self,
        *,
        request_id: str,
        notification_type: str,
        title: str,
        message: str,
        new_match_status: str,
    ) -> None:
        matches = (
            self.client.table("donor_matches")  # type: ignore[attr-defined]
            .select("donor_id, match_status, donor_profiles(user_id)")
            .eq("request_id", request_id)
            .in_("match_status", ["candidate", "notified", "accepted"])
            .execute()
        ).data or []
        seen_users: set[str] = set()
        for m in matches:
            uid = (m.get("donor_profiles") or {}).get("user_id")
            if uid and uid not in seen_users:
                seen_users.add(uid)
                self.client.table("notifications").insert(  # type: ignore[attr-defined]
                    {
                        "user_id": uid,
                        "notification_type": notification_type,
                        "title": title,
                        "message": message,
                        "related_request_id": request_id,
                        "delivery_status": "saved",
                    }
                ).execute()
        coords = (
            self.client.table("request_coordinators")  # type: ignore[attr-defined]
            .select("coordinator_user_id")
            .eq("request_id", request_id)
            .eq("status", "active")
            .execute()
        ).data or []
        for c in coords:
            self.client.table("notifications").insert(  # type: ignore[attr-defined]
                {
                    "user_id": c["coordinator_user_id"],
                    "notification_type": notification_type,
                    "title": title,
                    "message": message,
                    "related_request_id": request_id,
                    "delivery_status": "saved",
                }
            ).execute()
        self.client.table("donor_matches").update({"match_status": new_match_status}).eq(  # type: ignore[attr-defined]
            "request_id", request_id
        ).in_("match_status", ["candidate", "notified"]).execute()
        self.client.table("conversations").update({"status": "closed"}).eq(  # type: ignore[attr-defined]
            "request_id", request_id
        ).eq("status", "active").execute()
        self.client.table("donor_location_tracking").update(  # type: ignore[attr-defined]
            {"is_active": False, "tracking_status": "stopped"}
        ).eq("request_id", request_id).execute()
        self.client.table("request_share_links").update({"is_active": False}).eq(  # type: ignore[attr-defined]
            "request_id", request_id
        ).execute()

    def is_active_coordinator_for_request(self, user_id: str, request_id: str, permission: Optional[str] = None) -> bool:
        rows = (
            self.client.table("request_coordinators")  # type: ignore[attr-defined]
            .select("*")
            .eq("request_id", request_id)
            .eq("coordinator_user_id", user_id)
            .eq("status", "active")
            .limit(1)
            .execute()
        ).data or []
        if not rows:
            return False
        if permission:
            return bool(rows[0].get(permission))
        return True

    def invite_coordinator(
        self,
        *,
        request_row: Dict[str, Any],
        requester_id: str,
        coordinator_identifier: str,
        can_chat: bool,
        can_contact_blood_banks: bool,
        can_update_progress: bool,
    ) -> Optional[Dict[str, Any]]:
        ident = coordinator_identifier.strip()
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
        if target["id"] == requester_id:
            raise ValueError("Requester already owns this request and does not need coordinator assignment.")
        res = (
            self.client.table("request_coordinators")  # type: ignore[attr-defined]
            .upsert(
                {
                    "request_id": request_row["id"],
                    "requester_id": requester_id,
                    "coordinator_user_id": target["id"],
                    "status": "invited",
                    "can_chat": can_chat,
                    "can_contact_blood_banks": can_contact_blood_banks,
                    "can_update_progress": can_update_progress,
                    "invited_at": _now_iso(),
                    "responded_at": None,
                    "revoked_at": None,
                },
                on_conflict="request_id,coordinator_user_id",
            )
            .execute()
        )
        assign_id = res.data[0]["id"]
        self.client.table("notifications").insert(  # type: ignore[attr-defined]
            {
                "user_id": target["id"],
                "notification_type": "request_status_update",
                "title": "Emergency Coordinator Assignment Invite",
                "message": f"You have been authorized to coordinate {request_row['blood_group']} request at {request_row['hospital_name']}.",
                "related_request_id": request_row["id"],
                "delivery_status": "saved",
            }
        ).execute()
        return self.get_coordinator_assignment(assign_id)

    def _hydrate_coord_supabase(self, r: Dict[str, Any]) -> Dict[str, Any]:
        p = r.get("profiles") or {}
        br = r.get("blood_requests") or {}
        return {
            "id": r["id"],
            "request_id": r["request_id"],
            "requester_id": r["requester_id"],
            "coordinator_user_id": r["coordinator_user_id"],
            "coordinator_display_name": mask_display_name(p.get("full_name", "Coordinator")),
            "request_blood_group": br.get("blood_group"),
            "request_hospital_name": br.get("hospital_name"),
            "request_status": br.get("status"),
            "status": r["status"],
            "can_chat": bool(r.get("can_chat", True)),
            "can_contact_blood_banks": bool(r.get("can_contact_blood_banks", True)),
            "can_update_progress": bool(r.get("can_update_progress", True)),
            "invited_at": str(r["invited_at"]),
            "responded_at": str(r["responded_at"]) if r.get("responded_at") else None,
            "revoked_at": str(r["revoked_at"]) if r.get("revoked_at") else None,
        }

    def get_coordinator_assignment(self, assign_id: str) -> Optional[Dict[str, Any]]:
        rows = (
            self.client.table("request_coordinators")  # type: ignore[attr-defined]
            .select("*, profiles!request_coordinators_coordinator_user_id_fkey(full_name), blood_requests(blood_group, hospital_name, status)")
            .eq("id", assign_id)
            .limit(1)
            .execute()
        ).data or []
        return self._hydrate_coord_supabase(rows[0]) if rows else None

    def list_coordinators_for_request(self, request_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.client.table("request_coordinators")  # type: ignore[attr-defined]
            .select("*, profiles!request_coordinators_coordinator_user_id_fkey(full_name), blood_requests(blood_group, hospital_name, status)")
            .eq("request_id", request_id)
            .order("created_at", desc=True)
            .execute()
        ).data or []
        return [self._hydrate_coord_supabase(r) for r in rows]

    def list_my_coordinator_assignments(self, user_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.client.table("request_coordinators")  # type: ignore[attr-defined]
            .select("*, profiles!request_coordinators_coordinator_user_id_fkey(full_name), blood_requests(blood_group, hospital_name, status)")
            .eq("coordinator_user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        ).data or []
        return [self._hydrate_coord_supabase(r) for r in rows]

    def respond_to_coordinator_invite(self, *, assign_id: str, coordinator_user_id: str, accept: bool) -> Any:
        rows = (
            self.client.table("request_coordinators").select("*").eq("id", assign_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        if not rows:
            return None
        row = rows[0]
        if row["coordinator_user_id"] != coordinator_user_id:
            return "FORBIDDEN"
        if row["status"] == "revoked":
            return "REVOKED"
        new_status = "active" if accept else "declined"
        self.client.table("request_coordinators").update(  # type: ignore[attr-defined]
            {"status": new_status, "responded_at": _now_iso()}
        ).eq("id", assign_id).execute()
        return self.get_coordinator_assignment(assign_id)

    def revoke_coordinator(self, *, assign_id: str, actor_id: str, is_admin: bool) -> Any:
        rows = (
            self.client.table("request_coordinators").select("*").eq("id", assign_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        if not rows:
            return None
        row = rows[0]
        if not is_admin and row["requester_id"] != actor_id:
            return "FORBIDDEN"
        self.client.table("request_coordinators").update(  # type: ignore[attr-defined]
            {"status": "revoked", "revoked_at": _now_iso()}
        ).eq("id", assign_id).execute()
        return self.get_coordinator_assignment(assign_id)

    def add_coordinator_progress_update(self, *, request_row: Dict[str, Any], actor_id: str, notes: str) -> Dict[str, Any]:
        request_id = str(request_row["id"])
        self.client.table("request_status_history").insert(  # type: ignore[attr-defined]
            {
                "request_id": request_id,
                "previous_status": request_row["status"],
                "new_status": request_row["status"],
                "changed_by": actor_id,
                "notes": f"[Coordinator Update] {notes}",
            }
        ).execute()
        self.client.table("notifications").insert(  # type: ignore[attr-defined]
            {
                "user_id": request_row["requester_id"],
                "notification_type": "request_status_update",
                "title": "Emergency Coordinator Update",
                "message": f"Coordinator update for {request_row['hospital_name']}: {notes}",
                "related_request_id": request_id,
                "delivery_status": "saved",
            }
        ).execute()
        updated = self.get_blood_request(request_id)  # type: ignore[attr-defined]
        assert updated is not None
        return updated

    def upsert_hospital_profile(self, *, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.get_hospital_by_user_id(user_id)
        data = {**payload, "user_id": user_id}
        if existing and existing["verification_status"] in ("rejected", "suspended"):
            data["verification_status"] = "pending_verification"
        res = self.client.table("hospitals").upsert(data, on_conflict="user_id").execute()  # type: ignore[attr-defined]
        return res.data[0]

    def get_hospital_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        rows = (
            self.client.table("hospitals").select("*").eq("user_id", user_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        return rows[0] if rows else None

    def get_hospital_by_id(self, hospital_id: str) -> Optional[Dict[str, Any]]:
        rows = (
            self.client.table("hospitals").select("*").eq("id", hospital_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        return rows[0] if rows else None

    def list_verified_hospitals(self, city: Optional[str] = None) -> List[Dict[str, Any]]:
        q = self.client.table("hospitals").select("*").eq("verification_status", "verified")  # type: ignore[attr-defined]
        if city:
            q = q.ilike("city", city.strip())
        return q.order("hospital_name").execute().data or []

    def store_hospital_document_bytes(
        self, *, hospital_id: str, safe_filename: str, content_bytes: bytes, settings: Settings
    ) -> str:
        target_dir = Path(settings.upload_dir) / "hospitals" / hospital_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = (target_dir / safe_filename).resolve()
        target_file.write_bytes(content_bytes)
        return str(Path("hospitals") / hospital_id / safe_filename).replace("\\", "/")

    def submit_hospital_document(self, *, hospital_id: str, document_type: str, storage_path: str) -> Dict[str, Any]:
        return (
            self.client.table("hospital_verification_documents")  # type: ignore[attr-defined]
            .insert({"hospital_id": hospital_id, "document_type": document_type, "storage_path": storage_path})
            .execute()
        ).data[0]

    def list_hospital_documents(self, hospital_id: str) -> List[Dict[str, Any]]:
        return (
            self.client.table("hospital_verification_documents")  # type: ignore[attr-defined]
            .select("*")
            .eq("hospital_id", hospital_id)
            .order("created_at", desc=True)
            .execute()
        ).data or []

    def get_hospital_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        rows = (
            self.client.table("hospital_verification_documents").select("*").eq("id", doc_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        return rows[0] if rows else None

    def get_hospital_verification_history(self, hospital_id: str) -> List[Dict[str, Any]]:
        return (
            self.client.table("hospital_verification_history")  # type: ignore[attr-defined]
            .select("*")
            .eq("hospital_id", hospital_id)
            .order("created_at")
            .execute()
        ).data or []

    def admin_list_hospitals(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        q = self.client.table("hospitals").select("*")  # type: ignore[attr-defined]
        if status_filter:
            q = q.eq("verification_status", status_filter)
        rows = q.order("created_at", desc=True).execute().data or []
        for r in rows:
            r["documents"] = self.list_hospital_documents(r["id"])
        return rows

    def admin_review_hospital(
        self, *, hospital_id: str, verification_status: str, admin_id: str, notes: str
    ) -> Optional[Dict[str, Any]]:
        existing = self.get_hospital_by_id(hospital_id)
        if not existing:
            return None
        upd: Dict[str, Any] = {"verification_status": verification_status, "admin_notes": notes}
        if verification_status == "verified":
            upd["verified_by"] = admin_id
            upd["verified_at"] = _now_iso()
        self.client.table("hospitals").update(upd).eq("id", hospital_id).execute()  # type: ignore[attr-defined]
        self.client.table("hospital_verification_history").insert(  # type: ignore[attr-defined]
            {
                "hospital_id": hospital_id,
                "previous_status": existing["verification_status"],
                "new_status": verification_status,
                "actor_id": admin_id,
                "notes": notes,
            }
        ).execute()
        return self.get_hospital_by_id(hospital_id)

    def hospital_list_requests(self, hospital_row: Dict[str, Any]) -> List[Dict[str, Any]]:
        return (
            self.client.table("blood_requests")  # type: ignore[attr-defined]
            .select("*")
            .or_(f"hospital_id.eq.{hospital_row['id']},city.ilike.{hospital_row['city']}")
            .order("created_at", desc=True)
            .execute()
        ).data or []

    def hospital_can_manage_request(self, hospital_row: Dict[str, Any], req: Dict[str, Any]) -> bool:
        if req.get("hospital_id") and str(req["hospital_id"]) == str(hospital_row["id"]):
            return True
        if req.get("city", "").strip().lower() != hospital_row.get("city", "").strip().lower():
            return False
        h_name = hospital_row["hospital_name"].strip().lower()
        r_name = req.get("hospital_name", "").strip().lower()
        return h_name in r_name or r_name in h_name

    def hospital_confirm_or_update_request(
        self,
        *,
        hospital_row: Dict[str, Any],
        req: Dict[str, Any],
        actor_id: str,
        decision: str,
        still_required: bool,
        units_requested: Optional[int],
        additional_information: Optional[str],
        notes: Optional[str],
    ) -> Dict[str, Any]:
        upd: Dict[str, Any] = {
            "hospital_id": hospital_row["id"],
            "hospital_verification_status": decision,
            "hospital_confirmed_by": actor_id,
            "hospital_confirmed_at": _now_iso(),
        }
        if units_requested is not None:
            upd["units_requested"] = units_requested
        if additional_information is not None:
            upd["additional_information"] = additional_information
        if not still_required:
            upd["status"] = "cancelled"
            upd["cancellation_reason"] = notes or "Hospital confirmed blood is no longer required."
        self.client.table("blood_requests").update(upd).eq("id", req["id"]).execute()  # type: ignore[attr-defined]
        if not still_required:
            self._close_request_side_effects_supabase(
                request_id=str(req["id"]),
                notification_type="request_cancelled",
                title="Blood Request Closed by Hospital",
                message=notes or "Hospital closed request.",
                new_match_status="skipped",
            )
        updated = self.get_blood_request(str(req["id"]))  # type: ignore[attr-defined]
        assert updated is not None
        return updated

    def hospital_close_request(
        self,
        *,
        hospital_row: Dict[str, Any],
        req: Dict[str, Any],
        actor_id: str,
        target_status: str,
        reason: str,
    ) -> Dict[str, Any]:
        self.client.table("blood_requests").update(  # type: ignore[attr-defined]
            {"status": target_status, "hospital_id": hospital_row["id"], "cancellation_reason": reason}
        ).eq("id", req["id"]).execute()
        self._close_request_side_effects_supabase(
            request_id=str(req["id"]),
            notification_type="request_cancelled" if target_status == "cancelled" else "request_status_update",
            title=f"Blood Request {target_status.title()}",
            message=f"{hospital_row['hospital_name']}: {reason}",
            new_match_status="skipped",
        )
        updated = self.get_blood_request(str(req["id"]))  # type: ignore[attr-defined]
        assert updated is not None
        return updated

    def record_blood_bank_stock_update(
        self,
        *,
        blood_bank_id: str,
        blood_group: str,
        availability_status: str,
        notes: Optional[str],
        actor_id: str,
    ) -> Dict[str, Any]:
        row = (
            self.client.table("blood_bank_stock_updates")  # type: ignore[attr-defined]
            .insert(
                {
                    "blood_bank_id": blood_bank_id,
                    "blood_group": blood_group,
                    "availability_status": availability_status,
                    "notes": notes,
                    "updated_by": actor_id,
                }
            )
            .execute()
        ).data[0]
        self.client.table("blood_banks").update(  # type: ignore[attr-defined]
            {"availability_status": availability_status, "last_verified_at": _now_iso()}
        ).eq("id", blood_bank_id).execute()
        row["availability_label"] = PHASE1_AVAILABILITY_LABELS.get(row["availability_status"], "Availability unknown")
        return row

    def list_blood_bank_stock_updates(self, blood_bank_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.client.table("blood_bank_stock_updates")  # type: ignore[attr-defined]
            .select("*")
            .eq("blood_bank_id", blood_bank_id)
            .order("updated_at", desc=True)
            .limit(20)
            .execute()
        ).data or []
        for r in rows:
            r["availability_label"] = PHASE1_AVAILABILITY_LABELS.get(r["availability_status"], "Availability unknown")
        return rows
