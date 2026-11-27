-- =============================================================================
-- LifeLink: Supabase RLS Policies for Phase 3 Add-On Tables
-- =============================================================================

ALTER TABLE public.donation_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.referral_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY donation_records_own_or_admin ON public.donation_records
    FOR ALL USING (
        public.is_admin()
        OR EXISTS (
            SELECT 1 FROM public.donor_profiles dp
            WHERE dp.id = donation_records.donor_id AND dp.user_id = public.current_profile_id()
        )
    );

CREATE POLICY referral_records_own_or_admin ON public.referral_records
    FOR SELECT USING (
        public.is_admin()
        OR referrer_user_id = public.current_profile_id()
        OR referred_user_id = public.current_profile_id()
    );
