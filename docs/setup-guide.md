# LifeLink Setup & Configuration Guide

## 1. Required External Services & Credentials

| Service | Purpose | Required in Local Dev? | Required in Production? |
| --- | --- | --- | --- |
| **Supabase Project** | PostgreSQL database, Auth, Realtime, Storage, RLS | Optional (uses safe local SQLite dev DB when unset & `DEV_AUTH_MODE=true`) | **Yes** (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`) |
| **SMS Provider (via Supabase Auth)** | Real Phone OTP verification (Twilio / Vonage / MessageBird) | Optional (Dev mode shows clear warning and dev-only verification button) | **Yes** for phone OTP (`SUPABASE_PHONE_OTP_ENABLED=true`) |
| **Maps / Geocoding API** | Optional coordinate lookup for approximate locations | No (manual city/location entry supported) | Optional |
| **Official Blood-Bank Directory (e-RaktKosh)** | Official blood-bank verification & stock links | No (directory search + official portal links work) | Optional if API access is granted |

---

## 2. Setting Up Supabase

1. Create a free project at [supabase.com](https://supabase.com).
2. In **SQL Editor**, run the SQL scripts in order:
   - `supabase/migrations/001_initial_schema.sql`
   - `supabase/policies/001_rls_policies.sql`
   - *(Optional)* `supabase/seed.sql` (contains setup notes; does not insert fake donors or fake stock).
3. In **Authentication -> Providers**, enable Email/Password and (if SMS provider configured) Phone OTP.
4. Copy your Project URL, `anon` public key, `service_role` secret key, and JWT Secret from **Project Settings -> API** into `.env`.
5. Never place `SUPABASE_SERVICE_ROLE_KEY` in `frontend/`.

---

## 3. Running Locally (Windows / PowerShell)

```powershell
# 1. Copy environment template
Copy-Item .env.example .env

# 2. Create and activate virtual environment inside backend
python -m venv backend\.venv

# 3. Install dependencies
backend\.venv\Scripts\pip install -r backend\requirements.txt

# 4. Run the FastAPI server (serves both API and frontend)
backend\.venv\Scripts\uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser and `http://127.0.0.1:8000/docs` for Swagger API docs.

---

## 4. Creating an Administrator Account

For security, users **cannot** register as `admin` from the public registration page or modify their own role via API requests.

To promote an existing verified user to administrator:
- **Supabase:** Run in SQL Editor:
  ```sql
  UPDATE public.profiles SET role = 'admin' WHERE email = 'admin@example.com';
  ```
- **Local Dev Mode:** Run the CLI helper script:
  ```powershell
  backend\.venv\Scripts\python -m backend.app.cli create-admin --email admin@example.com
  ```

## 5. Optional Google Drive Direct Upload for Verification Documents

The configured Google Drive folder URL is stored in `.env` (`GOOGLE_DRIVE_FOLDER_URL`). To enable automatic server-to-Drive uploads:

1. Create a Google Cloud Service Account with the Google Drive API enabled and download its JSON key file.
2. Share the Google Drive folder (`1zi9cOxgHIYbzP18VU8Af9ZGMrFK7kwC3`) with the Service Account's `client_email` as **Editor**.
3. Set `GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE=path\to\service-account.json` in `.env`.
4. Without a Service Account key, uploaded files remain stored privately on disk (`backend/uploads/donor_documents/`) or Supabase Storage (`donor-documents` bucket) and are accessible to admins via the Admin Console.

