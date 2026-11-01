-- ==============================================================================
-- Migration: 00003_create_event_plans.sql
-- Description: Creates the event_plans table for versioned event plans,
--              unique constraints, partial unique index for single active plan,
--              atomic revision creation function, least-privilege grants, and RLS.
-- ==============================================================================

-- 1. Create event_plans table
CREATE TABLE public.event_plans (
  id pg_catalog.uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  event_id pg_catalog.uuid NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
  version pg_catalog.int4 NOT NULL DEFAULT 1,
  title pg_catalog.text NOT NULL DEFAULT 'Master Plan',
  summary pg_catalog.text NULL,
  content pg_catalog.jsonb NOT NULL,
  prompt_context pg_catalog.jsonb NULL,
  change_summary pg_catalog.text NULL,
  created_by pg_catalog.uuid NULL REFERENCES public.profiles(id) ON DELETE SET NULL,
  is_active pg_catalog.bool NOT NULL DEFAULT true,
  created_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),

  CONSTRAINT event_plans_version_check
    CHECK (version >= 1),
  CONSTRAINT event_plans_title_check
    CHECK (char_length(trim(title)) >= 1),
  CONSTRAINT uq_event_plans_event_version
    UNIQUE (event_id, version),
  CONSTRAINT uq_event_plans_id_event
    UNIQUE (id, event_id)
);

-- 2. Indexes for event_plans table
-- Enforce at most one active plan per event
CREATE UNIQUE INDEX idx_event_plans_single_active
  ON public.event_plans(event_id)
  WHERE is_active = true;

-- Performance index for version history queries
CREATE INDEX idx_event_plans_event_version
  ON public.event_plans(event_id, version DESC);

-- GIN index for structured content search
CREATE INDEX idx_event_plans_content_gin
  ON public.event_plans USING gin (content);

-- Index on author reference
CREATE INDEX idx_event_plans_created_by
  ON public.event_plans(created_by);

-- 3. Function to atomically create and activate a new plan revision
-- Preserves revision history without deleting previous versions
CREATE OR REPLACE FUNCTION public.create_and_activate_plan_revision(
  p_event_id pg_catalog.uuid,
  p_title pg_catalog.text,
  p_summary pg_catalog.text,
  p_content pg_catalog.jsonb,
  p_prompt_context pg_catalog.jsonb DEFAULT NULL,
  p_change_summary pg_catalog.text DEFAULT NULL
)
RETURNS public.event_plans
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_next_version pg_catalog.int4;
  v_new_plan public.event_plans;
  v_caller_id pg_catalog.uuid;
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

  -- 3. Row lock on parent event to serialize concurrent version numbering
  PERFORM 1 FROM public.events WHERE id = p_event_id FOR UPDATE;

  -- 4. Calculate next sequential revision (COALESCE is an unqualified SQL construct)
  SELECT COALESCE(pg_catalog.max(version), 0) + 1
  INTO v_next_version
  FROM public.event_plans
  WHERE event_id = p_event_id;

  -- 5. Atomically demote currently active plan
  UPDATE public.event_plans
  SET is_active = false
  WHERE event_id = p_event_id
    AND is_active = true;

  -- 6. Insert new plan revision as active (created_by is bound to verified caller)
  INSERT INTO public.event_plans (
    event_id,
    version,
    title,
    summary,
    content,
    prompt_context,
    change_summary,
    created_by,
    is_active,
    created_at
  )
  VALUES (
    p_event_id,
    v_next_version,
    p_title,
    p_summary,
    p_content,
    p_prompt_context,
    p_change_summary,
    v_caller_id,
    true,
    pg_catalog.now()
  )
  RETURNING * INTO v_new_plan;

  RETURN v_new_plan;
END;
$$;

ALTER FUNCTION public.create_and_activate_plan_revision(
  pg_catalog.uuid, pg_catalog.text, pg_catalog.text, pg_catalog.jsonb, pg_catalog.jsonb, pg_catalog.text
) OWNER TO postgres;

REVOKE ALL ON FUNCTION public.create_and_activate_plan_revision(
  pg_catalog.uuid, pg_catalog.text, pg_catalog.text, pg_catalog.jsonb, pg_catalog.jsonb, pg_catalog.text
) FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.create_and_activate_plan_revision(
  pg_catalog.uuid, pg_catalog.text, pg_catalog.text, pg_catalog.jsonb, pg_catalog.jsonb, pg_catalog.text
) TO authenticated;

-- 4. Least-privilege table grants
-- Direct table access is revoked by default. Authenticated clients receive SELECT only.
-- All plan creation and activation is strictly channeled through the SECURITY DEFINER
-- function create_and_activate_plan_revision, preventing arbitrary version injection
-- or mutation/deletion of historical revisions.
REVOKE ALL ON TABLE public.event_plans FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.event_plans TO authenticated;
GRANT ALL ON TABLE public.event_plans TO service_role;

-- 5. Row-level security for event_plans
ALTER TABLE public.event_plans ENABLE ROW LEVEL SECURITY;

-- Read policy: Authenticated users can view plans only for events they own
CREATE POLICY event_plans_select_own
  ON public.event_plans
  FOR SELECT
  TO authenticated
  USING (public.is_event_owner(event_id));

-- Note: Client INSERT, UPDATE, and DELETE policies are intentionally omitted.
-- Plan revisions are append-only through create_and_activate_plan_revision().
-- Deletions of plans occur solely via cascade when parent event is deleted,
-- preserving immutable revision history.
