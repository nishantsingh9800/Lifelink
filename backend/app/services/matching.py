from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# Preliminary ABO/Rh red-cell compatibility mapping (for candidate ranking only;
# final crossmatching and clinical compatibility are handled exclusively by blood banks).
PRELIMINARY_COMPATIBLE_DONOR_GROUPS: Dict[str, Set[str]] = {
    "O-": {"O-"},
    "O+": {"O-", "O+"},
    "A-": {"O-", "A-"},
    "A+": {"O-", "O+", "A-", "A+"},
    "B-": {"O-", "B-"},
    "B+": {"O-", "O+", "B-", "B+"},
    "AB-": {"O-", "A-", "B-", "AB-"},
    "AB+": {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"},
}


def _is_within_quiet_hours(now_hhmm: str, start_hhmm: str, end_hhmm: str) -> bool:
    """Return True if now_hhmm (HH:MM) falls inside [start, end), handling midnight wraparound."""
    if start_hhmm == end_hhmm:
        return False
    if start_hhmm < end_hhmm:
        return start_hhmm <= now_hhmm < end_hhmm
    return now_hhmm >= start_hhmm or now_hhmm < end_hhmm


def score_candidate(
    *,
    request_row: Dict[str, Any],
    donor_row: Dict[str, Any],
    allow_wider_city: bool,
    review_interval_days: int,
    evaluation_dt: Optional[datetime] = None,
) -> Tuple[bool, float, str]:
    """
    Evaluate a candidate donor using transparent, configurable rules.
    Availability is self-declared and never treated as clinical eligibility.
    """
    if donor_row.get("account_status") != "active":
        return False, 0.0, "Account inactive"
    if str(donor_row.get("user_id")) == str(request_row.get("requester_id")):
        return False, 0.0, "Cannot match requester to their own request"
    if not donor_row.get("emergency_notifications_enabled", True):
        return False, 0.0, "Donor opted out of notifications"

    now_dt = evaluation_dt or datetime.now()
    today_date = now_dt.date()
    today_iso = today_date.isoformat()
    now_hhmm = now_dt.strftime("%H:%M")

    avail = donor_row.get("availability_status", "unavailable")
    if avail == "unavailable":
        return False, 0.0, "Donor marked unavailable"

    # Temporary pause takes precedence over general availability
    paused_until = donor_row.get("paused_until")
    if paused_until:
        try:
            if datetime.fromisoformat(str(paused_until)[:10]).date() >= today_date:
                return False, 0.0, f"Donor temporarily paused until {str(paused_until)[:10]}"
        except ValueError:
            pass

    # 90-day post-donation recovery freeze
    frozen_until = donor_row.get("donor_frozen_until")
    if frozen_until:
        try:
            if datetime.fromisoformat(str(frozen_until)[:10]).date() > today_date:
                return False, 0.0, f"Donor in 3-month post-donation freeze until {str(frozen_until)[:10]}"
        except ValueError:
            pass

    # Selected-dates availability strictly checks scheduled dates
    if avail == "available_selected_dates":
        selected_dates = donor_row.get("available_dates") or []
        if today_iso not in selected_dates:
            return False, 0.0, "Today is not in donor's selected available dates"

    if avail == "emergency_only" and request_row.get("urgency") != "emergency" and not allow_wider_city:
        return False, 0.0, "Donor accepts emergency requests only"

    # Respect donor quiet hours unless urgent/emergency override is enabled
    q_start = donor_row.get("quiet_hours_start")
    q_end = donor_row.get("quiet_hours_end")
    q_enabled = donor_row.get("quiet_hours_enabled", True)
    emerg_override = donor_row.get("emergency_override_quiet_hours", True)
    if q_enabled and q_start and q_end and _is_within_quiet_hours(now_hhmm, q_start, q_end):
        if request_row.get("urgency") != "emergency" or not emerg_override:
            return False, 0.0, f"Donor is currently in configured quiet hours ({q_start}-{q_end})"

    req_group = request_row["blood_group"]
    donor_group = donor_row["blood_group"]
    compatible_set = PRELIMINARY_COMPATIBLE_DONOR_GROUPS.get(req_group, {req_group})
    if donor_group not in compatible_set:
        return False, 0.0, "Incompatible preliminary blood group"

    req_city = (request_row.get("city") or "").strip().lower()
    donor_city = (donor_row.get("city") or "").strip().lower()
    same_city = req_city == donor_city or (req_city in donor_city) or (donor_city in req_city)
    if not same_city and not allow_wider_city:
        return False, 0.0, "Outside initial city radius"

    reasons: List[str] = []
    score = 0.0

    if donor_group == req_group:
        score += 40.0
        reasons.append(f"Exact blood group ({donor_group})")
    else:
        score += 20.0
        reasons.append(f"Preliminary compatible group ({donor_group} for {req_group})")

    if same_city:
        score += 30.0
        reasons.append("Same city")
    else:
        score += 10.0
        reasons.append("Wider regional search")

    req_loc = (request_row.get("approximate_location") or "").strip().lower()
    donor_loc = (donor_row.get("approximate_location") or "").strip().lower()
    if req_loc and donor_loc and (req_loc in donor_loc or donor_loc in req_loc):
        score += 10.0
        reasons.append("Nearby approximate area")

    avail_scores = {
        "available_now": 25.0,
        "available_today": 15.0,
        "available_selected_dates": 15.0,
        "emergency_only": 10.0,
    }
    score += avail_scores.get(avail, 0.0)
    reasons.append(f"Availability: {avail.replace('_', ' ')}")

    ver_status = donor_row.get("verification_status", "not_submitted")
    if ver_status == "verified":
        score += 15.0
        reasons.append("Verified account")
    elif ver_status == "pending_review":
        score += 5.0
        reasons.append("Verification pending")

    if request_row.get("urgency") == "emergency":
        score += 5.0

    last_don = donor_row.get("last_donation_date")
    if last_don:
        try:
            days = (today_date - datetime.fromisoformat(str(last_don)[:10]).date()).days
            if 0 <= days < review_interval_days:
                score -= 20.0
                reasons.append(f"Recent donation ({days}d ago; blood-bank review required)")
        except ValueError:
            pass

    return True, round(score, 2), "; ".join(reasons)
