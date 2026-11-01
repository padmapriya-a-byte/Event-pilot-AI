-- ==============================================================================
-- Migration: 00001_initial_profiles_and_auth_trigger.sql
-- Description: Profiles table, RLS, least-privilege grants, system-field guard,
--              and automatic profile creation for Supabase Auth users.
-- Assumption: Supabase auth.users includes is_anonymous (boolean).
-- ==============================================================================

CREATE TABLE public.profiles (
  id pg_catalog.uuid PRIMARY KEY
    REFERENCES auth.users(id) ON DELETE CASCADE,
  email pg_catalog.text NULL,
  full_name pg_catalog.text NULL,
  avatar_url pg_catalog.text NULL,
  is_guest pg_catalog.bool NOT NULL DEFAULT false,
  created_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),
  updated_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now()
);

CREATE INDEX idx_profiles_email
  ON public.profiles(email) WHERE email IS NOT NULL;

CREATE INDEX idx_profiles_is_guest
  ON public.profiles(is_guest);

-- Least-privilege table access
REVOKE ALL ON TABLE public.profiles
  FROM PUBLIC, anon, authenticated;

GRANT SELECT ON TABLE public.profiles TO authenticated;
GRANT UPDATE (full_name, avatar_url)
  ON TABLE public.profiles TO authenticated;
GRANT ALL ON TABLE public.profiles TO service_role;

-- Row-level security
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY profiles_select_own
  ON public.profiles
  FOR SELECT
  TO authenticated
  USING ((SELECT auth.uid()) = id);

CREATE POLICY profiles_update_own
  ON public.profiles
  FOR UPDATE
  TO authenticated
  USING ((SELECT auth.uid()) = id)
  WITH CHECK ((SELECT auth.uid()) = id);

-- Protect system-managed profile fields
CREATE OR REPLACE FUNCTION public.protect_profile_system_fields()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  NEW.id := OLD.id;
  NEW.email := OLD.email;
  NEW.is_guest := OLD.is_guest;
  NEW.created_at := OLD.created_at;
  NEW.updated_at := pg_catalog.now();
  RETURN NEW;
END;
$$;

ALTER FUNCTION public.protect_profile_system_fields() OWNER TO postgres;

REVOKE ALL ON FUNCTION public.protect_profile_system_fields()
  FROM PUBLIC, anon, authenticated;

CREATE TRIGGER trg_protect_profile_system_fields
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.protect_profile_system_fields();

-- Automatically create a profile when a Supabase Auth user is created
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  INSERT INTO public.profiles (
    id,
    email,
    full_name,
    avatar_url,
    is_guest,
    created_at,
    updated_at
  )
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(
      NEW.raw_user_meta_data ->> 'full_name',
      NEW.raw_user_meta_data ->> 'name'
    ),
    NEW.raw_user_meta_data ->> 'avatar_url',
    COALESCE(NEW.is_anonymous, false),
    pg_catalog.now(),
    pg_catalog.now()
  );

  RETURN NEW;
END;
$$;

ALTER FUNCTION public.handle_new_user() OWNER TO postgres;

REVOKE ALL ON FUNCTION public.handle_new_user()
  FROM PUBLIC, anon, authenticated;

CREATE TRIGGER trg_on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();
