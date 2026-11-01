-- ==============================================================================
-- Migration: 00006_create_tasks_and_exports.sql
-- Description: Creates the tasks and plan_exports tables, constraints, indexes,
--              composite foreign keys to prevent cross-event plan references,
--              updated_at triggers, least-privilege grants, and RLS policies.
-- ==============================================================================

-- 1. Create tasks table
CREATE TABLE public.tasks (
  id pg_catalog.uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  event_id pg_catalog.uuid NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
  plan_id pg_catalog.uuid NULL,
  title pg_catalog.text NOT NULL,
  description pg_catalog.text NULL,
  status pg_catalog.text NOT NULL DEFAULT 'todo',
  priority pg_catalog.text NOT NULL DEFAULT 'medium',
  due_date pg_catalog.timestamptz NULL,
  assigned_to pg_catalog.uuid NULL REFERENCES public.profiles(id) ON DELETE SET NULL,
  category pg_catalog.text NULL,
  sort_order pg_catalog.int4 NOT NULL DEFAULT 0,
  created_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),
  updated_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),

  CONSTRAINT tasks_title_check
    CHECK (char_length(trim(title)) >= 1),
  CONSTRAINT tasks_status_check
    CHECK (status IN ('todo', 'in_progress', 'review', 'completed', 'blocked')),
  CONSTRAINT tasks_priority_check
    CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
  CONSTRAINT fk_tasks_plan_boundary
    FOREIGN KEY (plan_id, event_id)
    REFERENCES public.event_plans(id, event_id)
    ON DELETE SET NULL (plan_id)
);

-- 2. Indexes for tasks table
CREATE INDEX idx_tasks_event_id ON public.tasks(event_id);
CREATE INDEX idx_tasks_event_status ON public.tasks(event_id, status);
CREATE INDEX idx_tasks_due_date ON public.tasks(due_date);
CREATE INDEX idx_tasks_assigned_to ON public.tasks(assigned_to);

-- 3. Updated_at trigger for tasks (using public.set_updated_at from migration 00002)
CREATE TRIGGER trg_tasks_updated_at
  BEFORE UPDATE ON public.tasks
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();

-- 4. Create plan_exports table (private storage metadata only)
CREATE TABLE public.plan_exports (
  id pg_catalog.uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  event_id pg_catalog.uuid NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
  plan_id pg_catalog.uuid NULL,
  export_type pg_catalog.text NOT NULL,
  storage_path pg_catalog.text NOT NULL,
  file_size_bytes pg_catalog.int8 NULL,
  mime_type pg_catalog.text NOT NULL,
  metadata pg_catalog.jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by pg_catalog.uuid NULL REFERENCES public.profiles(id) ON DELETE SET NULL,
  created_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),

  CONSTRAINT plan_exports_type_check
    CHECK (export_type IN ('pdf_summary', 'ics_calendar', 'csv_budget', 'json_backup')),
  CONSTRAINT plan_exports_file_size_check
    CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
  CONSTRAINT fk_plan_exports_plan_boundary
    FOREIGN KEY (plan_id, event_id)
    REFERENCES public.event_plans(id, event_id)
    ON DELETE SET NULL (plan_id)
);

-- 5. Indexes for plan_exports table
CREATE INDEX idx_plan_exports_event_id ON public.plan_exports(event_id);
CREATE INDEX idx_plan_exports_event_type ON public.plan_exports(event_id, export_type);
CREATE INDEX idx_plan_exports_created_at ON public.plan_exports(created_at DESC);

-- 6. Least-privilege table grants
REVOKE ALL ON TABLE public.tasks FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.tasks TO authenticated;
GRANT ALL ON TABLE public.tasks TO service_role;

REVOKE ALL ON TABLE public.plan_exports FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.plan_exports TO authenticated;
GRANT ALL ON TABLE public.plan_exports TO service_role;

-- 7. Row-level security for tasks
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY tasks_select_own
  ON public.tasks
  FOR SELECT
  TO authenticated
  USING (public.is_event_owner(event_id));

CREATE POLICY tasks_insert_own
  ON public.tasks
  FOR INSERT
  TO authenticated
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY tasks_update_own
  ON public.tasks
  FOR UPDATE
  TO authenticated
  USING (public.is_event_owner(event_id))
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY tasks_delete_own
  ON public.tasks
  FOR DELETE
  TO authenticated
  USING (public.is_event_owner(event_id));

-- 8. Row-level security for plan_exports
ALTER TABLE public.plan_exports ENABLE ROW LEVEL SECURITY;

CREATE POLICY plan_exports_select_own
  ON public.plan_exports
  FOR SELECT
  TO authenticated
  USING (public.is_event_owner(event_id));

CREATE POLICY plan_exports_insert_own
  ON public.plan_exports
  FOR INSERT
  TO authenticated
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY plan_exports_update_own
  ON public.plan_exports
  FOR UPDATE
  TO authenticated
  USING (public.is_event_owner(event_id))
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY plan_exports_delete_own
  ON public.plan_exports
  FOR DELETE
  TO authenticated
  USING (public.is_event_owner(event_id));
