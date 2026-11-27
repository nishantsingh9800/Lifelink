-- =============================================================================
-- LifeLink: Optional Aadhaar at Signup (Verified When Donating or Receiving)
-- =============================================================================

ALTER TABLE public.profiles
    ALTER COLUMN aadhaar_last4 SET DEFAULT '0000',
    ALTER COLUMN aadhaar_hash DROP NOT NULL,
    ALTER COLUMN aadhaar_consent_at DROP NOT NULL;
