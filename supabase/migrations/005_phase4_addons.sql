-- =============================================================================
-- LifeLink: Phase 4 Add-On Extensions (Additional Regional Languages)
-- Run in Supabase SQL Editor AFTER 004_phase3_addons.sql
-- =============================================================================

ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_preferred_language_check;
ALTER TABLE public.profiles ADD CONSTRAINT profiles_preferred_language_check
    CHECK (preferred_language IN ('en', 'hi', 'mr', 'bn', 'ta'));
