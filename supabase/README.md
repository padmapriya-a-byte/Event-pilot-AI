# Supabase Migrations & Database Architecture

This directory is reserved for version-controlled PostgreSQL schema migrations for **EventPilot AI**.

## Directory Structure
- `migrations/`: Sequential SQL migration scripts (e.g., `00001_initial_schema.sql`, `00002_add_events_table.sql`).

## Guidelines
1. **Row Level Security (RLS)**:
   - All client-accessible tables must have RLS enabled.
   - Policies should enforce authentication via `auth.uid()`.
2. **Backend Admin Access**:
   - The Flask backend utilizes the `SUPABASE_SERVICE_ROLE_KEY` exclusively server-side for admin tasks or webhook ingestion.
   - The Service Role key must **never** be included in client-side bundles or repository commits.
3. **Applying Migrations**:
   - Use the Supabase CLI (`supabase db push`) or apply SQL migrations directly in the Supabase SQL Editor.
