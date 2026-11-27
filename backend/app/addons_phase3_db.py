"""Phase 3 Add-On Repository Mixins (SQLite + Supabase): Trust Profile, Donation History, Referrals & Appreciation."""

import json
import secrets
import sqlite3
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.utils.security import mask_display_name

# Configurable coordination guidance windows by donation component type (NOT universal or final clinical eligibility)
DONATION_TYPE_ADVISORY_DAYS = {
    "whole_blood": 90,
    "platelets": 14,
    "plasma": 28,
    "double_red_cells": 112,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_profile_completion(prof: Dict[str, Any], donor: Dict[str, Any]) -> int:
    checks = [
        bool(prof.get("full_name")),
        bool(prof.get("city")),
        bool(prof.get("approximate_location")),
        bool(prof.get("phone_verified")),
        bool(prof.get("aadhaar_verified")),
        bool(donor.get("blood_group")),
        donor.get("verification_status") in ("pending_review", "verified"),
    ]
    return round((sum(1 for c in checks if c) / len(checks)) * 100)


class Phase3SQLiteMixin:
    """SQLite implementations for Phase 3 trust, donation history, referral, and appreciation features."""

    def _init_phase3_schema(self, conn: sqlite3.Connection) -> None:
        p_cols = {r["name"] for r in conn.execute("PRAGMA table_info(profiles)").fetchall()}
        if "referral_code" not in p_cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN referral_code TEXT")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_ref_code ON profiles(referral_code)")
        if "referred_by_user_id" not in p_cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN referred_by_user_id TEXT REFERENCES profiles(id)")

        dp_cols = {r["name"] for r in conn.execute("PRAGMA table_info(donor_profiles)").fetchall()}
        if "recognition_public" not in dp_cols:
            conn.execute("ALTER TABLE donor_profiles ADD COLUMN recognition_public INTEGER NOT NULL DEFAULT 0")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS donation_records (
                id TEXT PRIMARY KEY,
                donor_id TEXT NOT NULL REFERENCES donor_profiles(id) ON DELETE CASCADE,
                donation_date TEXT NOT NULL,
                donation_type TEXT NOT NULL DEFAULT 'whole_blood',
                facility_name TEXT NOT NULL DEFAULT 'Licensed Blood Centre',
                evidence_status TEXT NOT NULL DEFAULT 'self_reported'
                    CHECK (evidence_status IN ('self_reported', 'verified_by_facility')),
                supporting_document_id TEXT REFERENCES donor_documents(id) ON DELETE SET NULL,
                notes TEXT,
                is_corrected INTEGER NOT NULL DEFAULT 0,
                correction_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS referral_records (
                id TEXT PRIMARY KEY,
                referrer_user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                referred_user_id TEXT NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
                referral_code TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'registered',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_don_rec_donor ON donation_records(donor_id, donation_date);
            CREATE INDEX IF NOT EXISTS idx_ref_rec_referrer ON referral_records(referrer_user_id);
            """
        )

    # --- Donor Trust Profile ---

    def get_donor_profile_by_id(self, donor_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute("SELECT * FROM donor_profiles WHERE id = ? LIMIT 1", (donor_id,)).fetchone()
        return dict(row) if row else None

    def can_view_donor_trust_profile(self, *, viewer_user_id: str, donor_row: Dict[str, Any]) -> bool:
        if str(donor_row["user_id"]) == viewer_user_id:
            return True
        with self._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT 1
                FROM donor_matches dm
                JOIN blood_requests br ON br.id = dm.request_id
                LEFT JOIN request_coordinators rc
                    ON rc.request_id = br.id AND rc.coordinator_user_id = ? AND rc.status = 'active'
                WHERE dm.donor_id = ?
                  AND (br.requester_id = ? OR rc.id IS NOT NULL)
                LIMIT 1
                """,
                (viewer_user_id, donor_row["id"], viewer_user_id),
            ).fetchone()
        return row is not None

    def get_donor_trust_profile(self, *, donor_row: Dict[str, Any]) -> Dict[str, Any]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            prof = conn.execute("SELECT * FROM profiles WHERE id = ? LIMIT 1", (donor_row["user_id"],)).fetchone()
            face = conn.execute(
                "SELECT 1 FROM donor_face_profiles WHERE donor_id = ? LIMIT 1", (donor_row["id"],)
            ).fetchone()
            rec_rows = conn.execute(
                "SELECT evidence_status FROM donation_records WHERE donor_id = ?", (donor_row["id"],)
            ).fetchall()
            resp_rows = conn.execute(
                "SELECT response FROM donor_responses WHERE donor_id = ?", (donor_row["id"],)
            ).fetchall()

        verified_donations = sum(1 for r in rec_rows if r["evidence_status"] == "verified_by_facility")
        self_donations = sum(1 for r in rec_rows if r["evidence_status"] == "self_reported")
        accepted_cnt = sum(1 for r in resp_rows if r["response"] == "accepted")
        declined_cnt = sum(1 for r in resp_rows if r["response"] == "declined")
        prof_dict = dict(prof) if prof else {}

        return {
            "donor_id": donor_row["id"],
            "display_name": mask_display_name(prof_dict.get("full_name", "Donor")),
            "blood_group": donor_row["blood_group"],
            "verified_indicators": {
                "phone_verified": bool(prof_dict.get("phone_verified", 0)),
                "aadhaar_verified": bool(prof_dict.get("aadhaar_verified", 0)),
                "document_verification_status": donor_row["verification_status"],
                "face_identity_enrolled": face is not None,
                "evidence_backed_donations_count": verified_donations,
            },
            "self_declared_indicators": {
                "availability_status": donor_row["availability_status"],
                "last_availability_updated_at": donor_row.get("last_availability_updated_at") or donor_row["updated_at"],
                "self_reported_donations_count": self_donations,
                "profile_completion_percent": _compute_profile_completion(prof_dict, donor_row),
            },
            "response_summary": {
                "total_responses": len(resp_rows),
                "accepted_count": accepted_cnt,
                "declined_count": declined_cnt,
                "declining_policy": "Declining a request carries zero penalty.",
            },
            "trust_disclaimer": (
                "Indicators distinguish independently verified platform checks from self-declared fields. "
                "LifeLink never ranks donors clinically or grants medical approval; licensed blood banks determine eligibility."
            ),
        }

    # --- Donation History & Reminders ---

    def list_donation_records(self, donor_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(
                "SELECT * FROM donation_records WHERE donor_id = ? ORDER BY donation_date DESC, created_at DESC",
                (donor_id,),
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["is_corrected"] = bool(item["is_corrected"])
            item["guidance_window_days"] = DONATION_TYPE_ADVISORY_DAYS.get(item["donation_type"], 90)
            out.append(item)
        return out

    def create_donation_record(self, *, donor_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        rec_id = str(uuid.uuid4())
        d_date = payload["donation_date"].isoformat() if isinstance(payload["donation_date"], date) else str(payload["donation_date"])
        d_type = payload.get("donation_type", "whole_blood")
        with self._connect() as conn:  # type: ignore[attr-defined]
            conn.execute(
                """
                INSERT INTO donation_records (
                    id, donor_id, donation_date, donation_type, facility_name,
                    evidence_status, supporting_document_id, notes, is_corrected,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'self_reported', ?, ?, 0, ?, ?)
                """,
                (
                    rec_id,
                    donor_id,
                    d_date,
                    d_type,
                    payload.get("facility_name", "Licensed Blood Centre").strip(),
                    payload.get("supporting_document_id"),
                    payload.get("notes"),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM donation_records WHERE id = ?", (rec_id,)).fetchone()
        data = dict(row)
        data["is_corrected"] = False
        data["guidance_window_days"] = DONATION_TYPE_ADVISORY_DAYS.get(d_type, 90)
        return data

    def correct_donation_record(self, *, donor_id: str, record_id: str, payload: Dict[str, Any]) -> Any:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            existing = conn.execute("SELECT * FROM donation_records WHERE id = ? LIMIT 1", (record_id,)).fetchone()
            if not existing:
                return None
            if existing["donor_id"] != donor_id:
                return "FORBIDDEN"
            d_date = (
                payload["donation_date"].isoformat()
                if payload.get("donation_date") is not None
                else existing["donation_date"]
            )
            d_type = payload.get("donation_type") or existing["donation_type"]
            facility = payload.get("facility_name") or existing["facility_name"]
            notes = payload["notes"] if "notes" in payload and payload["notes"] is not None else existing["notes"]
            conn.execute(
                """
                UPDATE donation_records
                SET donation_date = ?, donation_type = ?, facility_name = ?, notes = ?,
                    is_corrected = 1, correction_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (d_date, d_type, facility.strip(), notes, payload["correction_reason"].strip(), now, record_id),
            )
            row = conn.execute("SELECT * FROM donation_records WHERE id = ?", (record_id,)).fetchone()
        data = dict(row)
        data["is_corrected"] = bool(data["is_corrected"])
        data["guidance_window_days"] = DONATION_TYPE_ADVISORY_DAYS.get(data["donation_type"], 90)
        return data

    def send_availability_reminder(self, *, user_id: str, donor_row: Dict[str, Any]) -> Dict[str, Any]:
        last_up = donor_row.get("last_availability_updated_at") or donor_row["updated_at"]
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            self._create_notification(  # type: ignore[attr-defined]
                conn,
                user_id=user_id,
                notification_type="request_status_update",
                title="Reminder: Review Your Donor Availability",
                message=(
                    f"Please check if your availability ('{donor_row['availability_status']}') and calendar "
                    "are still up to date. Only licensed blood banks determine final donation eligibility."
                ),
                related_request_id=None,
            )
        return {"reminded": True, "last_availability_updated_at": last_up, "sent_at": now}

    # --- Referrals & Voluntary Appreciation ---

    def get_or_create_referral_summary(self, user_id: str) -> Dict[str, Any]:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            prof = conn.execute("SELECT referral_code FROM profiles WHERE id = ? LIMIT 1", (user_id,)).fetchone()
            code = prof["referral_code"] if prof and prof["referral_code"] else None
            if not code:
                code = "LL-" + secrets.token_hex(4).upper()
                conn.execute("UPDATE profiles SET referral_code = ?, updated_at = ? WHERE id = ?", (code, now, user_id))
            refs = conn.execute(
                """
                SELECT rr.id, rr.referral_code, rr.status, rr.created_at, p.full_name AS referred_name
                FROM referral_records rr
                JOIN profiles p ON p.id = rr.referred_user_id
                WHERE rr.referrer_user_id = ?
                ORDER BY rr.created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return {
            "referral_code": code,
            "successful_referrals_count": len(refs),
            "referrals": [
                {
                    "id": r["id"],
                    "referred_display_name": mask_display_name(r["referred_name"]),
                    "status": r["status"],
                    "created_at": r["created_at"],
                }
                for r in refs
            ],
            "anti_abuse_notice": "Self-referrals and duplicate Aadhaar referrals are blocked automatically.",
        }

    def apply_referral_on_registration(self, *, referral_code: str, new_user_id: str, new_aadhaar_hash: str) -> bool:
        code = referral_code.strip().upper()
        if not code:
            return False
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            referrer = conn.execute(
                "SELECT id, aadhaar_hash, account_status FROM profiles WHERE upper(referral_code) = ? LIMIT 1",
                (code,),
            ).fetchone()
            if not referrer or referrer["account_status"] != "active":
                return False
            if referrer["id"] == new_user_id or referrer["aadhaar_hash"] == new_aadhaar_hash:
                return False
            # Cap referrals per referrer to prevent spam abuse
            cnt = conn.execute(
                "SELECT COUNT(*) FROM referral_records WHERE referrer_user_id = ?", (referrer["id"],)
            ).fetchone()[0]
            if cnt >= 100:
                return False
            conn.execute(
                "UPDATE profiles SET referred_by_user_id = ? WHERE id = ?",
                (referrer["id"], new_user_id),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO referral_records (id, referrer_user_id, referred_user_id, referral_code, status, created_at)
                VALUES (?, ?, ?, ?, 'registered', ?)
                """,
                (str(uuid.uuid4()), referrer["id"], new_user_id, code, now),
            )
        return True

    def get_donor_appreciation_summary(self, *, user_id: str, donor_row: Dict[str, Any]) -> Dict[str, Any]:
        ref_summary = self.get_or_create_referral_summary(user_id)
        recs = self.list_donation_records(donor_row["id"])
        verified_count = sum(1 for r in recs if r["evidence_status"] == "verified_by_facility")
        total_recorded = len(recs)
        prof = self.get_profile_by_id(user_id) or {}  # type: ignore[attr-defined]

        milestones: List[str] = ["Registered Voluntary Donor Profile"]
        if prof.get("aadhaar_verified") or prof.get("phone_verified"):
            milestones.append("Verified Community Account")
        if total_recorded >= 1:
            milestones.append("Voluntary Contribution Recorded")
        if verified_count >= 1:
            milestones.append("Facility-Confirmed Contribution")
        if ref_summary["successful_referrals_count"] >= 1:
            milestones.append("Community Awareness Advocate")

        return {
            "display_name": prof.get("full_name", "LifeLink Donor") if donor_row.get("recognition_public") else mask_display_name(prof.get("full_name", "Donor")),
            "recognition_public": bool(donor_row.get("recognition_public", False)),
            "recorded_donations_count": total_recorded,
            "verified_donations_count": verified_count,
            "referrals_count": ref_summary["successful_referrals_count"],
            "milestones": milestones,
            "appreciation_message": "Thank you for volunteering to support emergency blood coordination.",
            "digital_card": {
                "title": "LifeLink Voluntary Appreciation Card",
                "holder_name": mask_display_name(prof.get("full_name", "Donor")),
                "blood_group": donor_row["blood_group"],
                "milestone_count": len(milestones),
                "issued_at": _now_iso(),
                "disclaimer": "Voluntary community recognition only — NOT an official government or medical certificate.",
            },
        }

    def update_recognition_preference(self, *, user_id: str, recognition_public: bool) -> Dict[str, Any]:
        now = _now_iso()
        with self._connect() as conn:  # type: ignore[attr-defined]
            conn.execute(
                "UPDATE donor_profiles SET recognition_public = ?, updated_at = ? WHERE user_id = ?",
                (int(recognition_public), now, user_id),
            )
        donor = self.get_donor_profile_by_user_id(user_id)  # type: ignore[attr-defined]
        assert donor is not None
        return self.get_donor_appreciation_summary(user_id=user_id, donor_row=donor)


class Phase3SupabaseMixin:
    """Supabase implementations for Phase 3 features."""

    def get_donor_profile_by_id(self, donor_id: str) -> Optional[Dict[str, Any]]:
        rows = (
            self.client.table("donor_profiles").select("*").eq("id", donor_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        return rows[0] if rows else None

    def can_view_donor_trust_profile(self, *, viewer_user_id: str, donor_row: Dict[str, Any]) -> bool:
        if str(donor_row["user_id"]) == viewer_user_id:
            return True
        matches = (
            self.client.table("donor_matches")  # type: ignore[attr-defined]
            .select("request_id, blood_requests(requester_id)")
            .eq("donor_id", donor_row["id"])
            .execute()
        ).data or []
        for m in matches:
            br = m.get("blood_requests") or {}
            if br.get("requester_id") == viewer_user_id:
                return True
            if self.is_active_coordinator_for_request(viewer_user_id, m["request_id"]):  # type: ignore[attr-defined]
                return True
        return False

    def get_donor_trust_profile(self, *, donor_row: Dict[str, Any]) -> Dict[str, Any]:
        prof = self.get_profile_by_id(donor_row["user_id"]) or {}  # type: ignore[attr-defined]
        face = (
            self.client.table("donor_face_profiles").select("id").eq("donor_id", donor_row["id"]).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        recs = (
            self.client.table("donation_records").select("evidence_status").eq("donor_id", donor_row["id"]).execute()  # type: ignore[attr-defined]
        ).data or []
        resps = (
            self.client.table("donor_responses").select("response").eq("donor_id", donor_row["id"]).execute()  # type: ignore[attr-defined]
        ).data or []
        verified_donations = sum(1 for r in recs if r["evidence_status"] == "verified_by_facility")
        self_donations = sum(1 for r in recs if r["evidence_status"] == "self_reported")
        accepted_cnt = sum(1 for r in resps if r["response"] == "accepted")
        declined_cnt = sum(1 for r in resps if r["response"] == "declined")
        return {
            "donor_id": donor_row["id"],
            "display_name": mask_display_name(prof.get("full_name", "Donor")),
            "blood_group": donor_row["blood_group"],
            "verified_indicators": {
                "phone_verified": bool(prof.get("phone_verified", False)),
                "aadhaar_verified": bool(prof.get("aadhaar_verified", False)),
                "document_verification_status": donor_row["verification_status"],
                "face_identity_enrolled": bool(face),
                "evidence_backed_donations_count": verified_donations,
            },
            "self_declared_indicators": {
                "availability_status": donor_row["availability_status"],
                "last_availability_updated_at": donor_row.get("last_availability_updated_at") or str(donor_row["updated_at"]),
                "self_reported_donations_count": self_donations,
                "profile_completion_percent": _compute_profile_completion(prof, donor_row),
            },
            "response_summary": {
                "total_responses": len(resps),
                "accepted_count": accepted_cnt,
                "declined_count": declined_cnt,
                "declining_policy": "Declining a request carries zero penalty.",
            },
            "trust_disclaimer": (
                "Indicators distinguish independently verified platform checks from self-declared fields. "
                "LifeLink never ranks donors clinically or grants medical approval."
            ),
        }

    def list_donation_records(self, donor_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.client.table("donation_records")  # type: ignore[attr-defined]
            .select("*")
            .eq("donor_id", donor_id)
            .order("donation_date", desc=True)
            .execute()
        ).data or []
        for r in rows:
            r["is_corrected"] = bool(r.get("is_corrected", False))
            r["guidance_window_days"] = DONATION_TYPE_ADVISORY_DAYS.get(r["donation_type"], 90)
        return rows

    def create_donation_record(self, *, donor_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        d_date = payload["donation_date"].isoformat() if isinstance(payload["donation_date"], date) else str(payload["donation_date"])
        row = (
            self.client.table("donation_records")  # type: ignore[attr-defined]
            .insert(
                {
                    "donor_id": donor_id,
                    "donation_date": d_date,
                    "donation_type": payload.get("donation_type", "whole_blood"),
                    "facility_name": payload.get("facility_name", "Licensed Blood Centre").strip(),
                    "evidence_status": "self_reported",
                    "supporting_document_id": payload.get("supporting_document_id"),
                    "notes": payload.get("notes"),
                }
            )
            .execute()
        ).data[0]
        row["is_corrected"] = False
        row["guidance_window_days"] = DONATION_TYPE_ADVISORY_DAYS.get(row["donation_type"], 90)
        return row

    def correct_donation_record(self, *, donor_id: str, record_id: str, payload: Dict[str, Any]) -> Any:
        rows = (
            self.client.table("donation_records").select("*").eq("id", record_id).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        if not rows:
            return None
        existing = rows[0]
        if existing["donor_id"] != donor_id:
            return "FORBIDDEN"
        upd: Dict[str, Any] = {"is_corrected": True, "correction_reason": payload["correction_reason"].strip()}
        if payload.get("donation_date") is not None:
            upd["donation_date"] = payload["donation_date"].isoformat()
        if payload.get("donation_type") is not None:
            upd["donation_type"] = payload["donation_type"]
        if payload.get("facility_name") is not None:
            upd["facility_name"] = payload["facility_name"].strip()
        if "notes" in payload and payload["notes"] is not None:
            upd["notes"] = payload["notes"]
        row = (
            self.client.table("donation_records").update(upd).eq("id", record_id).execute()  # type: ignore[attr-defined]
        ).data[0]
        row["is_corrected"] = True
        row["guidance_window_days"] = DONATION_TYPE_ADVISORY_DAYS.get(row["donation_type"], 90)
        return row

    def send_availability_reminder(self, *, user_id: str, donor_row: Dict[str, Any]) -> Dict[str, Any]:
        last_up = donor_row.get("last_availability_updated_at") or str(donor_row["updated_at"])
        self.client.table("notifications").insert(  # type: ignore[attr-defined]
            {
                "user_id": user_id,
                "notification_type": "request_status_update",
                "title": "Reminder: Review Your Donor Availability",
                "message": "Please verify your donor availability calendar. Only licensed blood banks determine final donation eligibility.",
                "delivery_status": "saved",
            }
        ).execute()
        return {"reminded": True, "last_availability_updated_at": last_up, "sent_at": _now_iso()}

    def get_or_create_referral_summary(self, user_id: str) -> Dict[str, Any]:
        prof = self.get_profile_by_id(user_id) or {}  # type: ignore[attr-defined]
        code = prof.get("referral_code")
        if not code:
            code = "LL-" + secrets.token_hex(4).upper()
            self.client.table("profiles").update({"referral_code": code}).eq("id", user_id).execute()  # type: ignore[attr-defined]
        refs = (
            self.client.table("referral_records")  # type: ignore[attr-defined]
            .select("*, profiles!referral_records_referred_user_id_fkey(full_name)")
            .eq("referrer_user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        ).data or []
        return {
            "referral_code": code,
            "successful_referrals_count": len(refs),
            "referrals": [
                {
                    "id": r["id"],
                    "referred_display_name": mask_display_name((r.get("profiles") or {}).get("full_name", "Member")),
                    "status": r["status"],
                    "created_at": str(r["created_at"]),
                }
                for r in refs
            ],
            "anti_abuse_notice": "Self-referrals and duplicate Aadhaar referrals are blocked automatically.",
        }

    def apply_referral_on_registration(self, *, referral_code: str, new_user_id: str, new_aadhaar_hash: str) -> bool:
        code = referral_code.strip().upper()
        if not code:
            return False
        rows = (
            self.client.table("profiles").select("id, aadhaar_hash, account_status").eq("referral_code", code).limit(1).execute()  # type: ignore[attr-defined]
        ).data or []
        if not rows or rows[0]["account_status"] != "active":
            return False
        ref = rows[0]
        if ref["id"] == new_user_id or ref["aadhaar_hash"] == new_aadhaar_hash:
            return False
        self.client.table("profiles").update({"referred_by_user_id": ref["id"]}).eq("id", new_user_id).execute()  # type: ignore[attr-defined]
        self.client.table("referral_records").insert(  # type: ignore[attr-defined]
            {"referrer_user_id": ref["id"], "referred_user_id": new_user_id, "referral_code": code, "status": "registered"}
        ).execute()
        return True

    def get_donor_appreciation_summary(self, *, user_id: str, donor_row: Dict[str, Any]) -> Dict[str, Any]:
        ref_summary = self.get_or_create_referral_summary(user_id)
        recs = self.list_donation_records(donor_row["id"])
        verified_count = sum(1 for r in recs if r["evidence_status"] == "verified_by_facility")
        total_recorded = len(recs)
        prof = self.get_profile_by_id(user_id) or {}  # type: ignore[attr-defined]
        milestones = ["Registered Voluntary Donor Profile"]
        if total_recorded >= 1:
            milestones.append("Voluntary Contribution Recorded")
        if verified_count >= 1:
            milestones.append("Facility-Confirmed Contribution")
        if ref_summary["successful_referrals_count"] >= 1:
            milestones.append("Community Awareness Advocate")
        return {
            "display_name": prof.get("full_name", "LifeLink Donor") if donor_row.get("recognition_public") else mask_display_name(prof.get("full_name", "Donor")),
            "recognition_public": bool(donor_row.get("recognition_public", False)),
            "recorded_donations_count": total_recorded,
            "verified_donations_count": verified_count,
            "referrals_count": ref_summary["successful_referrals_count"],
            "milestones": milestones,
            "appreciation_message": "Thank you for volunteering to support emergency blood coordination.",
            "digital_card": {
                "title": "LifeLink Voluntary Appreciation Card",
                "holder_name": mask_display_name(prof.get("full_name", "Donor")),
                "blood_group": donor_row["blood_group"],
                "milestone_count": len(milestones),
                "issued_at": _now_iso(),
                "disclaimer": "Voluntary community recognition only — NOT an official government or medical certificate.",
            },
        }

    def update_recognition_preference(self, *, user_id: str, recognition_public: bool) -> Dict[str, Any]:
        self.client.table("donor_profiles").update({"recognition_public": recognition_public}).eq("user_id", user_id).execute()  # type: ignore[attr-defined]
        donor = self.get_donor_profile_by_user_id(user_id)  # type: ignore[attr-defined]
        assert donor is not None
        return self.get_donor_appreciation_summary(user_id=user_id, donor_row=donor)
