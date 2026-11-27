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
    "Built for Safety, Privacy, and Accountability": "सुरक्षा, गोपनीयता और भरोसे के लिए बनाया गया",
    "Sign in to LifeLink": "LifeLink में लॉगिन करें",
    "Email Address or Phone Number": "ईमेल या फ़ोन नंबर",
    "Password": "पासवर्ड",
    "Sign In": "लॉगिन करें",
    "Register here": "यहाँ पंजीकरण करें",
    "Register on LifeLink": "LifeLink पर नया खाता बनाएं",
    "Full Name": "पूरा नाम",
    "Email Address": "ईमेल पता",
    "Phone Number": "फ़ोन नंबर",
    "Date of Birth": "जन्म तिथि",
    "City": "शहर",
    "General / Approximate Location": "क्षेत्र / नज़दीकी इलाका (घर का सटीक पता न लिखें)",
    "Account Role": "खाते की भूमिका",
    "Blood Group (Donor)": "ब्लड ग्रुप (रक्तदाता)",
    "Authenticate Aadhaar": "आधार सत्यापित करें",
    "Create Verified Account": "सत्यापित खाता बनाएं",
    "Patient / Ward Reference Name": "मरीज़ या वार्ड का नाम",
    "Required Blood Group": "ज़रूरी ब्लड ग्रुप",
    "Select blood group": "ब्लड ग्रुप चुनें",
    "Units Needed": "कितनी यूनिट चाहिए",
    "Urgency Level": "आपातकाल स्तर",
    "Hospital Name": "अस्पताल का नाम",
    "Hospital Location / Area": "अस्पताल का इलाका",
    "Approximate Location / Sector": "नज़दीकी सेक्टर या पहचान",
    "Required Date & Time": "कब तक रक्त चाहिए (तारीख व समय)",
    "Contact Preference": "संपर्क का तरीका",
    "Review Request Before Submitting": "भेजने से पहले विवरण जांचें",
    "Submit Blood Request": "रक्त अनुरोध भेजें",
    "Confirm & Submit Request": "पुष्टि करें और भेजें",
    "Edit Details": "विवरण बदलें",
    "Find Potential Donors": "संभावित रक्तदाता खोजें",
    "Blood Group": "ब्लड ग्रुप",
    "All blood groups": "सभी ब्लड ग्रुप",
    "Search Candidates": "रक्तदाता खोजें",
    "Blood-Bank Directory & Official Fallback": "ब्लड बैंक सूची व सरकारी पोर्टल",
    "Search Directory": "सूची में खोजें",
    "Facility Name or Address": "ब्लड बैंक का नाम या पता",
    "Donor Profile & Availability": "रक्तदाता प्रोफ़ाइल और उपलब्धता",
    "Save Donor Profile": "रक्तदाता प्रोफ़ाइल सहेजें",
    "Available now": "अभी उपलब्ध हूँ",
    "Available today": "आज उपलब्ध हूँ",
    "Available on selected dates": "चुनी हुई तारीखों पर उपलब्ध",
    "Emergency requests only": "केवल गंभीर आपातकाल के लिए",
    "Temporarily unavailable": "फिलहाल उपलब्ध नहीं हूँ",
    "Incoming Blood Request Alerts": "आने वाले रक्त अनुरोध अलर्ट",
    "Live Request Tracking": "लाइव अनुरोध स्थिति",
    "Refresh Now": "अभी ताज़ा करें",
    "Find & Notify Donors": "रक्तदाता खोजें व सूचित करें",
    "Expand / Escalate Stage": "खोज का दायरा बढ़ाएं",
    "Blood Banks": "ब्लड बैंक",
    "Mark Fulfilled": "रक्त मिल गया (पूर्ण)",
    "Cancel Request": "अनुरोध रद्द करें",
    "Open Private Chat": "सुरक्षित चैट खोलें",
    "My Requests": "मेरे रक्त अनुरोध",
    "Profile & Location Settings": "प्रोफ़ाइल और स्थान सेटिंग्स",
    "Save Profile Updates": "बदलाव सहेजें",
    "Emergency Coordinator Assignments": "आपातकालीन समन्वयक ज़िम्मेदारियां",
    "Family Emergency Account": "परिवार आपातकालीन खाता",
    "Authorize Family Member": "परिवार के सदस्य को अनुमति दें",
    "Community Referral & Awareness": "मित्रों को जोड़ें (रेफ़रल)",
  };

  const origTextMap = new WeakMap();
  const origPlaceholderMap = new WeakMap();
  let mainObserver = null;
  let isTranslatingDom = false;

  function translateTree(root, lang) {
    if (!root || isTranslatingDom) return;
    isTranslatingDom = true;
    try {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const parentTag = node.parentElement ? node.parentElement.tagName : "";
        if (parentTag === "SCRIPT" || parentTag === "STYLE" || parentTag === "CODE") continue;
        const raw = node.nodeValue || "";
        const trimmed = raw.trim();
        if (!trimmed) continue;
        if (!origTextMap.has(node)) {
          if (PHRASEBOOK_HI[trimmed]) {
            origTextMap.set(node, trimmed);
          }
        }
        const orig = origTextMap.get(node);
        if (orig) {
          const target = lang === "hi" ? (PHRASEBOOK_HI[orig] || orig) : orig;
          if (trimmed !== target) {
            node.nodeValue = raw.replace(trimmed, target);
          }
        }
      }

      root.querySelectorAll("input[placeholder], textarea[placeholder]").forEach((el) => {
        const ph = el.getAttribute("placeholder") || "";
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
    utter.lang = lang === "hi" ? "hi-IN" : lang === "mr" ? "mr-IN" : lang === "bn" ? "bn-IN" : lang === "ta" ? "ta-IN" : "en-IN";
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
    const mainEl = document.querySelector("main");
    if (mainEl) translateTree(mainEl, lang);
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

      if (mainEl) {
        applyLanguageToDom(lang);
        if (mainObserver) mainObserver.disconnect();
        mainObserver = new MutationObserver(() => {
          if (getLanguage() !== "en") translateTree(mainEl, getLanguage());
        });
        mainObserver.observe(mainEl, { childList: true, subtree: true });
      }

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
