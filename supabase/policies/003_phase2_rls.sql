-- =============================================================================
-- LifeLink: Supabase RLS Policies for Phase 2 Add-On Tables
-- =============================================================================

ALTER TABLE public.donor_availability ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_notification_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emergency_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.request_share_links ENABLE ROW LEVEL SECURITY;

CREATE POLICY donor_availability_own_or_admin ON public.donor_availability
    FOR ALL USING (
        public.is_admin()
        OR EXISTS (SELECT 1 FROM public.donor_profiles dp WHERE dp.id = donor_availability.donor_id AND dp.user_id = public.current_profile_id())
    );

CREATE POLICY notif_prefs_own ON public.user_notification_preferences
    FOR ALL USING (user_id = public.current_profile_id() OR public.is_admin());

CREATE POLICY emergency_contacts_participants ON public.emergency_contacts
    FOR ALL USING (
        public.is_admin()
        OR owner_user_id = public.current_profile_id()
        OR member_user_id = public.current_profile_id()
    );

CREATE POLICY share_links_requester_or_admin ON public.request_share_links
    FOR ALL USING (
        public.is_admin()
        OR created_by = public.current_profile_id()
        OR EXISTS (
            SELECT 1 FROM public.blood_requests br
            WHERE br.id = request_share_links.request_id AND br.requester_id = public.current_profile_id()
        )
    );
