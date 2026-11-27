-- =============================================================================
-- LifeLink: Initial PostgreSQL Schema for Supabase
-- Run in Supabase SQL Editor before applying 001_rls_policies.sql
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Shared updated_at trigger function
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- 1. profiles (Application user accounts linked to Supabase auth.users)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL CHECK (char_length(trim(full_name)) >= 2),
    email TEXT UNIQUE,
    phone_number TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'requester' CHECK (role IN ('requester', 'donor', 'admin')),
    city TEXT NOT NULL,
    approximate_location TEXT NOT NULL,
    date_of_birth DATE,
    account_status TEXT NOT NULL DEFAULT 'active' CHECK (account_status IN ('active', 'suspended', 'deleted')),
    phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
    aadhaar_last4 TEXT NOT NULL CHECK (char_length(aadhaar_last4) = 4),
    aadhaar_hash TEXT NOT NULL UNIQUE,
    aadhaar_verified BOOLEAN NOT NULL DEFAULT FALSE,
    aadhaar_consent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    terms_accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profiles_role ON public.profiles(role);
CREATE INDEX IF NOT EXISTS idx_profiles_city ON public.profiles(lower(city));
CREATE INDEX IF NOT EXISTS idx_profiles_auth_user_id ON public.profiles(auth_user_id);

CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Prevent non-service-role clients from elevating their own role or status
CREATE OR REPLACE FUNCTION public.prevent_self_privilege_escalation()
RETURNS TRIGGER AS $$
BEGIN
    IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'service_role' THEN
        IF NEW.role IS DISTINCT FROM OLD.role THEN
            RAISE EXCEPTION 'Changing user role is restricted to administrators.';
        END IF;
        IF NEW.account_status IS DISTINCT FROM OLD.account_status THEN
            RAISE EXCEPTION 'Changing account status is restricted to administrators.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_profiles_prevent_escalation
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.prevent_self_privilege_escalation();

-- -----------------------------------------------------------------------------
-- 2. donor_profiles
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.donor_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
    blood_group TEXT NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    availability_status TEXT NOT NULL DEFAULT 'unavailable'
        CHECK (availability_status IN ('available_now', 'available_today', 'unavailable', 'emergency_only')),
    last_donation_date DATE,
    donor_frozen_until DATE,
    donor_freeze_reason TEXT,
    preferred_contact_method TEXT NOT NULL DEFAULT 'in_app_chat'
        CHECK (preferred_contact_method IN ('in_app_chat', 'consent_phone')),
    verification_status TEXT NOT NULL DEFAULT 'not_submitted'
        CHECK (verification_status IN ('not_submitted', 'pending_review', 'verified', 'rejected')),
    emergency_notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    profile_completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_donor_profiles_blood_group ON public.donor_profiles(blood_group);
CREATE INDEX IF NOT EXISTS idx_donor_profiles_availability ON public.donor_profiles(availability_status);
CREATE INDEX IF NOT EXISTS idx_donor_profiles_verification ON public.donor_profiles(verification_status);

CREATE TRIGGER trg_donor_profiles_updated_at
    BEFORE UPDATE ON public.donor_profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- -----------------------------------------------------------------------------
-- 3. blood_requests
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.blood_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    patient_reference_name TEXT NOT NULL,
    blood_group TEXT NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    units_requested INTEGER NOT NULL DEFAULT 1 CHECK (units_requested BETWEEN 1 AND 20),
    hospital_name TEXT NOT NULL,
    hospital_location TEXT NOT NULL,
    city TEXT NOT NULL,
    approximate_location TEXT NOT NULL,
    urgency TEXT NOT NULL CHECK (urgency IN ('normal', 'urgent', 'emergency')),
    additional_information TEXT,
    requester_contact_preference TEXT NOT NULL DEFAULT 'in_app_chat',
    consent_given BOOLEAN NOT NULL DEFAULT FALSE CHECK (consent_given = TRUE),
    status TEXT NOT NULL DEFAULT 'created' CHECK (status IN (
        'created',
        'matching',
        'donors_notified',
        'responses_received',
        'connection_in_progress',
        'blood_bank_assistance',
        'escalation_in_progress',
        'fulfilled',
        'unresolved',
        'cancelled',
        'expired'
    )),
    escalation_stage INTEGER NOT NULL DEFAULT 1 CHECK (escalation_stage BETWEEN 1 AND 5),
    requested_for TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_blood_requests_requester ON public.blood_requests(requester_id);
CREATE INDEX IF NOT EXISTS idx_blood_requests_status ON public.blood_requests(status);
CREATE INDEX IF NOT EXISTS idx_blood_requests_city_group ON public.blood_requests(lower(city), blood_group);

CREATE TRIGGER trg_blood_requests_updated_at
    BEFORE UPDATE ON public.blood_requests
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- -----------------------------------------------------------------------------
-- 4. donor_matches
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.donor_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES public.blood_requests(id) ON DELETE CASCADE,
    donor_id UUID NOT NULL REFERENCES public.donor_profiles(id) ON DELETE CASCADE,
    priority_score NUMERIC(6,2) NOT NULL DEFAULT 0,
    match_reason TEXT NOT NULL,
    match_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (match_status IN ('candidate', 'notified', 'accepted', 'declined', 'skipped', 'expired')),
    escalation_stage INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id, donor_id)
);

CREATE INDEX IF NOT EXISTS idx_donor_matches_request ON public.donor_matches(request_id);
CREATE INDEX IF NOT EXISTS idx_donor_matches_donor ON public.donor_matches(donor_id);

CREATE TRIGGER trg_donor_matches_updated_at
    BEFORE UPDATE ON public.donor_matches
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- -----------------------------------------------------------------------------
-- 5. donor_responses
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.donor_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES public.blood_requests(id) ON DELETE CASCADE,
    donor_id UUID NOT NULL REFERENCES public.donor_profiles(id) ON DELETE CASCADE,
    response TEXT NOT NULL CHECK (response IN ('accepted', 'declined')),
    responded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id, donor_id)
);

CREATE INDEX IF NOT EXISTS idx_donor_responses_request ON public.donor_responses(request_id);

-- -----------------------------------------------------------------------------
-- 6. notifications
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL CHECK (notification_type IN (
        'new_request_alert',
        'donor_accepted',
        'donor_declined',
        'new_message',
        'request_status_update',
        'escalation_update',
        'blood_bank_fallback',
        'request_cancelled',
        'request_expired',
        'admin_notice'
    )),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    related_request_id UUID REFERENCES public.blood_requests(id) ON DELETE SET NULL,
    delivery_status TEXT NOT NULL DEFAULT 'saved' CHECK (delivery_status IN ('attempted', 'saved', 'delivered', 'failed')),
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON public.notifications(user_id, read_at);

-- -----------------------------------------------------------------------------
-- 7. conversations
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES public.blood_requests(id) ON DELETE CASCADE,
    requester_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    donor_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed', 'blocked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id, requester_id, donor_id)
);

CREATE INDEX IF NOT EXISTS idx_conversations_participants ON public.conversations(requester_id, donor_id);

CREATE TRIGGER trg_conversations_updated_at
    BEFORE UPDATE ON public.conversations
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- -----------------------------------------------------------------------------
-- 8. messages
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    message_text TEXT NOT NULL CHECK (char_length(trim(message_text)) >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON public.messages(conversation_id, created_at);

-- -----------------------------------------------------------------------------
-- 9. contact_sharing_consents
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.contact_sharing_consents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES public.blood_requests(id) ON DELETE CASCADE,
    requester_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    donor_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    requester_consent BOOLEAN NOT NULL DEFAULT FALSE,
    donor_consent BOOLEAN NOT NULL DEFAULT FALSE,
    requester_consent_at TIMESTAMPTZ,
    donor_consent_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'both_consented', 'withdrawn')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id, requester_id, donor_id)
);

CREATE TRIGGER trg_contact_sharing_consents_updated_at
    BEFORE UPDATE ON public.contact_sharing_consents
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- -----------------------------------------------------------------------------
-- 10. blood_banks
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.blood_banks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facility_name TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    phone TEXT NOT NULL,
    website TEXT,
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6),
    verification_status TEXT NOT NULL DEFAULT 'directory_listing'
        CHECK (verification_status IN ('licensed_verified', 'directory_listing', 'outdated', 'unverified')),
    availability_status TEXT NOT NULL DEFAULT 'contact_required'
        CHECK (availability_status IN (
            'directory_listing_only',
            'availability_not_available',
            'contact_required',
            'availability_confirmed_by_facility',
            'availability_unavailable',
            'information_outdated'
        )),
    source TEXT NOT NULL,
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_blood_banks_city ON public.blood_banks(lower(city));

CREATE TRIGGER trg_blood_banks_updated_at
    BEFORE UPDATE ON public.blood_banks
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- -----------------------------------------------------------------------------
-- 11. request_status_history
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.request_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES public.blood_requests(id) ON DELETE CASCADE,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    changed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_request_status_history_req ON public.request_status_history(request_id, created_at);

-- -----------------------------------------------------------------------------
-- 12. reports
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    reported_user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    request_id UUID REFERENCES public.blood_requests(id) ON DELETE SET NULL,
    reason TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'under_review', 'resolved', 'dismissed')),
    reviewed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_reports_updated_at
    BEFORE UPDATE ON public.reports
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- -----------------------------------------------------------------------------
-- 13. donor_documents
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.donor_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    donor_id UUID NOT NULL REFERENCES public.donor_profiles(id) ON DELETE CASCADE,
    storage_path TEXT NOT NULL,
    document_type TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (review_status IN ('pending_review', 'verified', 'rejected')),
    reviewed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_donor_documents_updated_at
    BEFORE UPDATE ON public.donor_documents
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- -----------------------------------------------------------------------------
-- 14. chatbot_sessions & 15. chatbot_messages
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.chatbot_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    session_status TEXT NOT NULL DEFAULT 'active' CHECK (session_status IN ('active', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_chatbot_sessions_updated_at
    BEFORE UPDATE ON public.chatbot_sessions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS public.chatbot_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.chatbot_sessions(id) ON DELETE CASCADE,
    sender_type TEXT NOT NULL CHECK (sender_type IN ('user', 'assistant')),
    message_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 16. user_blocks, 17. blood_bank_contact_attempts, 18. audit_logs
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blocker_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    blocked_user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (blocker_id, blocked_user_id)
);

CREATE TABLE IF NOT EXISTS public.blood_bank_contact_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES public.blood_requests(id) ON DELETE CASCADE,
    blood_bank_id UUID NOT NULL REFERENCES public.blood_banks(id) ON DELETE CASCADE,
    recorded_by UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    outcome TEXT NOT NULL CHECK (outcome IN ('contacted', 'confirmed_available', 'unavailable', 'no_response')),
    notes TEXT,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id UUID,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 19. donor_face_profiles & 20. face_verification_logs (Biometric Verification)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.donor_face_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    donor_id UUID NOT NULL UNIQUE REFERENCES public.donor_profiles(id) ON DELETE CASCADE,
    descriptor_json JSONB NOT NULL,
    consent_given BOOLEAN NOT NULL DEFAULT FALSE CHECK (consent_given = TRUE),
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_donor_face_profiles_updated_at
    BEFORE UPDATE ON public.donor_face_profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS public.face_verification_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    donor_id UUID NOT NULL REFERENCES public.donor_profiles(id) ON DELETE CASCADE,
    request_id UUID REFERENCES public.blood_requests(id) ON DELETE SET NULL,
    similarity_score NUMERIC(5,4) NOT NULL,
    verified BOOLEAN NOT NULL,
    reason TEXT NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 21. donor_location_tracking (Privacy-Safe Approximate Radius Only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.donor_location_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES public.blood_requests(id) ON DELETE CASCADE,
    donor_id UUID NOT NULL REFERENCES public.donor_profiles(id) ON DELETE CASCADE,
    zone_lat NUMERIC(7,3) NOT NULL,
    zone_lon NUMERIC(7,3) NOT NULL,
    radius_meters INTEGER NOT NULL DEFAULT 1000,
    tracking_status TEXT NOT NULL DEFAULT 'en_route'
        CHECK (tracking_status IN ('en_route', 'nearby', 'arrived_at_hospital', 'stopped')),
    distance_band TEXT NOT NULL DEFAULT 'Approximate ~1 km radius',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id, donor_id)
);

CREATE TRIGGER trg_donor_location_tracking_updated_at
    BEFORE UPDATE ON public.donor_location_tracking
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
