import re
from typing import Any, Dict, List
from urllib.parse import urlencode

BLOOD_GROUP_PATTERN = re.compile(r"(?<![A-Za-z])(AB|A|B|O)\s*([+-])(?=\s|$|[.,!?])", re.IGNORECASE)
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")

ASSISTANT_DISCLAIMER_EN = (
    "LifeLink Assistant is a rule-based platform guide, not a medical professional. "
    "It cannot diagnose conditions, decide donor medical eligibility, or guarantee blood availability."
)
ASSISTANT_DISCLAIMER_HI = (
    "LifeLink सहायक केवल प्लेटफ़ॉर्म गाइड है, डॉक्टर नहीं। यह बीमारी की जांच, रक्तदान की चिकित्सकीय पात्रता "
    "या रक्त की उपलब्धता की गारंटी नहीं दे सकता।"
)


def _wants_hindi(text: str, user: Dict[str, Any]) -> bool:
    if DEVANAGARI_PATTERN.search(text):
        return True
    lower = text.lower()
    hinglish_kws = ("khoon", "rakta", "madad", "chahiye", "aspatal", "stithi", "kaise", "hindi")
    if any(kw in lower for kw in hinglish_kws):
        return True
    return user.get("preferred_language") == "hi"


def generate_assistant_reply(
    *,
    message: str,
    user: Dict[str, Any],
    repo: Any,
) -> Dict[str, Any]:
    """Generate a transparent, rule-based, database-backed LifeLink Assistant response in English or Hindi."""
    text = message.strip()
    lower = text.lower()
    hi = _wants_hindi(text, user)
    disclaimer = ASSISTANT_DISCLAIMER_HI if hi else ASSISTANT_DISCLAIMER_EN

    # 1. Medical safety guardrails (diagnosis, eligibility, medication, transfusion advice)
    medical_keywords = (
        "diagnos",
        "medicine",
        "medication",
        "dosage",
        "transfus",
        "am i eligible",
        "medically fit",
        "hemoglobin",
        "disease",
        "symptom",
        "cure",
        "prescrib",
        "दवा",
        "इलाज",
        "बीमारी",
        "हीमोग्लोबिन",
        "जांच",
    )
    if any(kw in lower for kw in medical_keywords):
        return {
            "intent": "medical_safety_refusal",
            "reply": (
                "मैं केवल प्लेटफ़ॉर्म सहायक हूँ, डॉक्टर नहीं। मैं बीमारी की जांच, दवा, या रक्तदान के लिए आपकी "
                "चिकित्सकीय पात्रता तय नहीं कर सकता। कृपया डॉक्टर या लाइसेंस प्राप्त ब्लड बैंक से सलाह लें।"
                if hi
                else "I am a rule-based platform assistant, not a medical professional. I cannot diagnose "
                "medical conditions, prescribe medication, recommend transfusion procedures, or decide "
                "donor medical eligibility. Please consult a qualified physician or licensed blood bank."
            ),
            "suggested_actions": [
                {"label": "ब्लड बैंक सूची / Blood Banks" if hi else "Blood-Bank Directory", "url": "/pages/blood-banks.html"},
            ],
            "disclaimer": disclaimer,
        }

    # 2. Immediate emergency guidance
    if any(
        kw in lower
        for kw in (
            "immediate emergency",
            "urgent emergency",
            "critical",
            "bleeding",
            "accident",
            "emergency help",
            "तुरंत",
            "आपातकाल",
            "खून बह",
            "दुर्घटना",
        )
    ):
        return {
            "intent": "emergency_guidance",
            "reply": (
                "यदि यह तुरंत आपात स्थिति है, तो कृपया रक्तदाताओं का इंतज़ार न करें — तुरंत अस्पताल और "
                "ब्लड बैंक से सीधे संपर्क करें। आप साथ ही यहाँ रक्त अनुरोध फ़ॉर्म भी भर सकते हैं।"
                if hi
                else "If this is an immediate medical emergency, contact the treating hospital and its "
                "blood bank directly right away — do not delay emergency care while waiting for donor "
                "matching. I can also help you prepare a LifeLink request while you coordinate with the medical team."
            ),
            "suggested_actions": [
                {"label": "अभी रक्त मांगें / Create Request" if hi else "Create Blood Request", "url": "/pages/create-request.html?urgency=emergency"},
                {"label": "ब्लड बैंक / Blood Banks" if hi else "Blood-Bank Directory", "url": "/pages/blood-banks.html"},
            ],
            "disclaimer": disclaimer,
        }

    # 3. Request tracking / live database status lookup
    if any(kw in lower for kw in ("track", "status", "progress", "notified", "response", "my request", "स्थिति", "हाल", "stithi", "मेरा अनुरोध")):
        requests = repo.list_requests_for_user(str(user["id"]))
        if not requests:
            return {
                "intent": "request_tracking_empty",
                "reply": (
                    "आपके खाते में अभी कोई रक्त अनुरोध नहीं है। आप नया अनुरोध बना सकते हैं और उसकी स्थिति यहाँ देख सकते हैं।"
                    if hi
                    else "You do not have any blood requests recorded in your account yet. "
                    "You can create a structured request and I will help you track every status change."
                ),
                "suggested_actions": [
                    {"label": "नया रक्त अनुरोध / Create Request" if hi else "Create Blood Request", "url": "/pages/create-request.html"},
                ],
                "disclaimer": disclaimer,
            }

        uuid_match = UUID_PATTERN.search(text)
        target = None
        if uuid_match:
            req_id = uuid_match.group(0).lower()
            target = next((r for r in requests if str(r["id"]).lower() == req_id), None)
        if target is None:
            target = requests[0]

        matches = repo.list_matches_for_request(str(target["id"]))
        responses = repo.list_responses_for_request(str(target["id"]))
        accepted_count = sum(1 for r in responses if r["response"] == "accepted")
        declined_count = sum(1 for r in responses if r["response"] == "declined")

        extra_en = ""
        extra_hi = ""
        if int(target.get("escalation_stage", 1)) >= 4 or target["status"] == "blood_bank_assistance":
            extra_en = " Blood-bank assistance is currently recommended; please also contact the hospital's transfusion service."
            extra_hi = " अभी ब्लड बैंक से संपर्क करना आवश्यक है; कृपया अस्पताल के ब्लड बैंक से बात करें।"
        elif target["status"] == "escalation_in_progress":
            extra_en = " Search escalation is active."
            extra_hi = " आसपास और क्षेत्रों में खोज बढ़ाई गई है।"

        reply = (
            f"आपका ताज़ा अनुरोध ({target['blood_group']} — {target['hospital_name']}, {target['city']}): "
            f"स्थिति '{target['status'].replace('_', ' ')}' (चरण {target['escalation_stage']}/5)। "
            f"{len(matches)} संभावित रक्तदाताओं को सूचना भेजी गई, {len(responses)} जवाब मिले "
            f"({accepted_count} ने हाँ कहा, {declined_count} ने असमर्थता जताई)।{extra_hi}"
            if hi
            else f"Latest tracked request ({target['blood_group']} at {target['hospital_name']}, {target['city']}): "
            f"Current status is '{target['status'].replace('_', ' ')}' (Escalation Stage {target['escalation_stage']}/5). "
            f"{len(matches)} potential donor(s) notified, {len(responses)} response(s) recorded "
            f"({accepted_count} accepted, {declined_count} declined).{extra_en}"
        )
        return {
            "intent": "request_tracking",
            "reply": reply,
            "suggested_actions": [
                {"label": "विवरण देखें / Open Details" if hi else "Open Request Details", "url": f"/pages/request-details.html?id={target['id']}"},
                {"label": "मेरे अनुरोध / My Requests" if hi else "View All My Requests", "url": "/pages/my-requests.html"},
            ],
            "disclaimer": disclaimer,
        }

    # 4. Guided blood request creation draft (never silently submits)
    bg_match = BLOOD_GROUP_PATTERN.search(text)
    if (
        any(
            kw in lower
            for kw in (
                "create request",
                "need blood",
                "request blood",
                "arrange blood",
                "find blood",
                "खून",
                "रक्त",
                "चाहिए",
                "khoon",
                "chahiye",
                "रक्त मांग",
            )
        )
        or ("need" in lower and "blood" in lower)
        or bg_match
    ):
        draft: Dict[str, str] = {}
        if bg_match:
            draft["blood_group"] = f"{bg_match.group(1).upper()}{bg_match.group(2)}"
        if "emergency" in lower or "तुरंत" in lower:
            draft["urgency"] = "emergency"
        elif "normal" in lower or "सामान्य" in lower:
            draft["urgency"] = "normal"
        elif "urgent" in lower or "ज़रूरी" in lower:
            draft["urgency"] = "urgent"

        city_match = re.search(r"\bin\s+([A-Za-z]+)", text)
        if city_match:
            draft["city"] = city_match.group(1).strip().rstrip(".,!?")

        qs = urlencode(draft)
        url = f"/pages/create-request.html?{qs}" if qs else "/pages/create-request.html"
        summary_parts = [f"{k.replace('_', ' ')}: {v}" for k, v in draft.items()]
        summary = f" Pre-filled fields detected ({', '.join(summary_parts)})." if summary_parts else ""
        return {
            "intent": "create_request_guidance",
            "reply": (
                "रक्त अनुरोध बनाने के लिए मरीज़ का संदर्भ नाम, आवश्यक ब्लड ग्रुप, यूनिट संख्या, अस्पताल का नाम, शहर और सहमति दर्ज करें। "
                "सबमिट करने से पहले सभी विवरण जांच लें।"
                if hi
                else "To create a blood request, you will need the patient reference name, required blood group, "
                "units needed, hospital name and area, city, urgency level, and consent confirmation."
                f"{summary} Review and confirm the form before submitting — I never submit requests without your confirmation."
            ),
            "suggested_actions": [
                {"label": "फ़ॉर्म खोलें / Open Form" if hi else "Open Pre-Filled Request Form", "url": url},
            ],
            "disclaimer": disclaimer,
        }

    # 5. Privacy & contact sharing FAQ
    if any(kw in lower for kw in ("privacy", "phone", "number", "chat", "contact sharing", "report", "block", "फ़ोन", "नंबर", "गोपनीय", "चैट")):
        return {
            "intent": "privacy_faq",
            "reply": (
                "LifeLink में आपका फ़ोन नंबर और घर का पता सार्वजनिक खोज में कभी नहीं दिखता। "
                "रक्तदाता के हाँ करने पर सुरक्षित इन-ऐप चैट खुलती है, और दोनों पक्षों की सहमति के बिना फ़ोन नंबर साझा नहीं होता।"
                if hi
                else "LifeLink keeps phone numbers and exact home addresses hidden in donor searches. "
                "Private in-app chat opens only after a donor accepts a request. Phone numbers are shared "
                "only if both the requester and donor explicitly consent, and you can block or report any suspicious user."
            ),
            "suggested_actions": [
                {"label": "संदेश / Open Chat" if hi else "Open Private Messages", "url": "/pages/messages.html"},
                {"label": "गोपनीयता नीति / Privacy" if hi else "Read Privacy Policy", "url": "/pages/privacy.html"},
            ],
            "disclaimer": disclaimer,
        }

    # 6. Blood-bank directory guidance
    if any(kw in lower for kw in ("blood bank", "eraktkosh", "e-raktkosh", "hospital", "stock", "ब्लड बैंक", "अस्पताल", "स्टॉक")):
        return {
            "intent": "blood_bank_guidance",
            "reply": (
                "आप LifeLink की ब्लड बैंक सूची देख सकते हैं या भारत सरकार के e-RaktKosh पोर्टल पर जांच कर सकते हैं। "
                "स्टॉक की पक्की जानकारी के लिए ब्लड बैंक को सीधे फ़ोन अवश्य करें।"
                if hi
                else "You can search listed facilities in LifeLink's Blood-Bank Directory or check India's official "
                "e-RaktKosh portal. LifeLink never fabricates stock availability; always call the facility directly to confirm."
            ),
            "suggested_actions": [
                {"label": "ब्लड बैंक सूची / Directory" if hi else "Open Blood-Bank Directory", "url": "/pages/blood-banks.html"},
            ],
            "disclaimer": disclaimer,
        }

    # 7. Find potential donors guidance
    if any(kw in lower for kw in ("donor", "match", "search", "compatible", "रक्तदाता", "खोज")):
        return {
            "intent": "donor_search_guidance",
            "reply": (
                "LifeLink उपलब्धता, शहर और सत्यापन स्थिति के आधार पर संभावित रक्तदाताओं को खोजता है। "
                "अंतिम चिकित्सकीय जांच और क्रॉस-मैचिंग केवल लाइसेंस प्राप्त ब्लड बैंक द्वारा ही की जाती है।"
                if hi
                else "LifeLink prioritizes potential donors using transparent rules: availability status, city/location, "
                "verification state, and notification opt-in. A match is a preliminary candidate only — final "
                "medical eligibility and crossmatching are handled by the blood bank."
            ),
            "suggested_actions": [
                {"label": "रक्तदाता खोजें / Search Donors" if hi else "Search Potential Donors", "url": "/pages/find-donors.html"},
                {"label": "रक्तदाता प्रोफ़ाइल / Profile" if hi else "Manage My Donor Profile", "url": "/pages/donor-profile.html"},
            ],
            "disclaimer": disclaimer,
        }

    # Default help menu
    return {
        "intent": "help_overview",
        "reply": (
            "मैं LifeLink सहायक हूँ। आप मुझसे पूछ सकते हैं: "
            "(1) रक्त अनुरोध बनाने में मदद, (2) अपने अनुरोध की स्थिति देखना, "
            "(3) रक्तदाता मिलान के बारे में जानकारी, (4) नज़दीकी ब्लड बैंक खोजना, या (5) गोपनीयता नियम।"
            if hi
            else "I am LifeLink Assistant (rule-based platform guide). Ask me to: "
            "(1) help prepare a blood request, (2) track your active request status, "
            "(3) explain donor matching, (4) guide you to blood banks, or (5) explain privacy and contact sharing."
        ),
        "suggested_actions": [
            {"label": "रक्त मांगें / Request Blood" if hi else "Create Blood Request", "url": "/pages/create-request.html"},
            {"label": "स्थिति देखें / Track Request" if hi else "Track My Request", "url": "/pages/my-requests.html"},
            {"label": "ब्लड बैंक / Blood Banks" if hi else "Blood-Bank Directory", "url": "/pages/blood-banks.html"},
        ],
        "disclaimer": disclaimer,
    }
