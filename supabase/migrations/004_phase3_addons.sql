-- =============================================================================
-- LifeLink: Phase 3 Add-On Extensions (Trust Profile, Donation History & Referrals)
-- Run in Supabase SQL Editor AFTER 003_phase2_addons.sql
-- =============================================================================

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS referral_code TEXT UNIQUE,
    ADD COLUMN IF NOT EXISTS referred_by_user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL;

ALTER TABLE public.donor_profiles
    ADD COLUMN IF NOT EXISTS recognition_public BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS public.donation_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    donor_id UUID NOT NULL REFERENCES public.donor_profiles(id) ON DELETE CASCADE,
    donation_date DATE NOT NULL,
    donation_type TEXT NOT NULL DEFAULT 'whole_blood'
        CHECK (donation_type IN ('whole_blood', 'platelets', 'plasma', 'double_red_cells')),
    facility_name TEXT NOT NULL DEFAULT 'Licensed Blood Centre',
    evidence_status TEXT NOT NULL DEFAULT 'self_reported'
        CHECK (evidence_status IN ('self_reported', 'verified_by_facility')),
    supporting_document_id UUID REFERENCES public.donor_documents(id) ON DELETE SET NULL,
    notes TEXT,
    is_corrected BOOLEAN NOT NULL DEFAULT FALSE,
    correction_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_donation_records_donor ON public.donation_records(donor_id, donation_date DESC);

CREATE TRIGGER trg_donation_records_updated_at
    BEFORE UPDATE ON public.donation_records
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS public.referral_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    referred_user_id UUID NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
    referral_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'registered' CHECK (status IN ('registered')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_referral_records_referrer ON public.referral_records(referrer_user_id, created_at DESC);
