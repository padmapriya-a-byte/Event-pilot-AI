/**
 * Shared TypeScript type definitions for EventPilot AI.
 * Strictly aligned with backend PostgreSQL schemas and REST API contracts.
 */

// ============================================================================
// Core API Envelope & Health
// ============================================================================

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: unknown;
}

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: ApiErrorPayload;
  message?: string;
  count?: number;
  limit?: number;
  offset?: number;
  timestamp: string;
}

export interface BackendHealthData {
  status: string;
  service: string;
  environment: string;
  version: string;
  integrations: {
    gemini_ai: {
      configured: boolean;
      model: string;
    };
    supabase: {
      configured: boolean;
      url_provided: boolean;
    };
  };
}

export interface DeleteResponse {
  id: string;
  deleted: boolean;
}

// ============================================================================
// Event Management Types
// ============================================================================

export type EventType =
  | 'conference'
  | 'wedding'
  | 'meetup'
  | 'corporate'
  | 'concert'
  | 'exhibition'
  | 'hackathon'
  | 'other';

export type EventStatus =
  | 'draft'
  | 'planning'
  | 'confirmed'
  | 'completed'
  | 'cancelled';

export interface EventRecord {
  id: string;
  owner_id: string;
  title: string;
  description: string | null;
  event_type: EventType;
  status: EventStatus;
  start_date: string | null;
  end_date: string | null;
  timezone: string;
  expected_attendees: number | null;
  currency: string;
  target_budget: number | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateEventInput {
  title: string;
  event_type: EventType;
  description?: string | null;
  status?: EventStatus;
  start_date?: string | null;
  end_date?: string | null;
  timezone?: string;
  expected_attendees?: number | null;
  currency?: string;
  target_budget?: number | null;
  is_archived?: boolean;
}

export type UpdateEventInput = Partial<CreateEventInput>;

export interface ListEventsParams {
  status?: EventStatus;
  include_archived?: boolean;
  limit?: number;
  offset?: number;
}

// ============================================================================
// Event Preferences Types
// ============================================================================

export interface EventPreferencesRecord {
  id: string;
  event_id: string;
  vibe_style: string[];
  catering_preferences: Record<string, unknown>;
  accessibility_requirements: string[];
  target_audience: string | null;
  ai_generation_parameters: Record<string, unknown>;
  custom_constraints: unknown[];
  created_at: string;
  updated_at: string;
}

export interface UpdatePreferencesInput {
  vibe_style?: string[];
  catering_preferences?: Record<string, unknown>;
  accessibility_requirements?: string[];
  target_audience?: string | null;
  ai_generation_parameters?: Record<string, unknown>;
  custom_constraints?: unknown[];
}

// ============================================================================
// Budget Types
// ============================================================================

export type BudgetCategory =
  | 'venue'
  | 'catering'
  | 'av_production'
  | 'entertainment'
  | 'marketing'
  | 'staffing'
  | 'transportation'
  | 'decor'
  | 'permits'
  | 'contingency'
  | 'other';

export type PaymentStatus =
  | 'unpaid'
  | 'partially_paid'
  | 'paid'
  | 'cancelled';

export interface BudgetItemRecord {
  id: string;
  event_id: string;
  category: BudgetCategory;
  name: string;
  estimated_amount: number;
  confirmed_amount: number;
  actual_amount: number;
  paid_amount: number;
  payment_status: PaymentStatus;
  due_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateBudgetItemInput {
  category: BudgetCategory;
  name: string;
  estimated_amount?: number;
  confirmed_amount?: number;
  actual_amount?: number;
  paid_amount?: number;
  payment_status?: PaymentStatus;
  due_date?: string | null;
  notes?: string | null;
}

export type UpdateBudgetItemInput = Partial<CreateBudgetItemInput>;

export interface ListBudgetItemsParams {
  category?: BudgetCategory;
  payment_status?: PaymentStatus;
  limit?: number;
  offset?: number;
}

export interface CategoryBudgetBreakdown {
  estimated: number;
  confirmed: number;
  actual: number;
  paid: number;
  items_count: number;
}

export interface BudgetSummary {
  event_id: string;
  currency: string;
  target_budget: number;
  total_estimated: number;
  total_confirmed: number;
  total_actual: number;
  total_paid: number;
  remaining_budget: number;
  variance: number;
  is_over_budget: boolean;
  items_count: number;
  category_breakdown: Record<string, CategoryBudgetBreakdown>;
}

// ============================================================================
// Venue Types
// ============================================================================

export type VenueStatus =
  | 'shortlisted'
  | 'viewing_scheduled'
  | 'proposal_received'
  | 'selected'
  | 'rejected';

export interface VenueRecord {
  id: string;
  event_id: string;
  name: string;
  address: string | null;
  city: string | null;
  state_province: string | null;
  country: string | null;
  postal_code: string | null;
  capacity: number | null;
  rental_cost: number | null;
  amenities: string[];
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  status: VenueStatus;
  is_selected: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateVenueInput {
  name: string;
  address?: string | null;
  city?: string | null;
  state_province?: string | null;
  country?: string | null;
  postal_code?: string | null;
  capacity?: number | null;
  rental_cost?: number | null;
  amenities?: string[];
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  status?: VenueStatus;
  is_selected?: boolean;
  notes?: string | null;
}

export type UpdateVenueInput = Partial<CreateVenueInput>;

// ============================================================================
// Agenda Session Types
// ============================================================================

export type SessionType =
  | 'keynote'
  | 'panel'
  | 'workshop'
  | 'presentation'
  | 'break'
  | 'networking'
  | 'ceremony'
  | 'other';

export interface AgendaSessionRecord {
  id: string;
  event_id: string;
  title: string;
  description: string | null;
  start_time: string;
  end_time: string;
  session_type: SessionType;
  room_location: string | null;
  speaker_facilitator: string | null;
  venue_id: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface CreateSessionInput {
  title: string;
  start_time: string;
  end_time: string;
  description?: string | null;
  session_type?: SessionType;
  room_location?: string | null;
  speaker_facilitator?: string | null;
  venue_id?: string | null;
  sort_order?: number;
}

export type UpdateSessionInput = Partial<CreateSessionInput>;

// ============================================================================
// Task Management Types
// ============================================================================

export type TaskStatus =
  | 'todo'
  | 'in_progress'
  | 'review'
  | 'completed'
  | 'blocked';

export type TaskPriority =
  | 'low'
  | 'medium'
  | 'high'
  | 'urgent';

export interface TaskRecord {
  id: string;
  event_id: string;
  plan_id: string | null;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  assigned_to: string | null;
  category: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface CreateTaskInput {
  title: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  due_date?: string | null;
  assigned_to?: string | null;
  category?: string | null;
  plan_id?: string | null;
  sort_order?: number;
}

export type UpdateTaskInput = Partial<CreateTaskInput>;

export interface ListTasksParams {
  status?: TaskStatus;
  priority?: TaskPriority;
  limit?: number;
  offset?: number;
}

// ============================================================================
// Export / Deliverable Types
// ============================================================================

export type ExportType =
  | 'pdf_summary'
  | 'ics_calendar'
  | 'csv_budget'
  | 'json_backup';

export interface ExportRecord {
  id: string;
  event_id: string;
  user_id: string;
  plan_id: string | null;
  export_type: ExportType;
  storage_path: string;
  file_name: string;
  file_size_bytes: number;
  mime_type: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export interface GenerateExportInput {
  export_type: ExportType;
  plan_id?: string | null;
}

// ============================================================================
// AI Planning & Budget Optimization Types
// ============================================================================

export interface PlanTimelineItem {
  time_range: string;
  activity: string;
  description: string;
}

export interface PlanSuggestedVenue {
  name: string;
  location: string;
  estimated_cost: number;
  capacity: number;
  notes: string;
  is_suggestion: boolean;
  verification_status: string;
}

export interface PlanBudgetAllocation {
  category: string;
  allocated_amount: number;
  rationale: string;
}

export interface AIPlanGeneratedContent {
  theme: string;
  summary: string;
  timeline: PlanTimelineItem[];
  suggested_venues: PlanSuggestedVenue[];
  recommended_budget_allocation: PlanBudgetAllocation[];
  disclaimer: string;
}

export interface PlanRevisionRecord {
  id: string;
  event_id: string;
  revision_number: number;
  is_active: boolean;
  title: string;
  summary: string;
  content: AIPlanGeneratedContent;
  prompt_context: Record<string, unknown> | null;
  change_summary: string | null;
  created_at: string;
}

export interface PlanEventInput {
  event_id: string;
  prompt_context?: {
    user_notes?: string;
    notes?: string;
    [key: string]: unknown;
  } | null;
  change_summary?: string | null;
}

export interface PlanEventResponse {
  plan: PlanRevisionRecord;
  generated_content: AIPlanGeneratedContent;
}

export interface BudgetOptimizationAllocation {
  category: string;
  current_estimated: number;
  recommended_amount: number;
  variance: number;
  savings_strategy: string;
}

export interface AIBudgetOptimization {
  currency: string;
  target_budget: number | null;
  total_allocated: number;
  remaining_contingency: number;
  allocations: BudgetOptimizationAllocation[];
  optimization_tips: string[];
  disclaimer: string;
}

export interface BudgetOptimizeInput {
  event_id: string;
  optimization_goal?: string | null;
}
