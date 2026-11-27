-- =============================================================================
-- LifeLink: Phase 1 Add-On Extensions (Essential Usability & Coordination Core)
-- Run in Supabase SQL Editor AFTER 001_initial_schema.sql
-- =============================================================================

-- 1. Allow 'hospital' account role in profiles (never self-assign 'admin')
ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_role_check;
ALTER TABLE public.profiles ADD CONSTRAINT profiles_role_check
    CHECK (role IN ('requester', 'donor', 'hospital', 'admin'));

-- 2. Hospitals & Verification Workflow
CREATE TABLE IF NOT EXISTS public.hospitals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
    hospital_name TEXT NOT NULL CHECK (char_length(trim(hospital_name)) >= 2),
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
    verified_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hospitals_status_city ON public.hospitals(verification_status, lower(city));

CREATE TRIGGER trg_hospitals_updated_at
    BEFORE UPDATE ON public.hospitals
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS public.hospital_verification_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id UUID NOT NULL REFERENCES public.hospitals(id) ON DELETE CASCADE,
    document_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (review_status IN ('pending_review', 'verified', 'rejected')),
    reviewed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_hospital_docs_updated_at
    BEFORE UPDATE ON public.hospital_verification_documents
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS public.hospital_verification_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id UUID NOT NULL REFERENCES public.hospitals(id) ON DELETE CASCADE,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    actor_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hospital_ver_history ON public.hospital_verification_history(hospital_id, created_at);

-- 3. Extend blood_requests for quick emergency, coordinator notes, hospital verification & cancel reason
ALTER TABLE public.blood_requests
    ADD COLUMN IF NOT EXISTS is_emergency_quick BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS coordinator_contact_name TEXT,
    ADD COLUMN IF NOT EXISTS coordinator_contact_relation TEXT,
    ADD COLUMN IF NOT EXISTS hospital_id UUID REFERENCES public.hospitals(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS hospital_verification_status TEXT NOT NULL DEFAULT 'unconfirmed'
        CHECK (hospital_verification_status IN ('unconfirmed', 'confirmed_genuine', 'hospital_updated', 'flagged_invalid')),
    ADD COLUMN IF NOT EXISTS hospital_confirmed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS hospital_confirmed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_blood_requests_hospital ON public.blood_requests(hospital_id);

-- 4. Scoped Per-Request Emergency Coordinators
CREATE TABLE IF NOT EXISTS public.request_coordinators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES public.blood_requests(id) ON DELETE CASCADE,
    requester_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    coordinator_user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'invited'
        CHECK (status IN ('invited', 'active', 'declined', 'revoked')),
    can_chat BOOLEAN NOT NULL DEFAULT TRUE,
    can_contact_blood_banks BOOLEAN NOT NULL DEFAULT TRUE,
    can_update_progress BOOLEAN NOT NULL DEFAULT TRUE,
    invited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id, coordinator_user_id)
);

CREATE INDEX IF NOT EXISTS idx_request_coordinators_user ON public.request_coordinators(coordinator_user_id, status);
CREATE INDEX IF NOT EXISTS idx_request_coordinators_req ON public.request_coordinators(request_id, status);

CREATE TRIGGER trg_request_coordinators_updated_at
    BEFORE UPDATE ON public.request_coordinators
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 5. Blood-Bank Availability Labels & Stock Updates History
ALTER TABLE public.blood_banks DROP CONSTRAINT IF EXISTS blood_banks_availability_status_check;
ALTER TABLE public.blood_banks ADD CONSTRAINT blood_banks_availability_status_check
    CHECK (availability_status IN (
        'directory_listing_only',
        'availability_not_available',
        'contact_required',
        'availability_confirmed_by_facility',
        'availability_unavailable',
        'information_outdated',
        'confirmed_available',
        'reported_awaiting_confirmation',
        'availability_unknown',
        'currently_unavailable'
    ));

CREATE TABLE IF NOT EXISTS public.blood_bank_stock_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blood_bank_id UUID NOT NULL REFERENCES public.blood_banks(id) ON DELETE CASCADE,
    blood_group TEXT NOT NULL CHECK (blood_group IN ('ALL', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    availability_status TEXT NOT NULL CHECK (availability_status IN (
        'confirmed_available',
        'reported_awaiting_confirmation',
        'availability_unknown',
        'currently_unavailable',
        'information_outdated'
    )),
    notes TEXT,
    updated_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bb_stock_updates_bank ON public.blood_bank_stock_updates(blood_bank_id, updated_at DESC);
