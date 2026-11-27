-- =============================================================================
-- LifeLink: Phase 2 Add-On Extensions (UX, Language/Accessibility, Calendar, Family & Share Links)
-- Run in Supabase SQL Editor AFTER 002_phase1_addons.sql
-- =============================================================================

-- 1. User language & accessibility preferences
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS preferred_language TEXT NOT NULL DEFAULT 'en' CHECK (preferred_language IN ('en', 'hi')),
    ADD COLUMN IF NOT EXISTS accessibility_prefs JSONB NOT NULL DEFAULT '{"text_size": "normal", "high_contrast": false}'::jsonb;

-- 2. Donor availability calendar & notification preferences
ALTER TABLE public.donor_profiles
    DROP CONSTRAINT IF EXISTS donor_profiles_availability_status_check;
ALTER TABLE public.donor_profiles
    ADD CONSTRAINT donor_profiles_availability_status_check
    CHECK (availability_status IN ('available_now', 'available_today', 'available_selected_dates', 'unavailable', 'emergency_only'));

ALTER TABLE public.donor_profiles
    ADD COLUMN IF NOT EXISTS last_availability_updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.donor_availability (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    donor_id UUID NOT NULL UNIQUE REFERENCES public.donor_profiles(id) ON DELETE CASCADE,
    available_dates JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_distance_km INTEGER NOT NULL DEFAULT 25 CHECK (preferred_distance_km BETWEEN 1 AND 250),
    quiet_hours_start TEXT,
    quiet_hours_end TEXT,
    paused_until DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_donor_availability_updated_at
    BEFORE UPDATE ON public.donor_availability
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS public.user_notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
    in_app_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    quiet_hours_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    emergency_override_quiet_hours BOOLEAN NOT NULL DEFAULT TRUE,
    reminder_frequency_days INTEGER NOT NULL DEFAULT 30,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Family Emergency Accounts & On-Behalf-Of Request Attribution
CREATE TABLE IF NOT EXISTS public.emergency_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    member_user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    can_create_requests BOOLEAN NOT NULL DEFAULT TRUE,
    can_manage_requests BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'declined', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_user_id, member_user_id)
);

CREATE INDEX IF NOT EXISTS idx_emergency_contacts_member ON public.emergency_contacts(member_user_id, status);

ALTER TABLE public.blood_requests
    ADD COLUMN IF NOT EXISTS created_by_user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL;

-- 4. Sanitized Public Request Share Links
CREATE TABLE IF NOT EXISTS public.request_share_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL UNIQUE REFERENCES public.blood_requests(id) ON DELETE CASCADE,
    share_token TEXT NOT NULL UNIQUE,
    created_by UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_share_links_token ON public.request_share_links(share_token);
