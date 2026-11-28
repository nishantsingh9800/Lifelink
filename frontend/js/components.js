const LifeLinkUI = (() => {
  const TRANSLATIONS = {
    en: {
      brand_sub: "Emergency Donor Coordination",
      nav_home: "Home",
      nav_how_it_works: "How It Works",
      nav_find_donors: "Find Donors",
      nav_blood_banks: "Blood Banks",
      nav_about: "About",
      nav_login: "Login",
      nav_register: "Request Blood Now",
      nav_dashboard: "Dashboard",
      nav_create_request: "Request Blood Now",
      nav_my_requests: "My Requests",
      nav_incoming_requests: "Incoming Alerts",
      nav_donor_profile: "Donor Profile",
      nav_notifications: "Notifications",
      nav_messages: "Messages",
      nav_assistant: "Assistant",
      nav_admin: "Admin Console",
      nav_hospital_portal: "Hospital Portal",
      logout: "Logout",
      emergency_notice: "Emergency Notice: LifeLink coordinates donor outreach. In immediate medical emergencies, contact the treating hospital and licensed blood bank directly.",
    },
    hi: {
      brand_sub: "आपातकालीन रक्तदाता समन्वय",
      nav_home: "होम",
      nav_how_it_works: "कैसे काम करता है",
      nav_find_donors: "रक्तदाता खोजें",
      nav_blood_banks: "ब्लड बैंक",
      nav_about: "परिचय",
      nav_login: "लॉगिन",
      nav_register: "अभी रक्त अनुरोध करें",
      nav_dashboard: "डैशबोर्ड",
      nav_create_request: "अभी रक्त अनुरोध करें",
      nav_my_requests: "मेरे अनुरोध",
      nav_incoming_requests: "आने वाले अलर्ट",
      nav_donor_profile: "रक्तदाता प्रोफ़ाइल",
      nav_notifications: "सूचनाएं",
      nav_messages: "संदेश",
      nav_assistant: "सहायक",
      nav_admin: "एडमिन कंसोल",
      nav_hospital_portal: "अस्पताल पोर्टल",
      logout: "लॉगआउट",
      hero_cta_req: "अभी रक्त अनुरोध करें",
      hero_cta_reg: "खाता बनाएं",
      hero_cta_find: "रक्तदाता खोजें",
      hero_cta_bb: "ब्लड बैंक सूची",
      emergency_notice: "आपातकालीन सूचना: LifeLink केवल समन्वय मंच है। तुरंत चिकित्सा आवश्यकता में अस्पताल व लाइसेंस प्राप्त ब्लड बैंक से सीधे संपर्क करें।",
    },
    mr: {
      brand_sub: "आपत्कालीन रक्तदाता समन्वय",
      nav_home: "होम",
      nav_find_donors: "रक्तदाते शोधा",
      nav_blood_banks: "रक्तपेढी",
      nav_login: "लॉगिन",
      nav_register: "त्वरित रक्त विनंती",
      nav_dashboard: "डॅशबोर्ड",
      nav_create_request: "त्वरित रक्त विनंती",
      logout: "लॉगआउट",
      emergency_notice: "आपत्कालीन सूचना: LifeLink फक्त समन्वय मंच आहे. तातडीच्या गरजेसाठी रुग्णालयाशी संपर्क साधा.",
    },
    bn: {
      brand_sub: "জরুরি রক্তদাতা সমন্বয়",
      nav_home: "হোম",
      nav_find_donors: "রক্তদাতা খুঁজুন",
      nav_blood_banks: "ব্লাড ব্যাংক",
      nav_login: "লগইন",
      nav_register: "এখনই রক্ত চান",
      nav_dashboard: "ড্যাশবোর্ড",
      nav_create_request: "এখনই রক্ত চান",
      logout: "লগআউট",
      emergency_notice: "জরুরি বিজ্ঞপ্তি: LifeLink একটি সমন্বয় প্ল্যাটফর্ম। জরুরি অবস্থায় সরাসরি হাসপাতালের ব্লাড ব্যাংকে যোগাযোগ করুন।",
    },
    ta: {
      brand_sub: "அவசர இரத்த தான ஒருங்கிணைப்பு",
      nav_home: "முகப்பு",
      nav_find_donors: "கொடையாளர்களைத் தேடு",
      nav_blood_banks: "இரத்த வங்கிகள்",
      nav_login: "உள்நுழைக",
      nav_register: "உடனடி இரத்த கோரிக்கை",
      nav_dashboard: "டாஷ்போர்டு",
      nav_create_request: "உடனடி இரத்த கோரிக்கை",
      logout: "வெளியேறு",
      emergency_notice: "அவசர அறிவிப்பு: LifeLink ஒருங்கிணைப்பு தளம் மட்டுமே. உடனடி தேவைக்கு மருத்துவமனையை நேரடியாக அணுகவும்.",
    },
  };

  function getLanguage() {
    const saved = localStorage.getItem("lifelink_lang");
    return ["en", "hi", "mr", "bn", "ta"].includes(saved) ? saved : "en";
  }

  function applyAccessibilityFromStorage() {
    const html = document.documentElement;
    const size = localStorage.getItem("lifelink_a11y_text") || "normal";
    const contrast = localStorage.getItem("lifelink_a11y_contrast") === "1";
    html.classList.remove("a11y-text-lg", "a11y-text-xl", "a11y-high-contrast");
    if (size === "large") html.classList.add("a11y-text-lg");
    if (size === "xlarge") html.classList.add("a11y-text-xl");
    if (contrast) html.classList.add("a11y-high-contrast");
    html.lang = getLanguage();
  }

  const PHRASEBOOK_HI = {
    "LifeLink — Smart Blood Donor Matching & Emergency Response System": "LifeLink — स्मार्ट रक्तदाता मिलान और आपातकालीन सहायता प्रणाली",
    "Smart Blood Donor Matching & Emergency Response System": "स्मार्ट रक्तदाता मिलान और आपातकालीन सहायता प्रणाली",
    "Emergency Coordination Platform · Team LogicLoom": "आपातकालीन समन्वय मंच · टीम LogicLoom",
    "Team LogicLoom · GL Bajaj Mathura": "टीम LogicLoom · जीएल बजाज मथुरा",
    "Coordinated blood donor response when every minute counts.": "हर मिनट कीमती है — ज़रूरत के समय सही रक्तदाता से तुरंत जुड़ें।",
    "Most platforms help people find donors. LifeLink is designed to help coordinate the entire emergency response — combining prioritized donor alerts, privacy-first in-app chat, progressive search escalation, and blood-bank fallback assistance.": "LifeLink केवल रक्तदाता ढूँढने में नहीं, बल्कि पूरे आपातकालीन रक्त समन्वय में मदद करता है — प्राथमिकता अलर्ट, सुरक्षित चैट, चरणबद्ध खोज और ब्लड बैंक सहायता एक साथ।",
    "Request Blood Now": "अभी रक्त अनुरोध करें",
    "Register Account": "नया खाता बनाएं",
    "Search Donors": "रक्तदाता खोजें",
    "Blood-Bank Directory": "ब्लड बैंक सूची",
    "Easy 3-Step Visual Guide (आसान 3 चरण)": "आसान 3 चरण (सरल मार्गदर्शन)",
    "Simple guidance in everyday language. Switch between English and हिन्दी anytime using the top bar.": "सरल और आसान भाषा में मार्गदर्शन। ऊपर दिए बटन से कभी भी English और हिन्दी बदलें।",
    "1. Request Blood Now": "1. अभी रक्त अनुरोध करें",
    "Tap the red button, choose blood group and hospital name.": "लाल बटन दबाएं, ब्लड ग्रुप और अस्पताल का नाम भरें।",
    "2. Find Potential Donors": "2. पास के रक्तदाता खोजें",
    "Nearby verified helpers receive safe alerts without seeing your phone number.": "पास के सत्यापित रक्तदाताओं को आपका फ़ोन नंबर दिखाए बिना सुरक्षित अलर्ट मिलता है।",
    "3. Hospital & Blood Bank": "3. अस्पताल व ब्लड बैंक",
    "View verified blood-bank phone numbers and directions immediately.": "तुरंत सत्यापित ब्लड बैंक का फ़ोन नंबर और रास्ता देखें।",
    "How LifeLink Coordinates an Emergency": "LifeLink आपात स्थिति में कैसे मदद करता है",
    "From verified request creation to 5-stage progressive escalation and hospital fallback.": "अनुरोध बनाने से लेकर 5-चरण खोज और अस्पताल सहायता तक।",
    "Structured Request & Verification": "सुव्यवस्थित अनुरोध और सत्यापन",
    "Verified requesters submit hospital location, blood group, and urgency.": "सत्यापित उपयोगकर्ता अस्पताल, ब्लड ग्रुप और आपातकाल स्तर दर्ज करते हैं।",
    "Rule-Based Prioritized Alerts": "नियम-आधारित प्राथमिकता अलर्ट",
    "Nearby available potential donors are notified without exposing phone numbers.": "पास के उपलब्ध रक्तदाताओं को फ़ोन नंबर साझा किए बिना सूचित किया जाता है।",
    "Private In-App Communication": "निजी ऐप-के-भीतर चैट",
    "Accepting a request unlocks a private chat between requester and donor without exposing phone numbers.": "अनुरोध स्वीकार करने पर अनुरोधकर्ता और रक्तदाता के बीच फ़ोन नंबर छिपाकर निजी चैट खुलती है।",
    "5-Stage Escalation & Blood-Bank Fallback": "5-चरण खोज और ब्लड बैंक सहायता",
    "Expands radius automatically and directs to licensed blood banks if needed.": "ज़रूरत पड़ने पर दायरा बढ़ाता है और लाइसेंस प्राप्त ब्लड बैंकों से जोड़ता है।",
    "Built for Safety, Privacy, and Accountability": "सुरक्षा, गोपनीयता और भरोसे के लिए बनाया गया",
    "Every workflow protects personal contact details and avoids unverified medical claims.": "हर प्रक्रिया व्यक्तिगत संपर्क को सुरक्षित रखती है और झूठे चिकित्सा दावों से बचती है।",
    "Private Phone Protection:": "निजी फ़ोन नंबर सुरक्षा:",
    "Phone numbers and exact residential addresses are never shown in donor search results. Private conversations open only between a requester and an accepting donor.": "रक्तदाता खोज में फ़ोन नंबर और घर का सटीक पता कभी नहीं दिखता। निजी चैट केवल स्वीकार करने के बाद ही खुलती है।",
    "Medical Eligibility Notice:": "चिकित्सा पात्रता सूचना:",
    "Basic ABO/Rh group matching is preliminary only; crossmatching and donor eligibility are decided by licensed healthcare professionals.": "ब्लड ग्रुप मिलान केवल प्रारंभिक है; क्रॉसमैच और रक्तदान की पात्रता केवल लाइसेंस प्राप्त डॉक्टर/ब्लड बैंक ही तय करते हैं।",
    "No Fake Availability:": "कोई झूठा स्टॉक नहीं:",
    "LifeLink does not fabricate donor records or blood-bank stock numbers.": "LifeLink कभी भी नकली रक्तदाता या नकली ब्लड-बैंक स्टॉक संख्या नहीं दिखाता।",
    "Emergency Care:": "आपातकालीन देखभाल:",
    "In immediate emergencies, contact your treating hospital's blood bank directly alongside any platform outreach.": "तुरंत आपात स्थिति में अपने अस्पताल के ब्लड बैंक से सीधे संपर्क करें।",
    "Supported ABO / Rh Blood Groups": "समर्थित ब्लड ग्रुप (ABO / Rh)",
    "Preliminary group matching only. Final compatibility, crossmatching, and screening are performed exclusively by licensed blood centres.": "केवल प्रारंभिक मिलान। अंतिम जांच और क्रॉसमैच केवल लाइसेंस प्राप्त ब्लड सेंटर में ही होता है।",

    /* Navigation, footer & top bar */
    "Menu": "मेनू",
    "Contrast": "कॉन्ट्रास्ट",
    "Toggle navigation": "नेविगेशन खोलें/बंद करें",
    "Platform": "प्लेटफ़ॉर्म",
    "Privacy & Safety": "गोपनीयता व सुरक्षा",
    "How It Works": "कैसे काम करता है",
    "Find Donors": "रक्तदाता खोजें",
    "About LifeLink": "LifeLink के बारे में",
    "Privacy Policy": "गोपनीयता नीति",
    "Terms & Conditions": "नियम व शर्तें",
    "API Documentation": "API दस्तावेज़",
    "Built by Team LogicLoom, GL Bajaj Group of Institutions, Mathura. LifeLink does not guarantee blood availability or determine medical eligibility; clinical screening and crossmatching are handled solely by licensed blood centres.": "टीम LogicLoom, जीएल बजाज ग्रुप ऑफ़ इंस्टीट्यूशंस, मथुरा द्वारा निर्मित। LifeLink रक्त उपलब्धता की गारंटी नहीं देता और न ही चिकित्सा पात्रता तय करता है; चिकित्सीय जांच केवल लाइसेंस प्राप्त ब्लड सेंटर करते हैं।",

    /* Login & Register */
    "Login — LifeLink": "लॉगिन — LifeLink",
    "Account Sign In": "खाते में लॉगिन",
    "Sign in to LifeLink": "LifeLink में लॉगिन करें",
    "Access your requester, donor, or administrator workspace.": "अपने अनुरोधकर्ता, रक्तदाता या एडमिन खाते में प्रवेश करें।",
    "Email Address or Phone Number": "ईमेल या फ़ोन नंबर",
    "Password": "पासवर्ड",
    "Enter your password": "अपना पासवर्ड लिखें",
    "Sign In": "लॉगिन करें",
    "Signing in...": "लॉगिन हो रहा है...",
    "Need an account?": "नया खाता चाहिए?",
    "Register here": "यहाँ पंजीकरण करें",
    "Register — LifeLink": "पंजीकरण — LifeLink",
    "Register on LifeLink": "LifeLink पर नया खाता बनाएं",
    "Create your LifeLink account quickly without Aadhaar at signup. When Aadhaar e-KYC is active, it is verified only when donating or receiving blood.": "बिना आधार के तुरंत खाता बनाएं। जब आधार सत्यापन सक्रिय हो, तब यह केवल रक्तदान या रक्त लेते समय मांगा जाएगा।",
    "Full Name": "पूरा नाम",
    "Email Address": "ईमेल पता",
    "Phone Number": "फ़ोन नंबर",
    "Date of Birth": "जन्म तिथि",
    "City": "शहर",
    "General / Approximate Location": "क्षेत्र / नज़दीकी इलाका",
    "Do not enter exact house number.": "घर का सटीक पता न लिखें।",
    "Account Role": "खाते की भूमिका",
    "Requester (Need blood for patient)": "अनुरोधकर्ता (मरीज़ के लिए रक्त चाहिए)",
    "Donor (Willing to receive requests)": "रक्तदाता (रक्तदान करने के लिए तैयार)",
    "Hospital / Authorized Representative": "अस्पताल / अधिकृत प्रतिनिधि",
    "Blood Group (Donor)": "ब्लड ग्रुप (रक्तदाता)",
    "Select blood group": "ब्लड ग्रुप चुनें",
    "Referral Code (Optional)": "रेफ़रल कोड (वैकल्पिक)",
    "Minimum 8 characters": "कम से कम 8 अक्षर",
    "No Aadhaar number is needed to register or log in. When deployed, Aadhaar authentication is requested only when donating or requesting blood.": "साइनअप या लॉगिन के लिए आधार नंबर ज़रूरी नहीं है। लागू होने पर आधार केवल रक्तदान या रक्त मांगते समय मांगा जाता है।",
    "Local Development Mode active. You can register and sign in without Aadhaar while Aadhaar e-KYC is turned off.": "लोकल डेवलपमेंट मोड चालू है। आधार e-KYC बंद होने के कारण आप बिना आधार पंजीकरण और लॉगिन कर सकते हैं।",
    "Local Development Mode active (Supabase credentials not configured). Using local SQLite authentication for demonstration.": "लोकल डेवलपमेंट मोड सक्रिय है। प्रदर्शन के लिए लोकल SQLite उपयोग हो रहा है।",
    "I agree to the": "मैं सहमत हूँ",
    ", and understand that LifeLink does not guarantee blood availability or replace hospital blood banks.": "और समझता/समझती हूँ कि LifeLink रक्त उपलब्धता की गारंटी नहीं देता और न ही अस्पताल के ब्लड बैंक का विकल्प है।",
    "Create Verified Account": "खाता बनाएं",
    "Creating account...": "खाता बन रहा है...",
    "Already registered?": "पहले से खाता बना है?",
    "Sign in": "लॉगिन करें",
    "Authenticate Aadhaar": "आधार सत्यापित करें",
    "Aarav Sharma": "आरव शर्मा",
    "aarav@example.com": "aarav@example.com",
    "you@example.com or +919876543210": "ईमेल या +919876543210",
    "e.g., Chaumuha / NH-19": "जैसे: चौमुहा / NH-19",
    "Mathura": "मथुरा",
    "e.g., Mathura": "जैसे: मथुरा",
    "e.g., Mathura, Agra": "जैसे: मथुरा, आगरा",
    "e.g., LL-1A2B3C4D": "जैसे: LL-1A2B3C4D",
    "12-digit Aadhaar number": "12 अंकों का आधार नंबर",

    /* Dashboard */
    "Dashboard — LifeLink": "डैशबोर्ड — LifeLink",
    "Welcome": "स्वागत है",
    "Loading your verified workspace...": "आपका खाता लोड हो रहा है...",
    "Phone Verification Required": "फ़ोन सत्यापन आवश्यक है",
    "Verify your phone number via SMS OTP to activate full emergency coordination.": "पूर्ण आपातकालीन समन्वय चालू करने के लिए SMS OTP से अपना फ़ोन नंबर सत्यापित करें।",
    "Send SMS OTP": "SMS OTP भेजें",
    "Enter OTP code": "OTP कोड लिखें",
    "Verify OTP": "OTP सत्यापित करें",
    "Development-Only: Verify Phone Locally": "लोकल मोड: फ़ोन तुरंत सत्यापित करें",
    "Enabled only when live SMS OTP is not configured.": "जब लाइव SMS OTP सेट न हो तब उपलब्ध।",
    "Quick Availability Update": "त्वरित उपलब्धता बदलाव",
    "Profile & Location Settings": "प्रोफ़ाइल और स्थान सेटिंग्स",
    "Save Profile Updates": "बदलाव सहेजें",
    "Notification & Accessibility Preferences": "सूचना और भाषा/सुविधा सेटिंग्स",
    "Preferred Search Distance (km)": "खोज की पसंदीदा दूरी (किमी)",
    "Quiet Hours Start (24h HH:MM)": "शांत समय शुरू (24h HH:MM)",
    "Quiet Hours End (24h HH:MM)": "शांत समय समाप्त (24h HH:MM)",
    "Receive in-app emergency & lifecycle notifications": "ऐप के भीतर आपातकालीन व स्थिति सूचनाएं प्राप्त करें",
    "Respect configured donor quiet hours for normal requests": "सामान्य अनुरोधों के लिए शांत समय का पालन करें",
    "Allow critical emergency requests to bypass quiet hours": "गंभीर आपातकालीन अनुरोधों को शांत समय में भी आने दें",
    "Save Notification Preferences": "सूचना सेटिंग्स सहेजें",
    "Emergency Coordinator Assignments": "आपातकालीन समन्वयक ज़िम्मेदारियां",
    "Requests where a requester explicitly authorized you to help coordinate blood banks and donor chats.": "वे अनुरोध जहाँ अनुरोधकर्ता ने आपको ब्लड बैंक और चैट समन्वय की अनुमति दी है।",
    "Checking coordinator invitations...": "समन्वयक निमंत्रण देखे जा रहे हैं...",
    "Family Emergency Account": "परिवार आपातकालीन खाता",
    "Authorize trusted family members to create or manage blood requests on your behalf. Permissions can be revoked anytime.": "विश्वसनीय परिवारजन को अपनी ओर से रक्त अनुरोध बनाने या संभालने की अनुमति दें। अनुमति कभी भी हटाई जा सकती है।",
    "Trusted user email or phone number": "परिवार के सदस्य का ईमेल या फ़ोन नंबर",
    "Family member email or phone number": "परिवार के सदस्य का ईमेल या फ़ोन नंबर",
    "Relationship (e.g., Spouse, Sibling, Parent)": "रिश्ता (जैसे: भाई, बहन, माता-पिता)",
    "Authorize Family Member": "परिवार के सदस्य को अनुमति दें",
    "Community Referral & Awareness": "मित्रों को जोड़ें (रेफ़रल)",
    "Invite friends to register voluntarily. LifeLink prevents spam and does not operate competitive leaderboards.": "मित्रों को स्वेच्छा से जुड़ने के लिए आमंत्रित करें। LifeLink स्पैम रोकता है।",
    "Loading referral summary...": "रेफ़रल जानकारी लोड हो रही है...",
    "Aadhaar Check Paused (Pre-Deployment):": "आधार जांच अभी बंद है (प्री-डिप्लॉयमेंट):",
    "Create Blood Request": "रक्त अनुरोध बनाएं",
    "Donor Profile": "रक्तदाता प्रोफ़ाइल",
    "Accept Assignment": "ज़िम्मेदारी स्वीकारें",
    "Decline": "अस्वीकार करें",
    "Open Coordination View": "समन्वय पेज खोलें",
    "Revoke": "हटाएं",
    "No emergency coordinator invitations or assignments.": "कोई आपातकालीन समन्वयक निमंत्रण या ज़िम्मेदारी नहीं है।",
    "No trusted family contacts linked yet.": "अभी कोई परिवार का सदस्य जुड़ा नहीं है।",
    "No blood requests created yet": "अभी कोई रक्त अनुरोध नहीं बनाया गया है",
    "Create a structured emergency blood request to start donor coordination.": "रक्तदाता समन्वय शुरू करने के लिए नया रक्त अनुरोध बनाएं।",
    "Notification preferences saved.": "सूचना सेटिंग्स सहेजी गईं।",
    "Profile updated successfully.": "प्रोफ़ाइल सफलतापूर्वक अपडेट हुई।",
    "Family member authorization sent.": "परिवार के सदस्य को अनुमति भेजी गई।",
    "Family authorization revoked.": "परिवार की अनुमति हटाई गई।",
    "Coordinator response saved.": "समन्वयक उत्तर सहेजा गया।",
    "Referral summary unavailable right now.": "रेफ़रल जानकारी अभी उपलब्ध नहीं है।",

    /* Create Request */
    "Request Blood Now — LifeLink": "अभी रक्त अनुरोध करें — LifeLink",
    "Quick Emergency Request": "त्वरित आपातकालीन अनुरोध",
    "Submit a blood request for a patient (yourself or on behalf of a family member). Review details carefully before sending.": "मरीज़ (स्वयं या परिवारजन) के लिए रक्त अनुरोध दर्ज करें। भेजने से पहले सभी जानकारी ध्यान से जांचें।",
    "Quick Emergency Flow (fewer steps)": "त्वरित आपातकालीन मोड (कम चरण)",
    "Creating Request For": "किसके लिए अनुरोध बनाया जा रहा है",
    "Myself (Own Account)": "स्वयं (अपना खाता)",
    "Aadhaar Verification Required Before Receiving Blood": "रक्त अनुरोध करने से पहले आधार सत्यापन आवश्यक",
    "Enter your 12-digit Aadhaar once to verify your identity for blood requests.": "रक्त अनुरोध के लिए अपनी पहचान सत्यापित करने हेतु 12 अंकों का आधार नंबर दर्ज करें।",
    "I consent to Aadhaar verification before requesting blood.": "मैं रक्त अनुरोध से पहले आधार सत्यापन की सहमति देता/देती हूँ।",
    "Verify Aadhaar": "आधार सत्यापित करें",
    "Patient / Ward Reference Name": "मरीज़ या वार्ड का नाम",
    "e.g., Ward 4 / R. Kumar": "जैसे: वार्ड 4 / आर. कुमार",
    "Required Blood Group": "ज़रूरी ब्लड ग्रुप",
    "Units Needed": "कितनी यूनिट चाहिए",
    "Urgency Level": "आपातकाल स्तर",
    "Emergency (Immediate Need)": "आपातकालीन (तुरंत आवश्यकता)",
    "Urgent": "अति आवश्यक",
    "Normal / Scheduled": "सामान्य / निर्धारित",
    "Hospital Name": "अस्पताल का नाम",
    "e.g., District Hospital Mathura": "जैसे: ज़िला अस्पताल मथुरा",
    "Hospital Location / Area": "अस्पताल का इलाका",
    "e.g., Dampier Nagar": "जैसे: डैम्पियर नगर",
    "Approximate Location / Sector": "नज़दीकी सेक्टर या पहचान",
    "General area or landmark": "नज़दीकी क्षेत्र या प्रमुख पहचान",
    "Required Date & Time": "कब तक रक्त चाहिए (तारीख व समय)",
    "Contact Preference": "संपर्क का तरीका",
    "Private In-App Chat (Recommended)": "निजी ऐप-के-भीतर चैट (अनुशंसित)",
    "Mutual-Consent Phone Sharing": "दोनों की सहमति से फ़ोन नंबर साझा करना",
    "Authorized Family / Coordinator Name (Optional)": "अधिकृत परिवार / समन्वयक का नाम (वैकल्पिक)",
    "If submitting on behalf of family": "यदि परिवार की ओर से भेज रहे हैं",
    "Relationship / Role (Optional)": "रिश्ता / भूमिका (वैकल्पिक)",
    "e.g., Sister / Attendant": "जैसे: बहन / परिचारक",
    "Optional Supporting Coordination Info (No private medical history)": "अतिरिक्त समन्वय जानकारी (निजी मेडिकल इतिहास न लिखें)",
    "e.g., Blood Bank Counter #2, Case Ref": "जैसे: ब्लड बैंक काउंटर #2",
    "I consent to LifeLink processing and sharing these coordination details (phone number stays private unless mutually consented).": "मैं समन्वय के लिए ये विवरण उपयोग करने की सहमति देता/देती हूँ (मेरा फ़ोन नंबर बिना सहमति गुप्त रहेगा)।",
    "Review Request Before Submitting": "भेजने से पहले विवरण जांचें",
    "Submit Blood Request": "रक्त अनुरोध भेजें",
    "Submitting request...": "अनुरोध भेजा जा रहा है...",
    "Review Emergency Request Details": "आपातकालीन अनुरोध का विवरण जांचें",
    "Confirming will create this request once (duplicate active requests for the same blood group & city are prevented automatically).": "पुष्टि करने पर यह अनुरोध एक बार दर्ज होगा (एक ही शहर व ब्लड ग्रुप के दोहरे अनुरोध अपने आप रोके जाते हैं)।",
    "Edit Details": "विवरण बदलें",
    "Confirm & Submit Request": "पुष्टि करें और भेजें",
    "Submitting...": "भेजा जा रहा है...",
    "Request Recorded": "अनुरोध दर्ज हो गया",
    "Blood Request Submitted": "रक्त अनुरोध सफलतापूर्वक दर्ज",
    "Open Live Request Tracking": "लाइव अनुरोध स्थिति देखें",
    "View Nearby Blood Banks": "नज़दीकी ब्लड बैंक देखें",
    "Aadhaar verification when requesting/receiving blood is currently turned OFF (pre-deployment mode).": "रक्त अनुरोध/प्राप्त करते समय आधार सत्यापन अभी बंद है (प्री-डिप्लॉयमेंट मोड)।",
    "Aadhaar verified. You can now submit your blood request.": "आधार सत्यापित हो गया। अब आप रक्त अनुरोध भेज सकते हैं।",

    /* Find Donors */
    "Find Potential Donors — LifeLink": "संभावित रक्तदाता खोजें — LifeLink",
    "Find Potential Donors": "संभावित रक्तदाता खोजें",
    "Search registered donors who have marked themselves available. Phone numbers and exact home addresses are kept private.": "उपलब्ध पंजीकृत रक्तदाताओं को खोजें। फ़ोन नंबर और घर का पता गुप्त रखा जाता है।",
    "Platform results show candidate donors only. Final compatibility, health screening, and donation eligibility must be determined by a licensed blood bank or healthcare professional.": "यहाँ केवल संभावित रक्तदाता दिखाए जाते हैं। अंतिम पात्रता और स्वास्थ्य जांच केवल लाइसेंस प्राप्त ब्लड बैंक या डॉक्टर तय करते हैं।",
    "Blood Group": "ब्लड ग्रुप",
    "All blood groups": "सभी ब्लड ग्रुप",
    "Approximate Location": "नज़दीकी क्षेत्र",
    "Search Candidates": "रक्तदाता खोजें",
    "Searching registered potential donors...": "पंजीकृत रक्तदाताओं की खोज हो रही है...",
    "No available potential donors matched your filters": "आपके फ़िल्टर के अनुसार कोई उपलब्ध रक्तदाता नहीं मिला",

    /* Blood Banks & Hospitals Directory */
    "Blood-Bank Directory — LifeLink": "ब्लड बैंक सूची — LifeLink",
    "Blood-Bank Directory & Official Fallback": "ब्लड बैंक सूची व सरकारी पोर्टल",
    "Search verified blood-bank directory entries or check official national registries.": "नज़दीकी ब्लड बैंक, अस्पताल और सरकारी e-RaktKosh पोर्टल देखें।",
    "Nearby Blood Banks, Hospitals & e-RaktKosh Live Stock": "नज़दीकी ब्लड बैंक, अस्पताल और e-RaktKosh लाइव स्टॉक",
    "LifeLink lists verified directory entries and real nearby hospitals/blood banks with contact numbers and Google Maps links. Real-time blood-unit inventory per group comes from official e-RaktKosh or calling the facility directly (never fabricated).": "LifeLink वास्तविक नज़दीकी ब्लड बैंकों व अस्पतालों के नाम, फ़ोन नंबर और Google Maps लिंक दिखाता है। लाइव यूनिट संख्या के लिए सीधे फ़ोन करें या e-RaktKosh देखें।",
    "Open Google Maps Nearby": "Google Maps पर पास में देखें",
    "Check Live Stock on e-RaktKosh": "e-RaktKosh पर लाइव स्टॉक देखें",
    "Facility Type": "सुविधा का प्रकार",
    "Blood Banks & Hospitals": "ब्लड बैंक और अस्पताल दोनों",
    "Blood Banks Only": "केवल ब्लड बैंक",
    "Hospitals Only": "केवल अस्पताल",
    "Facility Name or Keyword (Optional)": "ब्लड बैंक या अस्पताल का नाम (वैकल्पिक)",
    "e.g., District Hospital, Rotary Blood Bank": "जैसे: ज़िला अस्पताल, रोटरी ब्लड बैंक",
    "Use My GPS Location": "मेरा GPS स्थान उपयोग करें",
    "Locating...": "स्थान खोजा जा रहा है...",
    "GPS Active": "GPS सक्रिय",
    "Search Nearby": "पास में खोजें",
    "Searching...": "खोज हो रही है...",
    "Search Directory": "सूची में खोजें",
    "Facility Name or Address": "ब्लड बैंक का नाम या पता",
    "Verified Partner Hospitals": "सत्यापित भागीदार अस्पताल",
    "Platform-verified hospitals indicate reviewed licensing documentation only; live stock is still confirmed directly at the blood bank.": "सत्यापित अस्पताल बैज केवल लाइसेंस दस्तावेज़ जांच दर्शाता है; लाइव ब्लड स्टॉक सीधे ब्लड बैंक से ही पता करें।",
    "Loading verified partner hospitals...": "सत्यापित अस्पताल लोड हो रहे हैं...",
    "No verified partner hospitals listed yet.": "अभी कोई सत्यापित भागीदार अस्पताल सूचीबद्ध नहीं है।",
    "Unable to load partner hospitals right now.": "अभी भागीदार अस्पताल लोड नहीं हो सके।",
    "No blood banks or hospitals loaded yet": "अभी कोई ब्लड बैंक या अस्पताल लोड नहीं हुआ",
    "Call Facility": "फ़ोन करें",
    "Google Maps Directions": "Google Maps रास्ता",
    "Find Contact on Google": "Google पर संपर्क खोजें",
    "e-RaktKosh Stock": "e-RaktKosh स्टॉक",
    "Website": "वेबसाइट",
    "Phone:": "फ़ोन:",
    "Email:": "ईमेल:",
    "Hours:": "समय:",
    "Log: Contacted": "दर्ज करें: संपर्क किया",
    "Confirmed Available": "उपलब्धता की पुष्टि हुई",
    "Unavailable": "अनुपलब्ध",
    "Contact attempt recorded for your request.": "आपके अनुरोध के लिए संपर्क प्रयास दर्ज किया गया।",
    "Blood Bank": "ब्लड बैंक",
    "Hospital": "अस्पताल",
    "Call facility / check e-RaktKosh for live units": "लाइव यूनिट के लिए कॉल करें या e-RaktKosh देखें",
    "Platform Verified": "प्लेटफ़ॉर्म सत्यापित",
    "Browser GPS is unavailable. Enter your city name instead.": "ब्राउज़र GPS उपलब्ध नहीं है। कृपया अपने शहर का नाम लिखें।",
    "Location permission denied. Enter your city name (e.g., Mathura) instead.": "स्थान की अनुमति नहीं मिली। कृपया शहर का नाम (जैसे मथुरा) लिखें।",

    /* Request Details & My Requests */
    "My Requests — LifeLink": "मेरे अनुरोध — LifeLink",
    "My Blood Requests": "मेरे रक्त अनुरोध",
    "Track request lifecycle status, donor responses, and escalation progress.": "अपने अनुरोध की स्थिति, रक्तदाताओं के उत्तर और खोज की प्रगति देखें।",
    "Create New Request": "नया अनुरोध बनाएं",
    "Loading your blood requests...": "आपके रक्त अनुरोध लोड हो रहे हैं...",
    "Open Tracking": "लाइव स्थिति खोलें",
    "Request Details — LifeLink": "अनुरोध विवरण — LifeLink",
    "Loading request details...": "अनुरोध का विवरण लोड हो रहा है...",
    "Share Safe Status Link": "सुरक्षित लिंक साझा करें",
    "Disable Link": "लिंक बंद करें",
    "Share via WhatsApp": "WhatsApp से भेजें",
    "Live Request Tracking": "लाइव अनुरोध स्थिति",
    "Auto-refreshes every 15 seconds · Private donor phone numbers hidden": "हर 15 सेकंड में स्वतः अपडेट · रक्तदाताओं के फ़ोन नंबर गुप्त हैं",
    "Hospital: Unconfirmed": "अस्पताल: अपुष्ट",
    "Refresh Now": "अभी ताज़ा करें",
    "Refreshing...": "ताज़ा हो रहा है...",
    "Donors Notified": "सूचित रक्तदाता",
    "Responses Received": "प्राप्त उत्तर",
    "Donors Interested": "इच्छुक रक्तदाता",
    "Last Status Update": "अंतिम स्थिति अपडेट",
    "Next Steps:": "अगले कदम:",
    "Request Information": "अनुरोध की जानकारी",
    "Hospital:": "अस्पताल:",
    "City / Area:": "शहर / इलाका:",
    "Units Requested:": "मांगी गई यूनिट:",
    "Urgency:": "आपातकाल:",
    "Escalation Stage:": "खोज चरण:",
    "Expires At:": "समाप्ति समय:",
    "Notes:": "नोट्स:",
    "of 5": "5 में से",
    "Stage": "चरण",
    "Recorded Status History": "स्थिति का पूरा इतिहास",
    "Prioritized Candidate Donors": "प्राथमिकता वाले संभावित रक्तदाता",
    "Potential matches only. Phone numbers and exact addresses remain hidden.": "केवल संभावित मिलान। फ़ोन नंबर और सटीक पता गुप्त रहता है।",
    "Donor Responses": "रक्तदाताओं के उत्तर",
    "Acceptance opens private communication but does not confirm donation completion.": "स्वीकृति केवल सुरक्षित चैट खोलती है, रक्तदान पूर्ण होना नहीं दर्शाती।",
    "No donor responses recorded yet.": "अभी तक किसी रक्तदाता का उत्तर नहीं आया है।",
    "No blood-bank contact attempts logged yet.": "अभी कोई ब्लड बैंक संपर्क दर्ज नहीं है।",
    "No external emergency coordinator assigned.": "कोई बाहरी समन्वयक नहीं जोड़ा गया है।",
    "Live Donor Arrival Map (Approximate Radius)": "रक्तदाता आगमन मानचित्र (अनुमानित दायरा)",
    "Shows an obfuscated ~1 km safety radius (like Swiggy/Zomato area circles) without exposing exact donor GPS coordinates.": "सटीक GPS दिखाए बिना केवल लगभग ~1 किमी का सुरक्षित दायरा दिखाता है।",
    "No active radius shared": "अभी कोई लाइव दायरा साझा नहीं",
    "When an accepted donor enables location sharing, their approximate ~1 km arrival zone appears here.": "जब स्वीकार करने वाला रक्तदाता लोकेशन चालू करेगा, उसका ~1 किमी क्षेत्र यहाँ दिखेगा।",
    "Actions": "कार्रवाई",
    "Find & Notify Donors": "रक्तदाता खोजें व सूचित करें",
    "Expand / Escalate Stage": "खोज का दायरा बढ़ाएं",
    "Blood Banks": "ब्लड बैंक",
    "Fulfilled via Blood Bank / Other": "ब्लड बैंक / अन्य माध्यम से पूरा हुआ",
    "Mark Fulfilled": "रक्त मिल गया (पूर्ण)",
    "Mark Unresolved": "अपूर्ण के रूप में दर्ज करें",
    "Cancel Request": "अनुरोध रद्द करें",
    "Emergency Coordinator Delegation": "आपातकालीन समन्वयक ज़िम्मेदारी",
    "Authorize a trusted registered user to monitor progress, log blood-bank outcomes, and chat with accepting donors for this request only. Access can be revoked anytime.": "किसी विश्वसनीय उपयोगकर्ता को इस अनुरोध की निगरानी, ब्लड बैंक संपर्क और चैट की अनुमति दें।",
    "Trusted user email or phone number": "विश्वसनीय उपयोगकर्ता का ईमेल या फ़ोन",
    "Authorize Coordinator": "समन्वयक को अनुमति दें",
    "Post Progress Update": "प्रगति अपडेट भेजें",
    "Revoke Access": "अनुमति हटाएं",
    "Open Private Chat": "सुरक्षित चैट खोलें",
    "Hospital & Blood-Bank Contact Log": "अस्पताल व ब्लड बैंक संपर्क लॉग",
    "Blood request cancelled and contacted donors notified.": "रक्त अनुरोध रद्द किया गया और रक्तदाताओं को सूचित किया गया।",
    "Request marked fulfilled.": "अनुरोध पूर्ण दर्ज किया गया।",
    "Coordinator invitation sent.": "समन्वयक को निमंत्रण भेजा गया।",
    "Coordinator access revoked.": "समन्वयक की अनुमति हटाई गई।",
    "Progress update recorded and requester notified.": "प्रगति अपडेट दर्ज हुआ और अनुरोधकर्ता को सूचित किया गया।",

    /* Incoming Requests & Donor Profile */
    "Incoming Donor Alerts — LifeLink": "आने वाले रक्त अनुरोध — LifeLink",
    "Incoming Blood Request Alerts": "आने वाले रक्त अनुरोध अलर्ट",
    "Requests matched to your donor profile. Accepting opens a private in-app chat without automatically sharing your phone number.": "आपकी रक्तदाता प्रोफ़ाइल से मेल खाने वाले अनुरोध। स्वीकार करने से बिना फ़ोन नंबर दिखे सुरक्षित चैट खुलती है।",
    "Aadhaar Verification Required Before Donating": "रक्तदान से पहले आधार सत्यापन आवश्यक",
    "Verify your 12-digit Aadhaar once before accepting a blood donation request.": "रक्तदान अनुरोध स्वीकार करने से पहले 12 अंकों का आधार सत्यापित करें।",
    "I consent to Aadhaar verification before donating blood.": "मैं रक्तदान से पहले आधार सत्यापन की सहमति देता/देती हूँ।",
    "Aadhaar verification when donating is currently turned OFF (pre-deployment mode).": "रक्तदान के समय आधार सत्यापन अभी बंद है (प्री-डिप्लॉयमेंट मोड)।",
    "Aadhaar verified for blood donation.": "रक्तदान के लिए आधार सत्यापित हो गया।",
    "Live Face Verification Required to Accept": "स्वीकार करने के लिए लाइव चेहरा सत्यापन आवश्यक",
    "Confirm you are the registered donor before accepting this blood request. Capture a live selfie or upload a front-facing photo.": "अनुरोध स्वीकार करने से पहले पुष्टि करें कि आप पंजीकृत रक्तदाता हैं। लाइव सेल्फी लें या स्पष्ट फोटो अपलोड करें।",
    "Mandatory Location Radius Sharing:": "अनिवार्य लोकेशन दायरा साझाकरण:",
    "Enabling browser location is required when accepting a blood request so the requester can see your approximate arrival zone (~1 km radius). Exact GPS coordinates are never stored or shared.": "अनुरोध स्वीकार करते समय ब्राउज़र लोकेशन चालू करना आवश्यक है ताकि ~1 किमी का अनुमानित आगमन दायरा दिख सके। सटीक GPS कभी साझा नहीं होता।",
    "Start Camera": "कैमरा चालू करें",
    "Capture Selfie & Confirm Help": "सेल्फी लें और मदद की पुष्टि करें",
    "Or enroll / test with a clear front-facing photo": "या सामने की स्पष्ट फोटो चुनें",
    "Verify Photo & Confirm Help": "फोटो जांचें और मदद की पुष्टि करें",
    "Cancel": "रद्द करें",
    "Loading incoming donor alerts...": "आने वाले रक्त अनुरोध लोड हो रहे हैं...",
    "No incoming blood request alerts": "अभी कोई रक्त अनुरोध अलर्ट नहीं है",
    "I CAN HELP": "मैं मदद कर सकता/सकती हूँ",
    "NOT AVAILABLE": "उपलब्ध नहीं हूँ",
    "Share: En Route": "स्थिति भेजें: रास्ते में हूँ",
    "Share: Nearby": "स्थिति भेजें: पास पहुँच गया",
    "Arrived at Hospital": "अस्पताल पहुँच गया",
    "Stop Sharing": "लोकेशन साझा करना बंद करें",
    "Live radius sharing stopped.": "लाइव दायरा साझा करना बंद किया गया।",

    "Donor Profile & Availability — LifeLink": "रक्तदाता प्रोफ़ाइल व उपलब्धता — LifeLink",
    "Donor Profile & Availability": "रक्तदाता प्रोफ़ाइल और उपलब्धता",
    "Manage your blood group, availability status, emergency alert preference, and donation history.": "अपना ब्लड ग्रुप, उपलब्धता, आपातकालीन अलर्ट पसंद और रक्तदान इतिहास संभालें।",
    "Availability Status": "उपलब्धता स्थिति",
    "Available now": "अभी उपलब्ध हूँ",
    "Available Now": "अभी उपलब्ध हूँ",
    "Available today": "आज उपलब्ध हूँ",
    "Available Today": "आज उपलब्ध हूँ",
    "Available on selected dates": "चुनी हुई तारीखों पर उपलब्ध",
    "Emergency requests only": "केवल गंभीर आपातकाल के लिए",
    "Emergency Only": "केवल आपातकाल",
    "Temporarily unavailable": "फिलहाल उपलब्ध नहीं हूँ",
    "Unavailable": "अनुपलब्ध",
    "Last Recorded Donation Date (Optional)": "पिछले रक्तदान की तारीख (वैकल्पिक)",
    "Preferred Contact Method": "संपर्क का पसंदीदा तरीका",
    "Opt in to receive emergency blood request notifications": "आपातकालीन रक्त अनुरोध सूचनाएं प्राप्त करें",
    "Save Donor Profile": "रक्तदाता प्रोफ़ाइल सहेजें",
    "Donor profile saved successfully.": "रक्तदाता प्रोफ़ाइल सफलतापूर्वक सहेजी गई।",
    "Self-declared availability controls outreach only and is never treated as medical eligibility.": "स्व-घोषित उपलब्धता केवल अलर्ट नियंत्रण के लिए है, इसे चिकित्सा पात्रता न मानें।",
    "Donor Availability Calendar & Quiet Hours": "उपलब्धता कैलेंडर और शांत समय",
    "Selected Available Dates (YYYY-MM-DD, comma-separated)": "उपलब्ध तारीखें (YYYY-MM-DD, कॉमा से अलग)",
    "Temporary Pause Until (Optional)": "अस्थायी विराम तक (वैकल्पिक)",
    "Save Availability Calendar": "उपलब्धता कैलेंडर सहेजें",
    "Availability calendar & quiet hours saved.": "उपलब्धता कैलेंडर और शांत समय सहेजा गया।",
    "Donor Trust & Reliability Indicators": "रक्तदाता भरोसा और विश्वसनीयता संकेत",
    "Verified checks are clearly separated from self-declared values. Declining a request carries zero penalty.": "सत्यापित और स्व-घोषित विवरण अलग दिखाए जाते हैं। अनुरोध अस्वीकार करने पर कोई दंड नहीं है।",
    "Save donor profile to view trust indicators.": "भरोसा संकेत देखने के लिए रक्तदाता प्रोफ़ाइल सहेजें।",
    "Face Identity Verification": "चेहरा पहचान सत्यापन",
    "Enroll your face once so live selfie checks confirm it is the registered donor accepting and donating — preventing impersonation.": "एक बार अपना चेहरा दर्ज करें ताकि लाइव सेल्फी से सही रक्तदाता की पुष्टि हो सके।",
    "Not Enrolled": "दर्ज नहीं है",
    "Face Enrolled": "चेहरा दर्ज है",
    "I consent to LifeLink extracting and storing my facial descriptor for donor anti-impersonation verification.": "मैं सुरक्षा जांच के लिए अपना चेहरा सत्यापन डेटा सहेजने की सहमति देता/देती हूँ।",
    "Capture & Enroll Face": "चेहरा स्कैन कर दर्ज करें",
    "Enroll Photo": "फोटो से चेहरा दर्ज करें",
    "Verify Photo": "फोटो जांचें",
    "Test Live Match": "लाइव मिलान जांचें",
    "Supporting Document Upload": "सहायक दस्तावेज़ अपलोड",
    "Upload a blood donor card, government photo ID, or blood-bank slip (PDF, PNG, JPG, WEBP · max 5 MB) for administrator verification.": "एडमिन सत्यापन के लिए रक्तदाता कार्ड, सरकारी पहचान पत्र या ब्लड बैंक पर्ची अपलोड करें (अधिकतम 5 MB)।",
    "Document Type": "दस्तावेज़ का प्रकार",
    "Blood Donor Card": "रक्तदाता कार्ड",
    "Government Photo ID": "सरकारी फोटो पहचान पत्र",
    "Blood Bank / Hospital Slip": "ब्लड बैंक / अस्पताल पर्ची",
    "Other Supporting Document": "अन्य सहायक दस्तावेज़",
    "Select Document": "दस्तावेज़ चुनें",
    "Upload Document for Review": "समीक्षा के लिए दस्तावेज़ अपलोड करें",
    "Uploading...": "अपलोड हो रहा है...",
    "Document uploaded and submitted for administrator review.": "दस्तावेज़ अपलोड कर समीक्षा के लिए भेजा गया।",
    "No verification documents submitted yet.": "अभी कोई सत्यापन दस्तावेज़ अपलोड नहीं हुआ है।",
    "Donation History Log & Reminders": "रक्तदान इतिहास व अनुस्मारक",
    "Save your donor profile to view your donation review advisory.": "रक्तदान अंतराल सलाह देखने के लिए प्रोफ़ाइल सहेजें।",
    "Record Successful Donation Today (3-Month Freeze)": "आज का सफल रक्तदान दर्ज करें (3 माह विश्राम)",
    "Send Availability Reminder": "उपलब्धता अनुस्मारक भेजें",
    "Add Self-Reported Donation": "पिछला रक्तदान जोड़ें",
    "Donation Date": "रक्तदान की तारीख",
    "Donation Type": "रक्तदान का प्रकार",
    "Whole Blood (90d guidance)": "संपूर्ण रक्त (90 दिन सलाह)",
    "Platelets (14d guidance)": "प्लेटलेट्स (14 दिन सलाह)",
    "Plasma (28d guidance)": "प्लाज़्मा (28 दिन सलाह)",
    "Double Red Cells (112d guidance)": "डबल रेड सेल्स (112 दिन सलाह)",
    "Self-reported donation record added.": "स्व-घोषित रक्तदान रिकॉर्ड जोड़ा गया।",
    "No multi-entry donation history records added yet.": "अभी कोई रक्तदान इतिहास रिकॉर्ड नहीं जुड़ा है।",
    "Voluntary Appreciation & Digital Card": "स्वैच्छिक सम्मान व डिजिटल कार्ड",
    "Non-competitive recognition only. Not an official medical or government certificate.": "यह केवल स्वैच्छिक सम्मान है, सरकारी या चिकित्सा प्रमाणपत्र नहीं।",
    "Allow my recognition summary to show publicly (first name + milestone)": "मेरा सम्मान सारांश सार्वजनिक रूप से दिखाने की अनुमति दें",
    "Save donor profile to view milestones.": "उपलब्धियां देखने के लिए प्रोफ़ाइल सहेजें।",

    /* Notifications, Messages, Assistant */
    "Notifications — LifeLink": "सूचनाएं — LifeLink",
    "Notifications": "सूचनाएं",
    "Real-time platform alerts, donor responses, and escalation updates.": "ताज़ा अनुरोध अलर्ट, रक्तदाता उत्तर और खोज स्थिति सूचनाएं।",
    "Mark All as Read": "सभी को पढ़ा हुआ चिह्नित करें",
    "Mark Read": "पढ़ा हुआ चिह्नित करें",
    "Read": "पढ़ा गया",
    "Unread": "नया",
    "Open Request": "अनुरोध खोलें",
    "Loading notifications...": "सूचनाएं लोड हो रही हैं...",
    "No notifications yet": "अभी कोई सूचना नहीं है",
    "Request alerts, donor acceptances/declines, and escalation updates will appear here.": "रक्त अनुरोध अलर्ट, रक्तदाता उत्तर और अपडेट यहाँ दिखेंगे।",

    "Private Messages — LifeLink": "निजी संदेश — LifeLink",
    "Private Chat & Mutual Consent": "निजी चैट और सहमति",
    "Conversations open only after donor acceptance. Phone numbers remain hidden unless both participants consent.": "चैट केवल रक्तदाता के स्वीकार करने पर खुलती है। दोनों की सहमति के बिना फ़ोन नंबर छिपा रहता है।",
    "Authorized Conversations": "अधिकृत बातचीत",
    "Select a conversation": "एक बातचीत चुनें",
    "Choose an authorized conversation on the left to exchange messages or manage contact sharing.": "संदेश भेजने या फ़ोन साझा करने के लिए बाईं ओर से बातचीत चुनें।",
    "Type a private coordination message...": "सुरक्षित समन्वय संदेश लिखें...",
    "Send": "भेजें",
    "Privacy & Contact Sharing": "गोपनीयता व संपर्क साझाकरण",
    "Agree to Share My Phone": "मेरा फ़ोन नंबर साझा करने की सहमति दें",
    "Withdraw Consent": "सहमति वापस लें",
    "Report": "शिकायत करें",
    "Block User": "उपयोगकर्ता ब्लॉक करें",
    "No conversations yet. Chats open automatically when a donor accepts a request.": "अभी कोई बातचीत नहीं है। रक्तदाता के अनुरोध स्वीकार करने पर चैट अपने आप खुलती है।",
    "No messages yet. Introduce yourself and coordinate hospital details safely.": "अभी कोई संदेश नहीं है। सुरक्षित रूप से अस्पताल का विवरण साझा करें।",
    "User blocked and conversation closed.": "उपयोगकर्ता ब्लॉक किया गया और बातचीत बंद की गई।",

    "LifeLink Assistant — LifeLink": "LifeLink सहायक — LifeLink",
    "LifeLink Assistant": "LifeLink सहायक",
    "Guided help for request preparation, live request tracking, privacy rules, and blood-bank resources.": "अनुरोध तैयारी, लाइव ट्रैकिंग, गोपनीयता नियम और ब्लड बैंक खोज के लिए सहायता।",
    "Rule-Based Platform Guide": "नियम-आधारित मंच मार्गदर्शक",
    "The LifeLink Assistant uses rule-based platform workflows and is not a medical professional.": "LifeLink सहायक केवल मंच की जानकारी देता है, यह डॉक्टर या चिकित्सा सलाहकार नहीं है।",
    "Prepare Request (B+ Mathura)": "अनुरोध तैयार करें (B+ मथुरा)",
    "Track My Request": "मेरा अनुरोध ट्रैक करें",
    "Emergency Guidance": "आपातकालीन मार्गदर्शन",
    "Privacy Protection": "गोपनीयता सुरक्षा",
    "Blood-Bank Help": "ब्लड बैंक मदद",
    "Ask about tracking your request, creating a request, privacy, or blood banks...": "अनुरोध, ट्रैकिंग, गोपनीयता या ब्लड बैंक के बारे में पूछें...",
    "Ask": "पूछें",

    /* Shared Request, Hospital Portal, Admin, Static Pages */
    "Shared Blood Request Status — LifeLink": "साझा रक्त अनुरोध स्थिति — LifeLink",
    "Public Shared Request View": "सार्वजनिक साझा अनुरोध स्थिति",
    "Shared publicly without exposing private phone numbers, documents, or personal conversations.": "फ़ोन नंबर, दस्तावेज़ या निजी चैट दिखाए बिना साझा की गई स्थिति।",
    "Loading shared request status...": "साझा अनुरोध स्थिति लोड हो रही है...",
    "Sign In to Respond": "उत्तर देने के लिए लॉगिन करें",
    "Able to donate safely via a licensed hospital blood bank? Register or log in to respond directly.": "क्या आप लाइसेंस प्राप्त ब्लड बैंक के माध्यम से रक्तदान कर सकते हैं? लॉगिन या पंजीकरण करें।",
    "Register as Donor": "रक्तदाता के रूप में जुड़ें",
    "Report Suspicious Shared Request": "संदिग्ध अनुरोध की रिपोर्ट करें",
    "Reason (e.g., Requesting money or suspicious details)": "कारण लिखें (जैसे: पैसे की मांग या गलत जानकारी)",
    "Submit Safety Report": "सुरक्षा रिपोर्ट भेजें",

    "Hospital Verification & Coordination Portal — LifeLink": "अस्पताल सत्यापन व समन्वय पोर्टल — LifeLink",
    "Hospital Coordination Portal": "अस्पताल समन्वय पोर्टल",
    "Hospital Registration": "अस्पताल पंजीकरण",
    "Licensed Facility Name": "लाइसेंस प्राप्त अस्पताल का नाम",
    "Registration / License Number": "पंजीकरण / लाइसेंस संख्या",
    "Hospital Address": "अस्पताल का पूरा पता",
    "Official Contact Phone": "अधिकारिक संपर्क फ़ोन",
    "Official Email (Optional)": "अधिकारिक ईमेल (वैकल्पिक)",
    "Authorized Representative Name": "अधिकृत प्रतिनिधि का नाम",
    "Representative Designation": "प्रतिनिधि का पद",
    "Save Hospital Registration": "अस्पताल पंजीकरण सहेजें",
    "Aadhaar Verification Required for Hospital Staff": "अस्पताल स्टाफ़ के लिए आधार सत्यापन आवश्यक",
    "Verify the authorized representative's 12-digit Aadhaar before submitting hospital registration.": "अस्पताल पंजीकरण से पहले अधिकृत प्रतिनिधि का 12 अंकों का आधार सत्यापित करें।",
    "I consent to Aadhaar verification as the hospital's authorized representative.": "मैं अस्पताल के अधिकृत प्रतिनिधि के रूप में आधार सत्यापन की सहमति देता/देती हूँ।",
    "Verify Staff Aadhaar": "स्टाफ़ आधार सत्यापित करें",
    "Licensing & Verification Documents": "लाइसेंस व सत्यापन दस्तावेज़",
    "Upload hospital registration certificate, Blood Centre license, or official authorization letter (PDF, PNG, JPG, WEBP, max 5 MB).": "अस्पताल पंजीकरण प्रमाणपत्र, ब्लड सेंटर लाइसेंस या प्राधिकरण पत्र अपलोड करें (अधिकतम 5 MB)।",
    "Hospital Registration Certificate": "अस्पताल पंजीकरण प्रमाणपत्र",
    "Licensed Blood Centre Permit": "ब्लड सेंटर लाइसेंस परमिट",
    "Authorized Representative Letter": "अधिकृत प्रतिनिधि पत्र",
    "Select Document File": "दस्तावेज़ फ़ाइल चुनें",
    "Upload Hospital Document": "अस्पताल दस्तावेज़ अपलोड करें",
    "Verification Audit History": "सत्यापन जांच इतिहास",
    "Facility Blood Requests (Verified Hospitals Only)": "अस्पताल के रक्त अनुरोध (केवल सत्यापित अस्पताल)",
    "Refresh Requests": "अनुरोध ताज़ा करें",
    "Hospital registration submitted for administrator review.": "अस्पताल पंजीकरण एडमिन समीक्षा के लिए भेजा गया।",
    "Hospital representative Aadhaar verified.": "अस्पताल प्रतिनिधि का आधार सत्यापित हो गया।",
    "Hospital verification document uploaded.": "अस्पताल सत्यापन दस्तावेज़ अपलोड हुआ।",

    "Admin Console — LifeLink": "एडमिन कंसोल — LifeLink",
    "Administrator Console": "एडमिनिस्ट्रेटर कंसोल",
    "Platform Overview, Moderation & Analytics": "प्लेटफ़ॉर्म अवलोकन, मॉडरेशन और विश्लेषण",
    "Platform Analytics": "प्लेटफ़ॉर्म आंकड़े",
    "Real database-backed counts only.": "केवल वास्तविक डेटाबेस आंकड़े।",
    "External Integrations Readiness": "बाहरी API एकीकरण स्थिति",
    "User Management": "उपयोगकर्ता प्रबंधन",
    "Filter": "फ़िल्टर करें",
    "All roles": "सभी भूमिकाएं",
    "Donor Document Reviews": "रक्तदाता दस्तावेज़ समीक्षा",
    "Hospital Verification & Audit Queue": "अस्पताल सत्यापन कतार",
    "Blood Requests Moderation": "रक्त अनुरोध मॉडरेशन",
    "Add Verified Blood-Bank Entry": "सत्यापित ब्लड बैंक जोड़ें",
    "Add Blood Bank": "ब्लड बैंक जोड़ें",
    "Reports & Safety Moderation": "शिकायतें और सुरक्षा समीक्षा",
    "Verify": "सत्यापित करें",
    "Reject": "अस्वीकार करें",
    "Suspend": "निलंबित करें",
    "Resolve": "हल करें",
    "Dismiss": "खारिज करें",
    "Delete": "हटाएं",
    "View File": "फ़ाइल देखें",

    /* How It Works, About, Privacy, Terms */
    "How It Works — LifeLink": "कैसे काम करता है — LifeLink",
    "How LifeLink Coordinates Blood Emergencies": "LifeLink रक्त आपातकाल का समन्वय कैसे करता है",
    "1. End-to-End Request Lifecycle": "1. रक्त अनुरोध की पूरी प्रक्रिया",
    "2. Five-Stage Progressive Escalation": "2. पांच-चरणीय खोज विस्तार प्रणाली",
    "Stage 1 — Nearby Potential Donors:": "चरण 1 — नज़दीकी संभावित रक्तदाता:",
    "Stage 2 — Additional Nearby Candidates:": "चरण 2 — अतिरिक्त नज़दीकी रक्तदाता:",
    "Stage 3 — Wider Search Radius:": "चरण 3 — विस्तृत क्षेत्र में खोज:",
    "Stage 4 — Blood-Bank Assistance:": "चरण 4 — ब्लड बैंक सहायता:",
    "Stage 5 — Hospital-Coordinated Search:": "चरण 5 — अस्पताल-समन्वित व्यापक खोज:",
    "Clinical & Operational Boundaries": "चिकित्सीय व संचालन सीमाएं",
    "Why LifeLink Exists": "LifeLink क्यों बनाया गया",
    "Safety & Privacy Commitments": "सुरक्षा व गोपनीयता प्रतिबद्धताएं",
    "Privacy Policy — LifeLink": "गोपनीयता नीति — LifeLink",
    "What Data We Collect:": "हम कौन-सा डेटा लेते हैं:",
    "Why We Collect It:": "हम इसे क्यों लेते हैं:",
    "Terms & Conditions — LifeLink": "नियम व शर्तें — LifeLink",
    "Medical Safety Disclaimer:": "चिकित्सीय सुरक्षा अस्वीकरण:",
    "Critical Safety Rule:": "महत्वपूर्ण सुरक्षा नियम:",
    "No Medical Advice or Guarantee:": "कोई चिकित्सा सलाह या गारंटी नहीं:",
    "Hospital First:": "अस्पताल को प्राथमिकता:",
    "Address": "पता",
    "Blood Bank Medical Officer": "ब्लड बैंक चिकित्सा अधिकारी",
    "Coordinator progress update (e.g., Called district blood bank counter)": "समन्वयक प्रगति अपडेट (जैसे: ज़िला ब्लड बैंक काउंटर पर बात हुई)",
    "District Blood Centre": "ज़िला ब्लड सेंटर",
    "Dr. A. Verma": "डॉ. ए. वर्मा",
    "Facility Name": "सुविधा / अस्पताल का नाम",
    "Full hospital address": "अस्पताल का पूरा पता",
    "Optional details for platform moderators": "मॉडरेटर के लिए अतिरिक्त जानकारी (वैकल्पिक)",
    "Phone": "फ़ोन",
    "Search name, email, city": "नाम, ईमेल या शहर खोजें",
    "Source (e.g., Official District Directory)": "स्रोत (जैसे: सरकारी ज़िला निर्देशिका)",
    "e.g., 2026-11-28, 2026-11-30": "जैसे: 2026-11-28, 2026-11-30",
    "e.g., UP-MED-2026-104": "जैसे: UP-MED-2026-104",
    "A verified hospital badge indicates LifeLink reviewed submitted hospital registration credentials. It does not guarantee live blood stock or clinical decisions.": "सत्यापित अस्पताल बैज केवल दर्शाता है कि LifeLink ने पंजीकरण दस्तावेज़ों की समीक्षा की है। यह लाइव स्टॉक या चिकित्सा निर्णय की गारंटी नहीं देता।",
    "Aadhaar": "आधार",
    "Aadhaar Status": "आधार स्थिति",
    "Access & Retention:": "पहुंच व डेटा संरक्षण:",
    "Access is limited to requests linked to your verified hospital facility.": "पहुंच केवल आपके सत्यापित अस्पताल से जुड़े अनुरोधों तक सीमित है।",
    "Access is restricted via backend role authorization and Supabase Row Level Security (RLS). Users can request account deactivation or deletion through profile settings or administrators.": "डेटा सुरक्षा भूमिका-आधारित जांच और RLS नीति से सुरक्षित है। उपयोगकर्ता प्रोफ़ाइल या एडमिन से खाता बंद करने का अनुरोध कर सकते हैं।",
    "Account Conduct:": "खाता आचरण:",
    "Account Verification:": "खाता सत्यापन:",
    "Action": "कार्रवाई",
    "Admin": "एडमिन",
    "All blood donation, screening, crossmatching, and transfusion procedures must occur through licensed blood centres and qualified medical professionals.": "सभी रक्तदान, जांच, क्रॉसमैच और रक्ताधान केवल लाइसेंस प्राप्त ब्लड सेंटर और योग्य डॉक्टरों द्वारा ही होने चाहिए।",
    "Approximate Area Only:": "केवल अनुमानित क्षेत्र:",
    "Authorized Blood Collection:": "अधिकृत रक्त संग्रह:",
    "Authorized Private Chat:": "अधिकृत निजी चैट:",
    "Broaden geographical scope using configurable city/distance rules.": "शहर और दूरी नियमों के अनुसार खोज क्षेत्र का विस्तार करें।",
    "Candidate donors are ranked by availability, proximity, and verification.": "रक्तदाताओं को उपलब्धता, नज़दीकी और सत्यापन के आधार पर क्रम में रखा जाता है।",
    "Candidates are prioritized using transparent rules: availability status, city/proximity, verification state, and notification opt-in. Final eligibility rests with the blood bank.": "रक्तदाताओं को पारदर्शी नियमों (उपलब्धता, शहर, सत्यापन और अलर्ट सहमति) से प्राथमिकता मिलती है। अंतिम पात्रता ब्लड बैंक तय करता है।",
    "Checking consent...": "सहमति जांची जा रही है...",
    "Configuration-gated status for external APIs. Unconfigured gateways remain disabled honestly.": "बाहरी API एकीकरण स्थिति। बिना सेट किए गए गेटवे निष्क्रिय रहते हैं।",
    "Designed to replace scattered social forwards and unverified calls with structured coordination.": "बिखरे हुए सोशल फॉरवर्ड और अनियोजित कॉल की जगह सुव्यवस्थित समन्वय के लिए बनाया गया।",
    "Donor": "रक्तदाता",
    "Donor Settings": "रक्तदाता सेटिंग्स",
    "During blood emergencies, families often rely on fragmented phone calls, WhatsApp forwards, and social media posts. This causes uncertain donor availability, uncoordinated follow-ups, and public exposure of personal phone numbers.": "रक्त आपातकाल में परिवारों को अक्सर बिखरे कॉल, WhatsApp फॉरवर्ड और सोशल मीडिया पर निर्भर रहना पड़ता है, जिससे गलत जानकारी व फ़ोन नंबर सार्वजनिक होने का जोखिम रहता है।",
    "Email": "ईमेल",
    "Emergency Coordination Status": "आपातकालीन समन्वय स्थिति",
    "Emergency Medical Notice:": "आपातकालीन चिकित्सा सूचना:",
    "Expand to more matching candidates if responses are insufficient.": "पर्याप्त उत्तर न मिलने पर अधिक योग्य रक्तदाताओं तक पहुंचें।",
    "Final blood compatibility and donor medical eligibility are determined solely by licensed blood centres.": "अंतिम रक्त मिलान और रक्तदान पात्रता केवल लाइसेंस प्राप्त ब्लड सेंटर ही तय करते हैं।",
    "Guide immediate contact with the treating hospital blood bank and licensed centres while keeping the request tracked as unresolved.": "अनुरोध को ट्रैक करते हुए तुरंत अस्पताल के ब्लड बैंक और लाइसेंस प्राप्त केंद्रों से संपर्क कराएं।",
    "Honest Escalation Workflow": "ईमानदार चरणबद्ध सहायता प्रक्रिया",
    "Hospital Fallback": "अस्पताल व ब्लड बैंक सहायता",
    "Hospital Verification & Request Oversight": "अस्पताल सत्यापन व अनुरोध निगरानी",
    "In-app chat opens only after donor acceptance; phone sharing requires mutual consent.": "ऐप चैट केवल रक्तदाता के स्वीकार करने पर खुलती है; फ़ोन नंबर साझा करने के लिए दोनों की सहमति ज़रूरी है।",
    "Licensed Screening:": "लाइसेंस प्राप्त जांच:",
    "LifeLink Assistant is a rule-based platform assistant, not a medical professional. It cannot diagnose conditions, determine donor eligibility, or replace hospital emergency care.": "LifeLink सहायक नियम-आधारित मार्गदर्शक है, डॉक्टर नहीं। यह बीमारी की जांच या अस्पताल आपात सेवा की जगह नहीं ले सकता।",
    "LifeLink brings donor prioritization, multi-donor alerts, progressive escalation, privacy-preserving chat, blood-bank discovery, and guided assistance into a single platform.": "LifeLink रक्तदाता प्राथमिकता, बहु-रक्तदाता अलर्ट, चरणबद्ध खोज, निजी चैट, ब्लड बैंक सूची और मार्गदर्शन को एक मंच पर लाता है।",
    "LifeLink is a coordination tool. It does not guarantee blood availability, replace licensed blood banks, or determine donor medical eligibility.": "LifeLink केवल एक समन्वय मंच है। यह रक्त उपलब्धता की गारंटी नहीं देता और न ही ब्लड बैंक या चिकित्सा जांच का विकल्प है।",
    "Location & Contact Privacy:": "स्थान व संपर्क गोपनीयता:",
    "Medical Disclaimer: LifeLink does not guarantee blood availability, determine donor medical eligibility, or replace licensed blood centres and hospital transfusion services.": "चिकित्सा अस्वीकरण: LifeLink रक्त उपलब्धता की गारंटी नहीं देता और न ही लाइसेंस प्राप्त ब्लड सेंटर व अस्पताल सेवाओं का विकल्प है।",
    "Multi-Donor Alerts:": "बहु-रक्तदाता अलर्ट:",
    "Multiple eligible candidates receive notifications with": "कई योग्य रक्तदाताओं को इन विकल्पों के साथ सूचना भेजी जाती है:",
    "Name": "नाम",
    "Name, email, phone number, city, approximate location, optional date of birth, blood group (for donors), and blood-request coordination records.": "नाम, ईमेल, फ़ोन नंबर, शहर, अनुमानित स्थान, वैकल्पिक जन्मतिथि, ब्लड ग्रुप और रक्त अनुरोध समन्वय विवरण।",
    "Never delay urgent medical care while waiting for donor matching or software escalation. Always coordinate immediately with your treating hospital's transfusion service.": "रक्तदाता मिलान की प्रतीक्षा में कभी भी तुरंत इलाज में देरी न करें। हमेशा अस्पताल की रक्त सेवा से सीधे संपर्क करें।",
    "Never shown publicly.": "कभी सार्वजनिक नहीं दिखाया जाता।",
    "No file selected.": "कोई फ़ाइल नहीं चुनी गई।",
    "Not Submitted": "जमा नहीं हुआ",
    "Not created": "नहीं बना",
    "Notify the closest suitable candidates first.": "सबसे नज़दीकी और उपयुक्त रक्तदाताओं को पहले सूचित करें।",
    "Only your city and general area are used for preliminary coordination.": "प्रारंभिक समन्वय के लिए केवल आपका शहर और सामान्य क्षेत्र उपयोग होता है।",
    "Optional Phone Sharing:": "वैकल्पिक फ़ोन साझाकरण:",
    "Outcome Recording:": "परिणाम दर्ज करना:",
    "Platform donor profiles and verification badges indicate account verification only. Final compatibility, health screening, and donation eligibility are determined exclusively by licensed blood banks and healthcare professionals.": "प्लेटफ़ॉर्म बैज केवल खाते का सत्यापन दर्शाते हैं। अंतिम जांच और रक्तदान पात्रता केवल ब्लड बैंक और डॉक्टर तय करते हैं।",
    "Preliminary Match Only:": "केवल प्रारंभिक मिलान:",
    "Privacy-First Communication": "गोपनीयता-प्रथम संवाद",
    "Privacy-Safe Share Link:": "सुरक्षित साझा लिंक:",
    "Public donor search shows only city and approximate location. Phone numbers are never returned in public search APIs and are only revealed if both requester and donor give explicit mutual consent.": "सार्वजनिक खोज में केवल शहर और अनुमानित क्षेत्र दिखता है। फ़ोन नंबर केवल दोनों पक्षों की स्पष्ट सहमति से ही साझा होता है।",
    "Register & Verify:": "पंजीकरण व सत्यापन:",
    "Registered Phone (Private)": "पंजीकृत फ़ोन (निजी)",
    "Request": "अनुरोध",
    "Requester": "अनुरोधकर्ता",
    "Requester specifies required blood group, units, hospital, city, and urgency.": "अनुरोधकर्ता आवश्यक ब्लड ग्रुप, यूनिट, अस्पताल, शहर और आपातकाल दर्ज करता है।",
    "Requests remain active or unresolved until genuine fulfilment, cancellation, or expiry is recorded.": "अनुरोध तब तक सक्रिय रहते हैं जब तक वास्तविक पूर्ति, रद्दीकरण या समाप्ति दर्ज न हो।",
    "Review submitted hospital registrations, inspect licensing files, and maintain audit decisions.": "जमा किए गए अस्पताल पंजीकरण व लाइसेंस फ़ाइलों की समीक्षा करें।",
    "Role": "भूमिका",
    "Rule-Based Prioritization:": "नियम-आधारित प्राथमिकता:",
    "Rule-Based Priority": "नियम-आधारित प्राथमिकता",
    "Selecting Urgent or Emergency prioritizes platform alerts but does": "अति आवश्यक या आपातकालीन चुनने से अलर्ट तेज़ जाते हैं, लेकिन यह",
    "Self-reported entries remain clearly tagged until confirmed by a facility. Final donation intervals depend on donation type and healthcare screening.": "स्व-घोषित विवरण अस्पताल की पुष्टि तक अलग दिखते हैं। अंतिम रक्तदान अंतराल चिकित्सा जांच पर निर्भर करता है।",
    "Status": "स्थिति",
    "Strictly to coordinate emergency blood-donor matching, notifications, authorized in-app communication, and platform safety moderation.": "केवल आपातकालीन रक्तदाता मिलान, सूचनाओं, सुरक्षित चैट और प्लेटफ़ॉर्म सुरक्षा के लिए।",
    "Submit Request:": "अनुरोध भेजें:",
    "Submitting false emergency requests, harassing users, or attempting unauthorized access will result in account suspension.": "झूठे अनुरोध भेजने, परेशान करने या अनधिकृत पहुंच का प्रयास करने पर खाता निलंबित कर दिया जाएगा।",
    "Surface verified directory listings and official resources such as e-RaktKosh.": "सत्यापित ब्लड बैंक सूची और e-RaktKosh जैसे सरकारी संसाधन दिखाएं।",
    "Track direct calls and availability confirmations with licensed blood centres.": "लाइसेंस प्राप्त ब्लड केंद्रों से की गई कॉल और पुष्टि का रिकॉर्ड रखें।",
    "Transparent Donor Matching": "पारदर्शी रक्तदाता मिलान",
    "Users must never delay urgent hospital treatment while waiting for donor matching or escalation.": "रक्तदाता मिलान की प्रतीक्षा में उपयोगकर्ता कभी भी तुरंत अस्पताल इलाज में देरी न करें।",
    "Users register as a Requester or Donor and verify their phone number.": "उपयोगकर्ता अनुरोधकर्ता या रक्तदाता के रूप में पंजीकरण कर अपना फ़ोन सत्यापित करते हैं।",
    "Verification & Review Status": "सत्यापन और समीक्षा स्थिति",
    "Verification Badge Notice:": "सत्यापन बैज सूचना:",
    "Verification Status": "सत्यापन स्थिति",
    "Verified hospitals can confirm request genuineness, update requirements, and close fulfilled or no-longer-needed requests.": "सत्यापित अस्पताल अनुरोध की सत्यता की पुष्टि कर सकते हैं और पूरे हुए अनुरोध बंद कर सकते हैं।",
    "Verifying administrator authorization...": "एडमिन अनुमति जांची जा रही है...",
    "View Escalation Protocol": "चरणबद्ध प्रक्रिया देखें",
    "Waiting for donor": "रक्तदाता की प्रतीक्षा",
    "When donor responses are insufficient, LifeLink escalates to wider search and verified blood-bank directory resources without fabricating stock availability.": "पर्याप्त उत्तर न मिलने पर LifeLink खोज का दायरा बढ़ाता है और झूठा स्टॉक दिखाए बिना सत्यापित ब्लड बैंक दिखाता है।",
    "Workflow & Safety Model": "कार्यप्रणाली और सुरक्षा मॉडल",
    "You can update your availability at any time.": "आप अपनी उपलब्धता कभी भी बदल सकते हैं।",
    "Your account is protected with role-based authorization and location privacy controls.": "आपका खाता भूमिका-आधारित सुरक्षा और स्थान गोपनीयता से सुरक्षित है।",
    "Your phone number is never visible in public donor searches.": "आपका फ़ोन नंबर सार्वजनिक खोज में कभी नहीं दिखता।",
    "actions.": "विकल्प।",
    "and": "और",
    "constitute medical verification. Contact the treating hospital or licensed blood bank immediately and never delay urgent care while waiting for donor responses.": "चिकित्सीय सत्यापन माना जाता। तुरंत अस्पताल या लाइसेंस प्राप्त ब्लड बैंक से संपर्क करें और इलाज में देरी न करें।",
    "not": "नहीं",
    "or": "या",
    "Forgot Password? Use Backup Recovery Code": "पासवर्ड भूल गए? बैकअप रिकवरी कोड से लॉगिन करें",
    "Recover Account Password": "खाते का पासवर्ड रीसेट करें",
    "Enter any one of your 6 single-use Instagram-style backup codes saved when you registered (each code works once), or request a reset email.": "पंजीकरण के समय मिले 6 बैकअप कोड में से कोई एक कोड डालें (हर कोड केवल एक बार काम करता है), या रीसेट ईमेल मांगें।",
    "One-Time Backup Recovery Code": "एक-बार उपयोग होने वाला रिकवरी कोड",
    "e.g., ABCD-1234": "जैसे: ABCD-1234",
    "New Password (minimum 8 characters)": "नया पासवर्ड (कम से कम 8 अक्षर)",
    "Enter new password": "नया पासवर्ड लिखें",
    "Reset Password & Sign In": "पासवर्ड बदलें और लॉगिन करें",
    "Resetting...": "बदला जा रहा है...",
    "Send Reset Email": "रीसेट ईमेल भेजें",
    "Account Created": "खाता बन गया",
    "Save Your 6 Backup Recovery Codes": "अपने 6 बैकअप रिकवरी कोड सुरक्षित सहेजें",
    "Keep these one-time Instagram-style codes somewhere safe (screenshot, notes, or download). If you ever forget your password, any unused code lets you reset it immediately.": "इन 6 गुप्त कोड को सुरक्षित जगह सहेजें (स्क्रीनशॉट या डाउनलोड करें)। पासवर्ड भूलने पर इनमें से कोई भी कोड तुरंत नया पासवर्ड सेट कर देगा।",
    "Copy All Codes": "सभी कोड कॉपी करें",
    "Copied!": "कॉपी हो गया!",
    "Download (.txt)": "डाउनलोड करें (.txt)",
    "Saved — Continue to Dashboard": "सहेज लिया — डैशबोर्ड पर जाएं",
    "Account Backup & Recovery Codes (Like Instagram)": "खाता बैकअप व रिकवरी कोड (Instagram जैसा)",
    "One-time secret codes let you reset your password and sign back in safely even without email OTP.": "एक-बार वाले गुप्त कोड से आप बिना ईमेल OTP के भी पासवर्ड भूलने पर सुरक्षित लॉगिन कर सकते हैं।",
    "Checking backup recovery codes...": "बैकअप रिकवरी कोड जांचे जा रहे हैं...",
    "Generate New Recovery Codes": "नए 6 रिकवरी कोड बनाएं",
    "Copy Codes": "कोड कॉपी करें",
    "New backup recovery codes generated. Save them safely!": "नए बैकअप रिकवरी कोड बन गए हैं। इन्हें सुरक्षित सहेजें!",
    "Backup codes copied to clipboard.": "बैकअप कोड कॉपी हो गए।",
    "🔊 Listen / सुनें": "🔊 सुनें",
  };

  function translateDynamicPattern(text) {
    let m;
    if ((m = text.match(/^Showing (\d+) facility result\(s\)(.*)$/i))) {
      const rest = m[2]
        .replace("Sources:", "स्रोत:")
        .replace("No external source matched", "कोई बाहरी स्रोत नहीं मिला")
        .replace("Sorted by your GPS location", "आपके GPS स्थान के अनुसार क्रमबद्ध");
      return `${m[1]} सुविधा परिणाम दिख रहे हैं${rest}`;
    }
    if ((m = text.match(/^([0-9.]+) km away$/i))) {
      return `${m[1]} किमी दूर`;
    }
    if ((m = text.match(/^Hospital:\s*(.+)$/i))) {
      const st = m[1] === "Unconfirmed" ? "अपुष्ट" : m[1];
      return `अस्पताल: ${st}`;
    }
    if ((m = text.match(/^Auto-refreshes every 15 seconds · Last checked (.+) · Private donor phone numbers hidden$/i))) {
      return `हर 15 सेकंड में स्वतः अपडेट · अंतिम जांच ${m[1]} · रक्तदाताओं के फ़ोन नंबर गुप्त`;
    }
    if ((m = text.match(/^Stage (\d+) of 5$/i))) {
      return `चरण ${m[1]} (5 में से)`;
    }
    if ((m = text.match(/^Request ID:\s*(.+)$/i))) {
      return `अनुरोध ID: ${m[1]}`;
    }
    if ((m = text.match(/^Current Status:\s*(.+)$/i))) {
      return `वर्तमान स्थिति: ${m[1]}`;
    }
    if ((m = text.match(/^Donors Notified Immediately:\s*(\d+)\s+eligible donor\(s\) alerted$/i))) {
      return `तुरंत सूचित रक्तदाता: ${m[1]} योग्य रक्तदाता को अलर्ट भेजा गया`;
    }
    if ((m = text.match(/^Donated by (.+)$/i))) {
      return `रक्तदान: ${m[1]}`;
    }
    if ((m = text.match(/^Aadhaar verified \((.+)\) for blood donation\.$/i))) {
      return `रक्तदान के लिए आधार सत्यापित (${m[1]})।`;
    }
    if ((m = text.match(/^©\s*\d{4}\s*LifeLink\s*·\s*Team LogicLoom\./i))) {
      return "© 2026 LifeLink · टीम LogicLoom। यह केवल समन्वय माध्यम है — आपातकालीन अस्पताल इलाज में कभी देरी न करें।";
    }
    return null;
  }

  const origTextMap = new WeakMap();
  const origPlaceholderMap = new WeakMap();
  let mainObserver = null;
  let isTranslatingDom = false;
  let origDocTitle = "";

  function translateTree(root, lang) {
    if (!root || isTranslatingDom) return;
    isTranslatingDom = true;
    try {
      if (!origDocTitle && document.title) {
        origDocTitle = document.title;
      }
      if (origDocTitle) {
        document.title = lang === "hi" ? (PHRASEBOOK_HI[origDocTitle] || origDocTitle) : origDocTitle;
      }

      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const parent = node.parentElement;
        const parentTag = parent ? parent.tagName : "";
        if (parentTag === "SCRIPT" || parentTag === "STYLE" || parentTag === "CODE") continue;
        if (parent && (parent.classList.contains("lang-pill-btn") || parent.closest("[data-no-i18n]"))) continue;
        const raw = node.nodeValue || "";
        const normalized = raw.replace(/\s+/g, " ").trim();
        if (!normalized) continue;

        if (!origTextMap.has(node)) {
          if (PHRASEBOOK_HI[normalized] || translateDynamicPattern(normalized)) {
            origTextMap.set(node, normalized);
          }
        }
        const orig = origTextMap.get(node);
        if (orig) {
          const target = lang === "hi" ? (PHRASEBOOK_HI[orig] || translateDynamicPattern(orig) || orig) : orig;
          if (normalized !== target) {
            const lead = (raw.match(/^\s*/) || [""])[0];
            const trail = (raw.match(/\s*$/) || [""])[0];
            node.nodeValue = `${lead}${target}${trail}`;
          }
        }
      }

      root.querySelectorAll("input[placeholder], textarea[placeholder]").forEach((el) => {
        const ph = (el.getAttribute("placeholder") || "").replace(/\s+/g, " ").trim();
        if (!origPlaceholderMap.has(el) && PHRASEBOOK_HI[ph]) {
          origPlaceholderMap.set(el, ph);
        }
        const origPh = origPlaceholderMap.get(el);
        if (origPh) {
          el.setAttribute("placeholder", lang === "hi" ? (PHRASEBOOK_HI[origPh] || origPh) : origPh);
        }
      });
    } finally {
      isTranslatingDom = false;
    }
  }

  function speakPageSummary() {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      window.alert("Voice playback is not supported in this browser.");
      return;
    }
    const lang = getLanguage();
    window.speechSynthesis.cancel();
    const h1 = document.querySelector("main h1")?.textContent?.trim() || "LifeLink";
    const sub = document.querySelector("main p")?.textContent?.trim() || "";
    const notice = document.querySelector(".alert-warning, .alert-info")?.textContent?.trim() || "";
    const speechText = `${h1}. ${sub}. ${notice}`.slice(0, 450);
    const utter = new SpeechSynthesisUtterance(speechText);
    utter.lang = lang === "hi" ? "hi-IN" : "en-IN";
    utter.rate = 0.92;
    window.speechSynthesis.speak(utter);
  }

  function applyLanguageToDom(lang) {
    const dict = TRANSLATIONS[lang] || TRANSLATIONS.en;
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (dict[key]) el.textContent = dict[key];
    });
    translateTree(document.body, lang);
    document.querySelectorAll(".lang-pill-btn").forEach((btn) => {
      btn.setAttribute("aria-pressed", String(btn.dataset.lang === lang));
    });
  }

  function setLanguage(next) {
    const valid = next === "hi" ? "hi" : "en";
    localStorage.setItem("lifelink_lang", valid);
    applyLanguageToDom(valid);
    persistPreferences({ preferred_language: valid });
  }

  async function persistPreferences(updates) {
    if (LifeLinkAPI.getToken()) {
      try {
        await LifeLinkAPI.request("/api/users/me/preferences", {
          method: "PATCH",
          body: JSON.stringify(updates),
        });
      } catch {
        /* ignore offline preference sync failure */
      }
    }
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  function showAlert(containerId, message, type = "info") {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.className = `alert alert-${type}`;
    el.textContent = message;
    el.classList.remove("hidden");
  }

  function clearAlert(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.textContent = "";
    el.classList.add("hidden");
  }

  function statusBadgeClass(status) {
    const s = String(status || "").toLowerCase();
    if (["fulfilled", "verified", "accepted", "available_now", "both_consented"].includes(s)) return "badge-success";
    if (["cancelled", "expired", "rejected", "declined", "unresolved", "blocked"].includes(s)) return "badge-red";
    if (["emergency", "escalation_in_progress", "blood_bank_assistance", "pending_review", "urgent"].includes(s)) return "badge-warning";
    return "badge-neutral";
  }

  function formatLabel(value) {
    return String(value || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function renderLayout(activeNavKey) {
    applyAccessibilityFromStorage();
    const lang = getLanguage();
    const dict = TRANSLATIONS[lang] || TRANSLATIONS.en;
    const textSize = localStorage.getItem("lifelink_a11y_text") || "normal";
    const highContrast = localStorage.getItem("lifelink_a11y_contrast") === "1";

    const user = LifeLinkAPI.getStoredUser();
    const hasToken = Boolean(LifeLinkAPI.getToken());
    const role = hasToken && user ? user.role : "public";

    const headerTarget = document.getElementById("site-header-mount");
    const footerTarget = document.getElementById("site-footer-mount");

    let navItems = [];
    if (role === "admin") {
      navItems = [
        { key: "admin", label: "Admin Console", href: "/pages/admin.html" },
        { key: "find-donors", label: "Find Donors", href: "/pages/find-donors.html" },
        { key: "blood-banks", label: "Blood Banks", href: "/pages/blood-banks.html" },
        { key: "dashboard", label: "Profile", href: "/pages/dashboard.html" },
      ];
    } else if (role === "hospital") {
      navItems = [
        { key: "hospital-portal", label: "Hospital Portal", href: "/pages/hospital-portal.html" },
        { key: "blood-banks", label: "Blood Banks", href: "/pages/blood-banks.html" },
        { key: "dashboard", label: "Account", href: "/pages/dashboard.html" },
      ];
    } else if (role === "requester" || role === "donor") {
      navItems = [
        { key: "create-request", label: "Request Blood Now", href: "/pages/create-request.html?quick=1", cta: true },
        { key: "dashboard", label: "Dashboard", href: "/pages/dashboard.html" },
        { key: "my-requests", label: "My Requests", href: "/pages/my-requests.html" },
        { key: "incoming-requests", label: "Incoming Alerts", href: "/pages/incoming-requests.html" },
        { key: "donor-profile", label: "Donor Profile", href: "/pages/donor-profile.html" },
        { key: "notifications", label: "Notifications", href: "/pages/notifications.html" },
        { key: "messages", label: "Messages", href: "/pages/messages.html" },
        { key: "assistant", label: "Assistant", href: "/pages/assistant.html" },
        { key: "blood-banks", label: "Blood Banks", href: "/pages/blood-banks.html" },
      ];
    } else {
      navItems = [
        { key: "home", label: "Home", href: "/index.html" },
        { key: "how-it-works", label: "How It Works", href: "/pages/how-it-works.html" },
        { key: "find-donors", label: "Find Donors", href: "/pages/find-donors.html" },
        { key: "blood-banks", label: "Blood Banks", href: "/pages/blood-banks.html" },
        { key: "about", label: "About", href: "/pages/about.html" },
        { key: "login", label: "Login", href: "/pages/login.html" },
        { key: "register", label: "Request Blood Now", href: "/pages/create-request.html?quick=1", cta: true },
      ];
    }

    if (headerTarget) {
      const linksHtml = navItems
        .map((item) => {
          const classes = [];
          if (item.key === activeNavKey) classes.push("active");
          if (item.cta) classes.push("nav-cta");
          const i18nKey = `nav_${item.key.replace(/-/g, "_")}`;
          const text = dict[i18nKey] || item.label;
          return `<li><a href="${item.href}" class="${classes.join(" ")}" data-i18n="${i18nKey}">${escapeHtml(text)}</a></li>`;
        })
        .join("");

      const logoutItem =
        role !== "public"
          ? `<li><button type="button" id="nav-logout-btn" class="nav-link-btn" data-i18n="logout">${escapeHtml(dict.logout)}</button></li>`
          : "";

      headerTarget.innerHTML = `
        <a href="#main-content" class="skip-link">Skip to main content</a>
        <div class="safety-strip">
          <div class="container">
            <span data-i18n="emergency_notice">${escapeHtml(dict.emergency_notice)}</span>
            <div class="a11y-toolbar" aria-label="Language and accessibility settings">
              <div class="lang-pill-group" role="group" aria-label="Quick language switch">
                <button type="button" class="lang-pill-btn" data-lang="en" aria-pressed="${lang === "en"}">English</button>
                <button type="button" class="lang-pill-btn" data-lang="hi" aria-pressed="${lang === "hi"}">हिन्दी</button>
              </div>
              <button type="button" id="a11y-speak-btn" class="a11y-btn" title="Listen to page guide">&#128266; सुनें</button>
              <button type="button" class="a11y-btn a11y-size-btn" data-size="normal" aria-pressed="${textSize === "normal"}" title="Standard text size">A</button>
              <button type="button" class="a11y-btn a11y-size-btn" data-size="large" aria-pressed="${textSize === "large"}" title="Large text size">A+</button>
              <button type="button" class="a11y-btn a11y-size-btn" data-size="xlarge" aria-pressed="${textSize === "xlarge"}" title="Extra large text size">A++</button>
              <button type="button" id="a11y-contrast-btn" class="a11y-btn" aria-pressed="${highContrast}">Contrast</button>
            </div>
          </div>
        </div>
        <header class="site-header">
          <div class="container nav-bar">
            <a class="brand" href="/index.html">
              <span class="brand-mark" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 2.5C12 2.5 5 10.2 5 15a7 7 0 0 0 14 0c0-4.8-7-12.5-7-12.5z"/>
                </svg>
              </span>
              <span>
                LifeLink
                <span class="brand-sub" data-i18n="brand_sub">${escapeHtml(dict.brand_sub)}</span>
              </span>
            </a>
            <button type="button" class="nav-toggle" id="nav-toggle-btn" aria-label="Toggle navigation">Menu</button>
            <ul class="nav-links" id="main-nav-links">
              ${linksHtml}
              ${logoutItem}
            </ul>
          </div>
        </header>
      `;

      const mainEl = document.querySelector("main");
      if (mainEl && !mainEl.id) mainEl.id = "main-content";

      document.querySelectorAll(".lang-pill-btn").forEach((btn) => {
        btn.addEventListener("click", () => setLanguage(btn.dataset.lang || "en"));
      });

      document.getElementById("a11y-speak-btn")?.addEventListener("click", speakPageSummary);

      document.querySelectorAll(".a11y-size-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const next = btn.dataset.size || "normal";
          localStorage.setItem("lifelink_a11y_text", next);
          applyAccessibilityFromStorage();
          document.querySelectorAll(".a11y-size-btn").forEach((b) => {
            b.setAttribute("aria-pressed", String(b.dataset.size === next));
          });
          persistPreferences({ text_size: next });
        });
      });

      const contrastBtn = document.getElementById("a11y-contrast-btn");
      if (contrastBtn) {
        contrastBtn.addEventListener("click", () => {
          const next = !(localStorage.getItem("lifelink_a11y_contrast") === "1");
          localStorage.setItem("lifelink_a11y_contrast", next ? "1" : "0");
          applyAccessibilityFromStorage();
          contrastBtn.setAttribute("aria-pressed", String(next));
          persistPreferences({ high_contrast: next });
        });
      }

      const toggleBtn = document.getElementById("nav-toggle-btn");
      const navList = document.getElementById("main-nav-links");
      if (toggleBtn && navList) {
        toggleBtn.addEventListener("click", () => navList.classList.toggle("open"));
      }
      const logoutBtn = document.getElementById("nav-logout-btn");
      if (logoutBtn) {
        logoutBtn.addEventListener("click", () => LifeLinkAuth.logout());
      }
    }

    if (footerTarget) {
      footerTarget.innerHTML = `
        <footer class="site-footer">
          <div class="container">
            <div class="footer-grid">
              <div>
                <strong>LifeLink — Smart Blood Donor Matching &amp; Emergency Response System</strong>
                <p style="margin-top: 8px;">
                  Built by Team LogicLoom, GL Bajaj Group of Institutions, Mathura.
                  LifeLink does not guarantee blood availability or determine medical eligibility;
                  clinical screening and crossmatching are handled solely by licensed blood centres.
                </p>
              </div>
              <div>
                <strong>Platform</strong>
                <ul class="footer-links">
                  <li><a href="/pages/how-it-works.html">How It Works</a></li>
                  <li><a href="/pages/find-donors.html">Find Donors</a></li>
                  <li><a href="/pages/blood-banks.html">Blood-Bank Directory</a></li>
                  <li><a href="/pages/about.html">About LifeLink</a></li>
                </ul>
              </div>
              <div>
                <strong>Privacy &amp; Safety</strong>
                <ul class="footer-links">
                  <li><a href="/pages/privacy.html">Privacy Policy</a></li>
                  <li><a href="/pages/terms.html">Terms &amp; Conditions</a></li>
                  <li><a href="/docs" target="_blank" rel="noopener">API Documentation</a></li>
                </ul>
              </div>
            </div>
            <div style="border-top: 1px solid var(--border); padding-top: 14px; font-size: 0.82rem;">
              &copy; ${new Date().getFullYear()} LifeLink &middot; Team LogicLoom. Coordination tool only &mdash; never delay urgent hospital care.
            </div>
          </div>
        </footer>
      `;
    }

    applyLanguageToDom(lang);
    if (mainObserver) mainObserver.disconnect();
    mainObserver = new MutationObserver(() => {
      if (getLanguage() !== "en") translateTree(document.body, getLanguage());
    });
    mainObserver.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  return {
    escapeHtml,
    showAlert,
    clearAlert,
    statusBadgeClass,
    formatLabel,
    renderLayout,
    speakPageSummary,
    setLanguage,
  };
})();
