-- =============================================================================
-- LifeLink: Supabase Row Level Security (RLS) Policies
-- Run in Supabase SQL Editor AFTER 001_initial_schema.sql
-- =============================================================================

-- Helper functions to resolve current profile ID and admin status
CREATE OR REPLACE FUNCTION public.current_profile_id()
RETURNS UUID AS $$
    SELECT id FROM public.profiles WHERE auth_user_id = auth.uid() LIMIT 1;
$$ LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public;

CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.profiles
        WHERE auth_user_id = auth.uid()
          AND role = 'admin'
          AND account_status = 'active'
    );
$$ LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public;

-- Enable RLS on all tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donor_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.blood_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donor_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donor_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_sharing_consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.blood_banks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.request_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donor_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chatbot_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chatbot_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.blood_bank_contact_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donor_face_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.face_verification_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donor_location_tracking ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- profiles: users only see/edit their own profile (role locked by trigger); admins see all
-- -----------------------------------------------------------------------------
CREATE POLICY profiles_select_own_or_admin ON public.profiles
    FOR SELECT USING (auth_user_id = auth.uid() OR public.is_admin());

CREATE POLICY profiles_insert_own ON public.profiles
    FOR INSERT WITH CHECK (auth_user_id = auth.uid() AND role IN ('requester', 'donor'));

CREATE POLICY profiles_update_own_or_admin ON public.profiles
    FOR UPDATE USING (auth_user_id = auth.uid() OR public.is_admin())
    WITH CHECK (auth_user_id = auth.uid() OR public.is_admin());

-- -----------------------------------------------------------------------------
-- donor_profiles: owner or admin full access; authenticated read via FastAPI safe projection
-- -----------------------------------------------------------------------------
CREATE POLICY donor_profiles_select_owner_or_admin ON public.donor_profiles
    FOR SELECT USING (user_id = public.current_profile_id() OR public.is_admin());

CREATE POLICY donor_profiles_insert_owner ON public.donor_profiles
    FOR INSERT WITH CHECK (user_id = public.current_profile_id());

CREATE POLICY donor_profiles_update_owner_or_admin ON public.donor_profiles
    FOR UPDATE USING (user_id = public.current_profile_id() OR public.is_admin());

-- -----------------------------------------------------------------------------
-- blood_requests: requester owns; matched donors can view limited request; admins see all
-- -----------------------------------------------------------------------------
CREATE POLICY blood_requests_select_authorized ON public.blood_requests
    FOR SELECT USING (
        requester_id = public.current_profile_id()
        OR public.is_admin()
        OR EXISTS (
            SELECT 1 FROM public.donor_matches dm
            JOIN public.donor_profiles dp ON dp.id = dm.donor_id
            WHERE dm.request_id = blood_requests.id
              AND dp.user_id = public.current_profile_id()
        )
    );

CREATE POLICY blood_requests_insert_requester ON public.blood_requests
    FOR INSERT WITH CHECK (requester_id = public.current_profile_id());

CREATE POLICY blood_requests_update_requester_or_admin ON public.blood_requests
    FOR UPDATE USING (requester_id = public.current_profile_id() OR public.is_admin());

-- -----------------------------------------------------------------------------
-- donor_matches & donor_responses
-- -----------------------------------------------------------------------------
CREATE POLICY donor_matches_select_authorized ON public.donor_matches
    FOR SELECT USING (
        public.is_admin()
        OR EXISTS (SELECT 1 FROM public.blood_requests br WHERE br.id = donor_matches.request_id AND br.requester_id = public.current_profile_id())
        OR EXISTS (SELECT 1 FROM public.donor_profiles dp WHERE dp.id = donor_matches.donor_id AND dp.user_id = public.current_profile_id())
    );

CREATE POLICY donor_responses_select_authorized ON public.donor_responses
    FOR SELECT USING (
        public.is_admin()
        OR EXISTS (SELECT 1 FROM public.blood_requests br WHERE br.id = donor_responses.request_id AND br.requester_id = public.current_profile_id())
        OR EXISTS (SELECT 1 FROM public.donor_profiles dp WHERE dp.id = donor_responses.donor_id AND dp.user_id = public.current_profile_id())
    );

CREATE POLICY donor_responses_insert_own_donor ON public.donor_responses
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM public.donor_profiles dp WHERE dp.id = donor_responses.donor_id AND dp.user_id = public.current_profile_id())
    );

-- -----------------------------------------------------------------------------
-- notifications: strictly own notifications
-- -----------------------------------------------------------------------------
CREATE POLICY notifications_select_own ON public.notifications
    FOR SELECT USING (user_id = public.current_profile_id() OR public.is_admin());

CREATE POLICY notifications_update_own ON public.notifications
    FOR UPDATE USING (user_id = public.current_profile_id());

-- -----------------------------------------------------------------------------
-- conversations & messages: strictly authorized participants only
-- -----------------------------------------------------------------------------
CREATE POLICY conversations_select_participant ON public.conversations
    FOR SELECT USING (
        requester_id = public.current_profile_id()
        OR donor_id = public.current_profile_id()
    );

CREATE POLICY messages_select_participant ON public.messages
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.conversations c
            WHERE c.id = messages.conversation_id
              AND (c.requester_id = public.current_profile_id() OR c.donor_id = public.current_profile_id())
        )
    );

CREATE POLICY messages_insert_participant ON public.messages
    FOR INSERT WITH CHECK (
        sender_id = public.current_profile_id()
        AND EXISTS (
            SELECT 1 FROM public.conversations c
            WHERE c.id = messages.conversation_id
              AND c.status = 'active'
              AND (c.requester_id = public.current_profile_id() OR c.donor_id = public.current_profile_id())
        )
    );

-- -----------------------------------------------------------------------------
-- contact_sharing_consents: strictly participants
-- -----------------------------------------------------------------------------
CREATE POLICY contact_consents_participant ON public.contact_sharing_consents
    FOR ALL USING (
        requester_id = public.current_profile_id()
        OR donor_id = public.current_profile_id()
    );

-- -----------------------------------------------------------------------------
-- blood_banks: public directory read; admin-only write
-- -----------------------------------------------------------------------------
CREATE POLICY blood_banks_public_read ON public.blood_banks
    FOR SELECT USING (TRUE);

CREATE POLICY blood_banks_admin_write ON public.blood_banks
    FOR ALL USING (public.is_admin());

-- -----------------------------------------------------------------------------
-- request_status_history, blood_bank_contact_attempts
-- -----------------------------------------------------------------------------
CREATE POLICY status_history_authorized ON public.request_status_history
    FOR SELECT USING (
        public.is_admin()
        OR EXISTS (
            SELECT 1 FROM public.blood_requests br
            WHERE br.id = request_status_history.request_id
              AND br.requester_id = public.current_profile_id()
        )
    );

CREATE POLICY bb_attempts_authorized ON public.blood_bank_contact_attempts
    FOR ALL USING (
        recorded_by = public.current_profile_id() OR public.is_admin()
    );

-- -----------------------------------------------------------------------------
-- reports, donor_documents, chatbot, blocks, audit_logs
-- -----------------------------------------------------------------------------
CREATE POLICY reports_select_own_or_admin ON public.reports
    FOR SELECT USING (reporter_id = public.current_profile_id() OR public.is_admin());

CREATE POLICY reports_insert_own ON public.reports
    FOR INSERT WITH CHECK (reporter_id = public.current_profile_id());

CREATE POLICY reports_admin_update ON public.reports
    FOR UPDATE USING (public.is_admin());

CREATE POLICY donor_documents_own_or_admin ON public.donor_documents
    FOR ALL USING (
        public.is_admin()
        OR EXISTS (SELECT 1 FROM public.donor_profiles dp WHERE dp.id = donor_documents.donor_id AND dp.user_id = public.current_profile_id())
    );

CREATE POLICY chatbot_sessions_own ON public.chatbot_sessions
    FOR ALL USING (user_id = public.current_profile_id());

CREATE POLICY chatbot_messages_own ON public.chatbot_messages
    FOR ALL USING (
        EXISTS (SELECT 1 FROM public.chatbot_sessions cs WHERE cs.id = chatbot_messages.session_id AND cs.user_id = public.current_profile_id())
    );

CREATE POLICY user_blocks_own ON public.user_blocks
    FOR ALL USING (blocker_id = public.current_profile_id());

CREATE POLICY audit_logs_admin_only ON public.audit_logs
    FOR SELECT USING (public.is_admin());

CREATE POLICY donor_face_profiles_own_or_admin ON public.donor_face_profiles
    FOR ALL USING (
        public.is_admin()
        OR EXISTS (SELECT 1 FROM public.donor_profiles dp WHERE dp.id = donor_face_profiles.donor_id AND dp.user_id = public.current_profile_id())
    );

CREATE POLICY face_verification_logs_own_or_admin ON public.face_verification_logs
    FOR SELECT USING (
        public.is_admin()
        OR EXISTS (SELECT 1 FROM public.donor_profiles dp WHERE dp.id = face_verification_logs.donor_id AND dp.user_id = public.current_profile_id())
    );

CREATE POLICY tracking_authorized_participants ON public.donor_location_tracking
    FOR ALL USING (
        public.is_admin()
        OR EXISTS (SELECT 1 FROM public.blood_requests br WHERE br.id = donor_location_tracking.request_id AND br.requester_id = public.current_profile_id())
        OR EXISTS (SELECT 1 FROM public.donor_profiles dp WHERE dp.id = donor_location_tracking.donor_id AND dp.user_id = public.current_profile_id())
    );
