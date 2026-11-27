# LifeLink — Smart Blood Donor Matching & Emergency Response System

**Team:** LogicLoom  
**Institution:** GL Bajaj Group of Institutions, Mathura  
**Domain:** Healthcare Technology / Emergency Response / Digital Blood Donation

> *"Most platforms help people find donors. LifeLink is designed to help coordinate the emergency response."*

## Implemented Modules (Phases 1–8 Complete)

- **Authentication & Role-Based Security:** Registration (`requester` / `donor`), login, phone OTP hooks + clearly labelled local development verification, PBKDF2 password hashing, JWT validation, rate limiting, security headers, and backend-enforced `admin` authorization.
- **Donor & Blood Request Management:** Donor availability (`available_now`, `available_today`, `emergency_only`, `unavailable`), donation history review advisories, supporting document submission, blood request creation, duplicate prevention, auto-expiry, cancellation, and full status timeline.
- **Rule-Based Matching & 5-Stage Progressive Escalation:** Transparent candidate prioritization, multi-donor alerts (`I CAN HELP` / `NOT AVAILABLE`), automatic no-candidate fallback, and 5-stage escalation through Blood-Bank Assistance and Hospital-Coordinated Wider Search.
- **Private Communication & Consent Sharing:** Request-specific private chat unlocked only on donor acceptance, third-party access isolation (`403`), mutual-consent phone sharing (never automatic), withdrawal support, user blocking, and reporting.
- **Rule-Based LifeLink Assistant:** Guided request preparation (never silently submits), live database-backed request tracking, emergency hospital-first guidance, privacy FAQs, and medical safety guardrails.
- **Blood-Bank Directory & Admin Console:** Directory search with distance/directions & e-RaktKosh portal link, contact-attempt logging, genuine outcome recording (`fulfilled` / `unresolved`), and full admin moderation, document verification, blood-bank CRUD, analytics, and audit logs.

## Quick Start (Local Development)

```powershell
# 1. Copy environment template
Copy-Item .env.example .env

# 2. Create virtual environment and install dependencies
python -m venv backend\.venv
backend\.venv\Scripts\pip install -r backend\requirements.txt

# 3. Run the entire automated test suite (Phases 1-8)
backend\.venv\Scripts\python -m pytest -v

# 4. Start the web application & FastAPI backend
backend\.venv\Scripts\uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:
- Web Application: `http://127.0.0.1:8000`
- Swagger API Docs: `http://127.0.0.1:8000/docs`

## Creating an Admin Account for Local Demonstration

1. Register a normal account at `/pages/register.html` (e.g., `admin@lifelink.local`).
2. Promote that account via the backend CLI:
   ```powershell
   backend\.venv\Scripts\python -m backend.app.cli create-admin --email admin@lifelink.local
   ```
3. Sign in at `/pages/login.html` to access `/pages/admin.html`.

## Documentation

- [Architecture & ER Diagram](docs/architecture.md)
- [API Documentation](docs/api-documentation.md)
- [Setup & Supabase Guide](docs/setup-guide.md)

## Important Medical & Safety Notice

LifeLink is a coordination platform only. It does **not** determine medical eligibility, crossmatching, or blood safety, and cannot guarantee blood availability. In an immediate medical emergency, contact the treating hospital and its licensed blood bank directly.
