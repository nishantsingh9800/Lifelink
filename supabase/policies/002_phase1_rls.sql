-- =============================================================================
-- LifeLink: Supabase RLS Policies for Phase 1 Add-On Tables
-- Run in Supabase SQL Editor AFTER 002_phase1_addons.sql
-- =============================================================================

ALTER TABLE public.hospitals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hospital_verification_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hospital_verification_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.request_coordinators ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.blood_bank_stock_updates ENABLE ROW LEVEL SECURITY;

-- Update profile signup policy so 'hospital' role can register safely (never admin)
DROP POLICY IF EXISTS profiles_insert_own ON public.profiles;
CREATE POLICY profiles_insert_own ON public.profiles
    FOR INSERT WITH CHECK (auth_user_id = auth.uid() AND role IN ('requester', 'donor', 'hospital'));

-- Allow active coordinators & verified managing hospitals to read authorized blood_requests
DROP POLICY IF EXISTS blood_requests_select_authorized ON public.blood_requests;
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
        OR EXISTS (
            SELECT 1 FROM public.request_coordinators rc
            WHERE rc.request_id = blood_requests.id
              AND rc.coordinator_user_id = public.current_profile_id()
              AND rc.status = 'active'
        )
        OR EXISTS (
            SELECT 1 FROM public.hospitals h
            WHERE h.user_id = public.current_profile_id()
              AND h.verification_status = 'verified'
              AND (blood_requests.hospital_id = h.id OR lower(blood_requests.city) = lower(h.city))
        )
    );

-- Hospitals: own registration read/write; verified hospitals readable publicly; admin full
CREATE POLICY hospitals_select_policy ON public.hospitals
    FOR SELECT USING (
        user_id = public.current_profile_id()
        OR verification_status = 'verified'
        OR public.is_admin()
    );

CREATE POLICY hospitals_insert_own ON public.hospitals
    FOR INSERT WITH CHECK (user_id = public.current_profile_id());

CREATE POLICY hospitals_update_own_or_admin ON public.hospitals
    FOR UPDATE USING (user_id = public.current_profile_id() OR public.is_admin());

CREATE POLICY hospital_docs_own_or_admin ON public.hospital_verification_documents
    FOR ALL USING (
        public.is_admin()
        OR EXISTS (
            SELECT 1 FROM public.hospitals h
            WHERE h.id = hospital_verification_documents.hospital_id
              AND h.user_id = public.current_profile_id()
        )
    );

CREATE POLICY hospital_history_own_or_admin ON public.hospital_verification_history
    FOR SELECT USING (
        public.is_admin()
        OR EXISTS (
            SELECT 1 FROM public.hospitals h
            WHERE h.id = hospital_verification_history.hospital_id
              AND h.user_id = public.current_profile_id()
        )
    );

-- Request Coordinators: requester, invited/active coordinator, or admin
CREATE POLICY request_coordinators_participant ON public.request_coordinators
    FOR ALL USING (
        public.is_admin()
        OR requester_id = public.current_profile_id()
        OR coordinator_user_id = public.current_profile_id()
    );

-- Conversations & Messages: allow active coordinators in addition to requester and donor
DROP POLICY IF EXISTS conversations_select_participant ON public.conversations;
CREATE POLICY conversations_select_participant ON public.conversations
    FOR SELECT USING (
        requester_id = public.current_profile_id()
        OR donor_id = public.current_profile_id()
        OR EXISTS (
            SELECT 1 FROM public.request_coordinators rc
            WHERE rc.request_id = conversations.request_id
              AND rc.coordinator_user_id = public.current_profile_id()
              AND rc.status = 'active'
              AND rc.can_chat = TRUE
        )
    );

DROP POLICY IF EXISTS messages_select_participant ON public.messages;
CREATE POLICY messages_select_participant ON public.messages
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.conversations c
            WHERE c.id = messages.conversation_id
              AND (
                  c.requester_id = public.current_profile_id()
                  OR c.donor_id = public.current_profile_id()
                  OR EXISTS (
                      SELECT 1 FROM public.request_coordinators rc
                      WHERE rc.request_id = c.request_id
                        AND rc.coordinator_user_id = public.current_profile_id()
                        AND rc.status = 'active'
                        AND rc.can_chat = TRUE
                  )
              )
        )
    );

DROP POLICY IF EXISTS messages_insert_participant ON public.messages;
CREATE POLICY messages_insert_participant ON public.messages
    FOR INSERT WITH CHECK (
        sender_id = public.current_profile_id()
        AND EXISTS (
            SELECT 1 FROM public.conversations c
            WHERE c.id = messages.conversation_id
              AND c.status = 'active'
              AND (
                  c.requester_id = public.current_profile_id()
                  OR c.donor_id = public.current_profile_id()
                  OR EXISTS (
                      SELECT 1 FROM public.request_coordinators rc
                      WHERE rc.request_id = c.request_id
                        AND rc.coordinator_user_id = public.current_profile_id()
                        AND rc.status = 'active'
                        AND rc.can_chat = TRUE
                  )
              )
        )
    );

-- Blood bank stock updates: public read; admin or verified hospital write
CREATE POLICY bb_stock_updates_public_read ON public.blood_bank_stock_updates
    FOR SELECT USING (TRUE);

CREATE POLICY bb_stock_updates_authorized_write ON public.blood_bank_stock_updates
    FOR INSERT WITH CHECK (
        public.is_admin()
        OR EXISTS (
            SELECT 1 FROM public.hospitals h
            WHERE h.user_id = public.current_profile_id()
              AND h.verification_status = 'verified'
        )
    );
