-- ==============================================================================
-- Migration: 00002_create_events_and_preferences.sql
-- Description: Creates the events and event_preferences tables, constraints,
--              indexes, the public.is_event_owner security-definer helper,
--              updated_at triggers, least-privilege grants, and RLS policies.
-- ==============================================================================

-- 1. Create events table
CREATE TABLE public.events (
  id pg_catalog.uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  owner_id pg_catalog.uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  title pg_catalog.text NOT NULL,
  description pg_catalog.text NULL,
  event_type pg_catalog.text NOT NULL,
  status pg_catalog.text NOT NULL DEFAULT 'draft',
  start_date pg_catalog.timestamptz NULL,
  end_date pg_catalog.timestamptz NULL,
  timezone pg_catalog.text NOT NULL DEFAULT 'UTC',
  expected_attendees pg_catalog.int4 NULL,
  currency pg_catalog.varchar(3) NOT NULL DEFAULT 'USD',
  target_budget pg_catalog.numeric(12, 2) NULL,
  is_archived pg_catalog.bool NOT NULL DEFAULT false,
  created_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),
  updated_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),

  CONSTRAINT events_title_check
    CHECK (char_length(trim(title)) >= 2),
  CONSTRAINT events_type_check
    CHECK (event_type IN ('conference', 'wedding', 'meetup', 'corporate', 'concert', 'exhibition', 'hackathon', 'other')),
  CONSTRAINT events_status_check
    CHECK (status IN ('draft', 'planning', 'confirmed', 'completed', 'cancelled')),
  CONSTRAINT events_date_range_check
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
  CONSTRAINT events_attendees_check
    CHECK (expected_attendees IS NULL OR expected_attendees >= 0),
  CONSTRAINT events_currency_check
    CHECK (currency ~ '^[A-Z]{3}$'),
  CONSTRAINT events_target_budget_check
    CHECK (target_budget IS NULL OR target_budget >= 0)
);

-- 2. Indexes for events table
CREATE INDEX idx_events_owner_id ON public.events(owner_id);
CREATE INDEX idx_events_status ON public.events(status);
CREATE INDEX idx_events_start_date ON public.events(start_date);
CREATE INDEX idx_events_created_at ON public.events(created_at DESC);

-- 3. Security-definer ownership helper function
-- Used by child tables and policies to verify caller event ownership
CREATE OR REPLACE FUNCTION public.is_event_owner(target_event_id pg_catalog.uuid)
RETURNS pg_catalog.bool
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.events
    WHERE id = target_event_id
      AND owner_id = (SELECT auth.uid())
  );
$$;

ALTER FUNCTION public.is_event_owner(pg_catalog.uuid) OWNER TO postgres;

REVOKE ALL ON FUNCTION public.is_event_owner(pg_catalog.uuid)
  FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.is_event_owner(pg_catalog.uuid)
  TO authenticated, service_role;

-- 4. Create event_preferences table (one row per event)
CREATE TABLE public.event_preferences (
  id pg_catalog.uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  event_id pg_catalog.uuid NOT NULL UNIQUE REFERENCES public.events(id) ON DELETE CASCADE,
  vibe_style pg_catalog.text[] NOT NULL DEFAULT '{}',
  catering_preferences pg_catalog.jsonb NOT NULL DEFAULT '{}'::jsonb,
  accessibility_requirements pg_catalog.text[] NOT NULL DEFAULT '{}',
  target_audience pg_catalog.text NULL,
  ai_generation_parameters pg_catalog.jsonb NOT NULL DEFAULT '{"temperature": 0.7, "model": "gemini-2.5-flash"}'::jsonb,
  custom_constraints pg_catalog.jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),
  updated_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now()
);

-- 5. Indexes for event_preferences table
CREATE INDEX idx_event_preferences_event_id ON public.event_preferences(event_id);
CREATE INDEX idx_event_preferences_catering_gin ON public.event_preferences USING gin (catering_preferences);

-- 6. Updated_at trigger function & triggers
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  NEW.updated_at := pg_catalog.now();
  RETURN NEW;
END;
$$;

ALTER FUNCTION public.set_updated_at() OWNER TO postgres;

REVOKE ALL ON FUNCTION public.set_updated_at()
  FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.set_updated_at()
  TO authenticated, service_role;

CREATE TRIGGER trg_events_updated_at
  BEFORE UPDATE ON public.events
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_event_preferences_updated_at
  BEFORE UPDATE ON public.event_preferences
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();

-- 7. Least-privilege table grants
REVOKE ALL ON TABLE public.events FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.events TO authenticated;
GRANT ALL ON TABLE public.events TO service_role;

REVOKE ALL ON TABLE public.event_preferences FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.event_preferences TO authenticated;
GRANT ALL ON TABLE public.event_preferences TO service_role;

-- 8. Row-level security for events
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;

CREATE POLICY events_select_own
  ON public.events
  FOR SELECT
  TO authenticated
  USING ((SELECT auth.uid()) = owner_id);

CREATE POLICY events_insert_own
  ON public.events
  FOR INSERT
  TO authenticated
  WITH CHECK ((SELECT auth.uid()) = owner_id);

CREATE POLICY events_update_own
  ON public.events
  FOR UPDATE
  TO authenticated
  USING ((SELECT auth.uid()) = owner_id)
  WITH CHECK ((SELECT auth.uid()) = owner_id);

CREATE POLICY events_delete_own
  ON public.events
  FOR DELETE
  TO authenticated
  USING ((SELECT auth.uid()) = owner_id);

-- 9. Row-level security for event_preferences
ALTER TABLE public.event_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY event_preferences_select_own
  ON public.event_preferences
  FOR SELECT
  TO authenticated
  USING (public.is_event_owner(event_id));

CREATE POLICY event_preferences_insert_own
  ON public.event_preferences
  FOR INSERT
  TO authenticated
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY event_preferences_update_own
  ON public.event_preferences
  FOR UPDATE
  TO authenticated
  USING (public.is_event_owner(event_id))
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY event_preferences_delete_own
  ON public.event_preferences
  FOR DELETE
  TO authenticated
  USING (public.is_event_owner(event_id));
