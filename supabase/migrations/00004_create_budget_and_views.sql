-- ==============================================================================
-- Migration: 00004_create_budget_and_views.sql
-- Description: Creates the budget_items table, constraints, indexes, RLS,
--              updated_at trigger, and the event_budget_summaries aggregation
--              view configured with security_invoker = true.
-- ==============================================================================

-- 1. Create budget_items table
CREATE TABLE public.budget_items (
  id pg_catalog.uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  event_id pg_catalog.uuid NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
  category pg_catalog.text NOT NULL,
  name pg_catalog.text NOT NULL,
  estimated_amount pg_catalog.numeric(12, 2) NOT NULL DEFAULT 0.00,
  confirmed_amount pg_catalog.numeric(12, 2) NOT NULL DEFAULT 0.00,
  actual_amount pg_catalog.numeric(12, 2) NOT NULL DEFAULT 0.00,
  paid_amount pg_catalog.numeric(12, 2) NOT NULL DEFAULT 0.00,
  payment_status pg_catalog.text NOT NULL DEFAULT 'unpaid',
  due_date pg_catalog.date NULL,
  notes pg_catalog.text NULL,
  created_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),
  updated_at pg_catalog.timestamptz NOT NULL DEFAULT pg_catalog.now(),

  CONSTRAINT budget_items_category_check
    CHECK (category IN ('venue', 'catering', 'av_production', 'entertainment', 'marketing', 'staffing', 'transportation', 'decor', 'permits', 'contingency', 'other')),
  CONSTRAINT budget_items_name_check
    CHECK (char_length(trim(name)) >= 1),
  CONSTRAINT budget_items_estimated_amount_check
    CHECK (estimated_amount >= 0),
  CONSTRAINT budget_items_confirmed_amount_check
    CHECK (confirmed_amount >= 0),
  CONSTRAINT budget_items_actual_amount_check
    CHECK (actual_amount >= 0),
  CONSTRAINT budget_items_paid_amount_check
    CHECK (paid_amount >= 0),
  CONSTRAINT budget_items_payment_status_check
    CHECK (payment_status IN ('unpaid', 'partially_paid', 'paid', 'cancelled'))
);

-- 2. Indexes for budget_items table
CREATE INDEX idx_budget_items_event_category ON public.budget_items(event_id, category);
CREATE INDEX idx_budget_items_payment_status ON public.budget_items(event_id, payment_status);
CREATE INDEX idx_budget_items_due_date ON public.budget_items(due_date);

-- 3. Updated_at trigger for budget_items
CREATE TRIGGER trg_budget_items_updated_at
  BEFORE UPDATE ON public.budget_items
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();

-- 4. Least-privilege table grants
REVOKE ALL ON TABLE public.budget_items FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.budget_items TO authenticated;
GRANT ALL ON TABLE public.budget_items TO service_role;

-- 5. Row-level security for budget_items
ALTER TABLE public.budget_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY budget_items_select_own
  ON public.budget_items
  FOR SELECT
  TO authenticated
  USING (public.is_event_owner(event_id));

CREATE POLICY budget_items_insert_own
  ON public.budget_items
  FOR INSERT
  TO authenticated
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY budget_items_update_own
  ON public.budget_items
  FOR UPDATE
  TO authenticated
  USING (public.is_event_owner(event_id))
  WITH CHECK (public.is_event_owner(event_id));

CREATE POLICY budget_items_delete_own
  ON public.budget_items
  FOR DELETE
  TO authenticated
  USING (public.is_event_owner(event_id));

-- 6. Budget summary aggregation view
-- Configured with security_invoker = true so PostgreSQL 15+ evaluates RLS policies
-- of underlying tables (events and budget_items) for the querying user.
CREATE OR REPLACE VIEW public.event_budget_summaries
WITH (security_invoker = true)
AS
WITH category_aggregates AS (
  SELECT
    event_id,
    pg_catalog.jsonb_object_agg(
      category,
      pg_catalog.jsonb_build_object(
        'estimated', cat_estimated,
        'confirmed', cat_confirmed,
        'actual', cat_actual,
        'paid', cat_paid
      )
    ) AS category_breakdowns
  FROM (
    SELECT
      event_id,
      category,
      COALESCE(pg_catalog.sum(estimated_amount), 0.00) AS cat_estimated,
      COALESCE(pg_catalog.sum(confirmed_amount), 0.00) AS cat_confirmed,
      COALESCE(pg_catalog.sum(actual_amount), 0.00) AS cat_actual,
      COALESCE(pg_catalog.sum(paid_amount), 0.00) AS cat_paid
    FROM public.budget_items
    GROUP BY event_id, category
  ) sub
  GROUP BY event_id
),
event_totals AS (
  SELECT
    event_id,
    COALESCE(pg_catalog.sum(estimated_amount), 0.00) AS total_estimated,
    COALESCE(pg_catalog.sum(confirmed_amount), 0.00) AS total_confirmed,
    COALESCE(pg_catalog.sum(actual_amount), 0.00) AS total_actual,
    COALESCE(pg_catalog.sum(paid_amount), 0.00) AS total_paid
  FROM public.budget_items
  GROUP BY event_id
)
SELECT
  e.id AS event_id,
  e.owner_id,
  e.target_budget,
  e.currency,
  COALESCE(t.total_estimated, 0.00) AS total_estimated,
  COALESCE(t.total_confirmed, 0.00) AS total_confirmed,
  COALESCE(t.total_actual, 0.00) AS total_actual,
  COALESCE(t.total_paid, 0.00) AS total_paid,
  (COALESCE(e.target_budget, 0.00) - COALESCE(t.total_actual, 0.00)) AS remaining_budget,
  COALESCE(c.category_breakdowns, '{}'::jsonb) AS category_breakdowns
FROM public.events e
LEFT JOIN event_totals t ON e.id = t.event_id
LEFT JOIN category_aggregates c ON e.id = c.event_id;

-- 7. Grants for view
REVOKE ALL ON TABLE public.event_budget_summaries FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.event_budget_summaries TO authenticated;
GRANT ALL ON TABLE public.event_budget_summaries TO service_role;
