-- ==============================================================================
-- Migration: 00008_atomic_venue_selection.sql
-- Description: Adds atomic venue selection stored procedure to eliminate
--              concurrency race conditions when selecting event venues.
-- ==============================================================================

-- 1. Create atomic venue selection function
-- Serializes selection per event using FOR UPDATE row locking on public.events,
-- atomically unselects any currently selected venue, and marks the chosen venue
-- as selected within a single transaction.

CREATE OR REPLACE FUNCTION public.select_event_venue(
  p_event_id pg_catalog.uuid,
  p_venue_id pg_catalog.uuid
)
RETURNS public.venues
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
DECLARE
  v_caller_id pg_catalog.uuid;
  v_venue public.venues;
BEGIN
  -- 1. Enforce authenticated caller identity
  v_caller_id := auth.uid();
  IF v_caller_id IS NULL THEN
    RAISE EXCEPTION 'Unauthorized: Authenticated session required'
      USING ERRCODE = '42501';
  END IF;

  -- 2. Verify event ownership
  IF NOT public.is_event_owner(p_event_id) THEN
    RAISE EXCEPTION 'Forbidden: Caller does not own event %', p_event_id
      USING ERRCODE = '42501';
  END IF;

  -- 3. Acquire exclusive row lock on parent event to serialize concurrent selections
  PERFORM 1 FROM public.events WHERE id = p_event_id FOR UPDATE;

  -- 4. Verify target venue exists and belongs to the specified event
  SELECT * INTO v_venue
  FROM public.venues
  WHERE id = p_venue_id AND event_id = p_event_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Venue % not found for event %', p_venue_id, p_event_id
      USING ERRCODE = 'P0002';
  END IF;

  -- 5. Atomically demote any currently selected venue for this event
  UPDATE public.venues
  SET is_selected = false,
      updated_at = pg_catalog.now()
  WHERE event_id = p_event_id
    AND id <> p_venue_id
    AND is_selected = true;

  -- 6. Atomically promote the target venue to selected
  UPDATE public.venues
  SET is_selected = true,
      status = 'selected',
      updated_at = pg_catalog.now()
  WHERE id = p_venue_id AND event_id = p_event_id
  RETURNING * INTO v_venue;

  RETURN v_venue;
END;
$$;

ALTER FUNCTION public.select_event_venue(pg_catalog.uuid, pg_catalog.uuid) OWNER TO postgres;

REVOKE ALL ON FUNCTION public.select_event_venue(pg_catalog.uuid, pg_catalog.uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.select_event_venue(pg_catalog.uuid, pg_catalog.uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.select_event_venue(pg_catalog.uuid, pg_catalog.uuid) TO service_role;
