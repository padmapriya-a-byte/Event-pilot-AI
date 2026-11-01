-- ==============================================================================
-- Migration: 00005_create_venues_and_agenda_sessions.sql
-- Description: Creates the venues and agenda_sessions tables, constraints,
--              indexes, composite foreign keys to prevent cross-event venue
--              references, updated_at triggers, least-privilege grants, and RLS.
-- ==============================================================================

-- 1. Create venues table
CREATE TABLE public.venues (
  id pg_catalog.uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  event_id pg_catalog.uuid NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
  name pg_catalog.text NOT NULL,
  address pg_catalog.text NULL,
  city pg_catalog.text NULL,
  state_province pg_catalog.text NULL,
  country pg_catalog.text NULL,
  postal_code pg_catalog.text NULL,
  capacity pg_catalog.int4 NULL,
  rental_cost pg_catalog.numeric(12, 2) NULL,
  contact_name pg_catalog.text NULL,
  contact_email pg_catalog.text NULL,
  contact_phone pg_catalog.text NULL,
  amenities pg_catalog.text[] NOT NULL DEFAULT '{}',
  status pg_catalog.text NOT NULL DEFAULT 'shortlisted',
  is_selected pg_catalog.bool NOT NULL DEFAULT false,
  notes pg_catalog.text NULL,
  created_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),
  updated_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),

  CONSTRAINT venues_name_check
    CHECK (char_length(trim(name)) >= 1),
  CONSTRAINT venues_capacity_check
    CHECK (capacity IS NULL OR capacity > 0),
  CONSTRAINT venues_rental_cost_check
    CHECK (rental_cost IS NULL OR rental_cost >= 0),
  CONSTRAINT venues_status_check
    CHECK (status IN ('shortlisted', 'viewing_scheduled', 'proposal_received', 'selected', 'rejected')),
  CONSTRAINT uq_venues_id_event
    UNIQUE (id, event_id)
);

-- 2. Indexes for venues table
CREATE INDEX idx_venues_event_id ON public.venues(event_id);
CREATE INDEX idx_venues_status ON public.venues(event_id, status);

-- Enforce at most one selected venue per event
CREATE UNIQUE INDEX idx_venues_single_selected
  ON public.venues(event_id)
  WHERE is_selected = true;

-- 3. Create agenda_sessions table
CREATE TABLE public.agenda_sessions (
  id pg_catalog.uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  event_id pg_catalog.uuid NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
  venue_id pg_catalog.uuid NULL,
  title pg_catalog.text NOT NULL,
  description pg_catalog.text NULL,
  speaker_facilitator pg_catalog.text NULL,
  room_location pg_catalog.text NULL,
  start_time pg_catalog.timestamptz NOT NULL,
  end_time pg_catalog.timestamptz NOT NULL,
  session_type pg_catalog.text NOT NULL DEFAULT 'presentation',
  sort_order pg_catalog.int4 NOT NULL DEFAULT 0,
  created_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),
  updated_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),

  CONSTRAINT agenda_sessions_title_check
    CHECK (char_length(trim(title)) >= 1),
  CONSTRAINT agenda_sessions_time_range_check
    CHECK (end_time > start_time),
  CONSTRAINT agenda_sessions_type_check
    CHECK (session_type IN ('keynote', 'panel', 'workshop', 'presentation', 'break', 'networking', 'ceremony', 'other')),
  CONSTRAINT fk_agenda_sessions_venue_boundary
    FOREIGN KEY (venue_id, event_id)
    REFERENCES public.venues(id, event_id)
    ON DELETE SET NULL (venue_id)
);

-- 4. Indexes for agenda_sessions table
CREATE INDEX idx_agenda_sessions_event_start ON public.agenda_sessions(event_id, start_time);
CREATE INDEX idx_agenda_sessions_venue_id ON public.agenda_sessions(venue_id);

-- 5. Updated_at triggers (using public.set_updated_at from migration 00002)
CREATE TRIGGER trg_venues_updated_at
  BEFORE UPDATE ON public.venues
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_agenda_sessions_updated_at
  BEFORE UPDATE ON public.agenda_sessions
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();

-- 6. Least-privilege table grants
REVOKE ALL ON TABLE public.venues FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.venues TO authenticated;
GRANT ALL ON TABLE public.venues TO service_role;

REVOKE ALL ON TABLE public.agenda_sessions FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.agenda_sessions TO authenticated;
GRANT ALL ON TABLE public.agenda_sessions TO service_role;

-- 7. Row-level security for venues
ALTER TABLE public.venues ENABLE ROW LEVEL SECURITY;

CREATE POLICY venues_select_own
  ON public.venues
  FOR SELECT
  TO authenticated
  USING (public.is_event_owner(event_id));

CREATE POLICY venues_insert_own
  ON public.venues
  FOR INSERT
  TO authenticated
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY venues_update_own
  ON public.venues
  FOR UPDATE
  TO authenticated
  USING (public.is_event_owner(event_id))
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY venues_delete_own
  ON public.venues
  FOR DELETE
  TO authenticated
  USING (public.is_event_owner(event_id));

-- 8. Row-level security for agenda_sessions
ALTER TABLE public.agenda_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY agenda_sessions_select_own
  ON public.agenda_sessions
  FOR SELECT
  TO authenticated
  USING (public.is_event_owner(event_id));

CREATE POLICY agenda_sessions_insert_own
  ON public.agenda_sessions
  FOR INSERT
  TO authenticated
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY agenda_sessions_update_own
  ON public.agenda_sessions
  FOR UPDATE
  TO authenticated
  USING (public.is_event_owner(event_id))
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY agenda_sessions_delete_own
  ON public.agenda_sessions
  FOR DELETE
  TO authenticated
  USING (public.is_event_owner(event_id));
