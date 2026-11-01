-- ==============================================================================
-- Migration: 00007_enable_row_level_security.sql
-- Description: Final Phase 2 security hardening. Confirms RLS enablement across
--              all 9 application tables, enforces least-privilege grants,
--              preserves owner-scoped access, ensures restricted write access
--              for event_plans, and restricts plan_exports to authenticated
--              SELECT only (service_role handles export writes).
-- ==============================================================================

-- 1. Ensure Row Level Security (RLS) is explicitly enabled across all 9 application tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.budget_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.venues ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agenda_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plan_exports ENABLE ROW LEVEL SECURITY;

-- 2. Baseline grant audit: Revoke default permissions from PUBLIC and anon across all tables
REVOKE ALL ON TABLE public.profiles FROM PUBLIC, anon;
REVOKE ALL ON TABLE public.events FROM PUBLIC, anon;
REVOKE ALL ON TABLE public.event_preferences FROM PUBLIC, anon;
REVOKE ALL ON TABLE public.event_plans FROM PUBLIC, anon;
REVOKE ALL ON TABLE public.budget_items FROM PUBLIC, anon;
REVOKE ALL ON TABLE public.venues FROM PUBLIC, anon;
REVOKE ALL ON TABLE public.agenda_sessions FROM PUBLIC, anon;
REVOKE ALL ON TABLE public.tasks FROM PUBLIC, anon;
REVOKE ALL ON TABLE public.plan_exports FROM PUBLIC, anon;

-- 3. Security hardening for plan_exports:
-- Restrict authenticated clients to SELECT only.
-- Backend service_role exclusively generates and records export deliverables.
REVOKE INSERT, UPDATE, DELETE ON TABLE public.plan_exports FROM authenticated;

-- Drop client write policies from plan_exports if they exist
DROP POLICY IF EXISTS plan_exports_insert_own ON public.plan_exports;
DROP POLICY IF EXISTS plan_exports_update_own ON public.plan_exports;
DROP POLICY IF EXISTS plan_exports_delete_own ON public.plan_exports;

-- Ensure owner-scoped read policy exists for plan_exports
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'plan_exports'
      AND policyname = 'plan_exports_select_own'
  ) THEN
    CREATE POLICY plan_exports_select_own
      ON public.plan_exports
      FOR SELECT
      TO authenticated
      USING (public.is_event_owner(event_id));
  END IF;
END
$$;

-- 4. Audit verification of event_plans write restriction:
-- Verify direct client write access remains revoked.
-- Revisions must be created exclusively via create_and_activate_plan_revision().
REVOKE INSERT, UPDATE, DELETE ON TABLE public.event_plans FROM authenticated;
DROP POLICY IF EXISTS event_plans_insert_own ON public.event_plans;
DROP POLICY IF EXISTS event_plans_update_own ON public.event_plans;
DROP POLICY IF EXISTS event_plans_delete_own ON public.event_plans;

-- Ensure owner-scoped read policy exists for event_plans
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'event_plans'
      AND policyname = 'event_plans_select_own'
  ) THEN
    CREATE POLICY event_plans_select_own
      ON public.event_plans
      FOR SELECT
      TO authenticated
      USING (public.is_event_owner(event_id));
  END IF;
END
$$;
