import { createBrowserClient } from '@supabase/ssr';

/**
 * Creates and returns a Supabase client for client-side React components.
 * Strictly uses public environment variables (URL and ANON key).
 * Service-role keys are never included or accessed here.
 */
export function createClient() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';

  return createBrowserClient(supabaseUrl, supabaseAnonKey);
}
