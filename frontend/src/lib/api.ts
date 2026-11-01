import {
  ApiResponse,
  BackendHealthData,
  EventRecord,
  CreateEventInput,
  UpdateEventInput,
  ListEventsParams,
  EventPreferencesRecord,
  UpdatePreferencesInput,
  BudgetItemRecord,
  CreateBudgetItemInput,
  UpdateBudgetItemInput,
  ListBudgetItemsParams,
  BudgetSummary,
  VenueRecord,
  CreateVenueInput,
  UpdateVenueInput,
  AgendaSessionRecord,
  CreateSessionInput,
  UpdateSessionInput,
  TaskRecord,
  CreateTaskInput,
  UpdateTaskInput,
  ListTasksParams,
  ExportRecord,
  GenerateExportInput,
  PlanEventInput,
  PlanEventResponse,
  BudgetOptimizeInput,
  AIBudgetOptimization,
  DeleteResponse,
} from '@/types';
import { createClient } from '@/lib/supabase/client';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';

/**
 * Builds a valid URL query string from a key-value parameter object.
 */
function buildQueryString(params?: Record<string, unknown>): string {
  if (!params) return '';
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.append(key, String(value));
    }
  }
  const str = searchParams.toString();
  return str ? `?${str}` : '';
}

/**
 * Retrieves the current Supabase session access token, or null if unauthenticated.
 * Handles missing sessions and client initialization failures safely.
 */
export async function getAuthToken(): Promise<string | null> {
  try {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token || null;
  } catch {
    return null;
  }
}

/**
 * Core fetch wrapper for making calls to the Flask backend API.
 * Automatically injects the active Supabase session access token when available.
 */
export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const url = `${API_BASE_URL.replace(/\/$/, '')}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  const headers = new Headers(options.headers);
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  // Automatically attach active Supabase session access token if not explicitly provided
  if (!headers.has('Authorization')) {
    const token = await getAuthToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const data: ApiResponse<T> = await response.json();
    return data;
  }

  // Gracefully handle non-JSON or proxy failure responses
  if (!response.ok) {
    return {
      success: false,
      error: {
        code: `HTTP_${response.status}`,
        message: response.statusText || 'An error occurred while communicating with the backend API.',
      },
      timestamp: new Date().toISOString(),
    };
  }

  const rawText = await response.text();
  return {
    success: true,
    data: rawText as unknown as T,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Streams deliverable files (PDF, ICS, CSV, JSON) from the backend as Blobs.
 */
export async function apiDownload(
  endpoint: string,
  options: RequestInit = {}
): Promise<{ blob: Blob; filename?: string; mimeType: string }> {
  const url = `${API_BASE_URL.replace(/\/$/, '')}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  const headers = new Headers(options.headers);
  if (!headers.has('Authorization')) {
    const token = await getAuthToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorMessage = response.statusText;
    try {
      const errJson = await response.json();
      errorMessage = errJson.error?.message || errJson.message || errorMessage;
    } catch {
      // Ignore JSON parse failure
    }
    throw new Error(`Download failed (${response.status}): ${errorMessage}`);
  }

  const blob = await response.blob();
  const mimeType = response.headers.get('content-type') || 'application/octet-stream';

  let filename: string | undefined;
  const disposition = response.headers.get('content-disposition');
  if (disposition && disposition.includes('filename=')) {
    const match = disposition.match(/filename="?([^";]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
  }

  return { blob, filename, mimeType };
}

// ============================================================================
// Health API
// ============================================================================

/**
 * Checks the operational health of the Flask backend.
 */
export async function getBackendHealth(): Promise<ApiResponse<BackendHealthData>> {
  return apiFetch<BackendHealthData>('/api/health');
}

// ============================================================================
// Events API
// ============================================================================

export const eventsApi = {
  /**
   * Lists events owned by the authenticated user with optional filtering.
   */
  list(params?: ListEventsParams): Promise<ApiResponse<EventRecord[]>> {
    const qs = buildQueryString(params as Record<string, unknown>);
    return apiFetch<EventRecord[]>(`/api/events${qs}`);
  },

  /**
   * Retrieves a single event by ID.
   */
  get(eventId: string): Promise<ApiResponse<EventRecord>> {
    return apiFetch<EventRecord>(`/api/events/${eventId}`);
  },

  /**
   * Creates a new event owned by the authenticated user.
   */
  create(data: CreateEventInput): Promise<ApiResponse<EventRecord>> {
    return apiFetch<EventRecord>('/api/events', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Updates fields of an existing event owned by the caller.
   */
  update(eventId: string, data: UpdateEventInput): Promise<ApiResponse<EventRecord>> {
    return apiFetch<EventRecord>(`/api/events/${eventId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  /**
   * Deletes an event owned by the caller.
   */
  delete(eventId: string): Promise<ApiResponse<DeleteResponse>> {
    return apiFetch<DeleteResponse>(`/api/events/${eventId}`, {
      method: 'DELETE',
    });
  },

  /**
   * Retrieves preferences for an event.
   */
  getPreferences(eventId: string): Promise<ApiResponse<EventPreferencesRecord>> {
    return apiFetch<EventPreferencesRecord>(`/api/events/${eventId}/preferences`);
  },

  /**
   * Updates or upserts preferences for an event.
   */
  updatePreferences(
    eventId: string,
    data: UpdatePreferencesInput
  ): Promise<ApiResponse<EventPreferencesRecord>> {
    return apiFetch<EventPreferencesRecord>(`/api/events/${eventId}/preferences`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },
};

// ============================================================================
// Budget API
// ============================================================================

export const budgetApi = {
  /**
   * Retrieves aggregated budget summary and category breakdown.
   */
  getSummary(eventId: string): Promise<ApiResponse<BudgetSummary>> {
    return apiFetch<BudgetSummary>(`/api/events/${eventId}/budget/summary`);
  },

  /**
   * Lists budget items for an event with optional category/status filters.
   */
  listItems(
    eventId: string,
    params?: ListBudgetItemsParams
  ): Promise<ApiResponse<BudgetItemRecord[]>> {
    const qs = buildQueryString(params as Record<string, unknown>);
    return apiFetch<BudgetItemRecord[]>(`/api/events/${eventId}/budget/items${qs}`);
  },

  /**
   * Retrieves a single budget item.
   */
  getItem(eventId: string, itemId: string): Promise<ApiResponse<BudgetItemRecord>> {
    return apiFetch<BudgetItemRecord>(`/api/events/${eventId}/budget/items/${itemId}`);
  },

  /**
   * Creates a budget item strictly bound to the target event.
   */
  createItem(
    eventId: string,
    data: CreateBudgetItemInput
  ): Promise<ApiResponse<BudgetItemRecord>> {
    return apiFetch<BudgetItemRecord>(`/api/events/${eventId}/budget/items`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Updates a budget item belonging to the target event.
   */
  updateItem(
    eventId: string,
    itemId: string,
    data: UpdateBudgetItemInput
  ): Promise<ApiResponse<BudgetItemRecord>> {
    return apiFetch<BudgetItemRecord>(`/api/events/${eventId}/budget/items/${itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  /**
   * Deletes a budget item from the event.
   */
  deleteItem(eventId: string, itemId: string): Promise<ApiResponse<DeleteResponse>> {
    return apiFetch<DeleteResponse>(`/api/events/${eventId}/budget/items/${itemId}`, {
      method: 'DELETE',
    });
  },
};

// ============================================================================
// AI Intelligence API
// ============================================================================

export const aiApi = {
  /**
   * Generates a complete event master plan using Gemini and saves a new active revision.
   */
  planEvent(data: PlanEventInput): Promise<ApiResponse<PlanEventResponse>> {
    return apiFetch<PlanEventResponse>('/api/ai/plan-event', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Analyzes current budget items and produces AI cost optimizations.
   */
  optimizeBudget(data: BudgetOptimizeInput): Promise<ApiResponse<AIBudgetOptimization>> {
    return apiFetch<AIBudgetOptimization>('/api/ai/budget-optimize', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};

// ============================================================================
// Venues API
// ============================================================================

export const venuesApi = {
  /**
   * Lists all shortlisted or selected venues for an event.
   */
  list(eventId: string): Promise<ApiResponse<VenueRecord[]>> {
    return apiFetch<VenueRecord[]>(`/api/events/${eventId}/venues`);
  },

  /**
   * Retrieves a single venue candidate.
   */
  get(eventId: string, venueId: string): Promise<ApiResponse<VenueRecord>> {
    return apiFetch<VenueRecord>(`/api/events/${eventId}/venues/${venueId}`);
  },

  /**
   * Creates a new venue candidate for the event.
   */
  create(eventId: string, data: CreateVenueInput): Promise<ApiResponse<VenueRecord>> {
    return apiFetch<VenueRecord>(`/api/events/${eventId}/venues`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Updates a venue, automatically demoting previous selections if is_selected is set.
   */
  update(
    eventId: string,
    venueId: string,
    data: UpdateVenueInput
  ): Promise<ApiResponse<VenueRecord>> {
    return apiFetch<VenueRecord>(`/api/events/${eventId}/venues/${venueId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  /**
   * Deletes a venue candidate.
   */
  delete(eventId: string, venueId: string): Promise<ApiResponse<DeleteResponse>> {
    return apiFetch<DeleteResponse>(`/api/events/${eventId}/venues/${venueId}`, {
      method: 'DELETE',
    });
  },
};

// ============================================================================
// Agenda Sessions API
// ============================================================================

export const agendaApi = {
  /**
   * Lists agenda sessions for an event ordered chronologically.
   */
  list(eventId: string): Promise<ApiResponse<AgendaSessionRecord[]>> {
    return apiFetch<AgendaSessionRecord[]>(`/api/events/${eventId}/agenda`);
  },

  /**
   * Retrieves a single agenda session.
   */
  get(eventId: string, sessionId: string): Promise<ApiResponse<AgendaSessionRecord>> {
    return apiFetch<AgendaSessionRecord>(`/api/events/${eventId}/agenda/${sessionId}`);
  },

  /**
   * Creates a new agenda session enforcing chronological ordering and venue boundaries.
   */
  create(eventId: string, data: CreateSessionInput): Promise<ApiResponse<AgendaSessionRecord>> {
    return apiFetch<AgendaSessionRecord>(`/api/events/${eventId}/agenda`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Updates an existing agenda session.
   */
  update(
    eventId: string,
    sessionId: string,
    data: UpdateSessionInput
  ): Promise<ApiResponse<AgendaSessionRecord>> {
    return apiFetch<AgendaSessionRecord>(`/api/events/${eventId}/agenda/${sessionId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  /**
   * Deletes an agenda session from the event.
   */
  delete(eventId: string, sessionId: string): Promise<ApiResponse<DeleteResponse>> {
    return apiFetch<DeleteResponse>(`/api/events/${eventId}/agenda/${sessionId}`, {
      method: 'DELETE',
    });
  },
};

// ============================================================================
// Tasks API
// ============================================================================

export const tasksApi = {
  /**
   * Lists tasks for an event with optional status/priority filtering.
   */
  list(eventId: string, params?: ListTasksParams): Promise<ApiResponse<TaskRecord[]>> {
    const qs = buildQueryString(params as Record<string, unknown>);
    return apiFetch<TaskRecord[]>(`/api/events/${eventId}/tasks${qs}`);
  },

  /**
   * Retrieves a single task.
   */
  get(eventId: string, taskId: string): Promise<ApiResponse<TaskRecord>> {
    return apiFetch<TaskRecord>(`/api/events/${eventId}/tasks/${taskId}`);
  },

  /**
   * Creates a new task bound to the event.
   */
  create(eventId: string, data: CreateTaskInput): Promise<ApiResponse<TaskRecord>> {
    return apiFetch<TaskRecord>(`/api/events/${eventId}/tasks`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Updates a task belonging to the event.
   */
  update(
    eventId: string,
    taskId: string,
    data: UpdateTaskInput
  ): Promise<ApiResponse<TaskRecord>> {
    return apiFetch<TaskRecord>(`/api/events/${eventId}/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  /**
   * Deletes a task from the event.
   */
  delete(eventId: string, taskId: string): Promise<ApiResponse<DeleteResponse>> {
    return apiFetch<DeleteResponse>(`/api/events/${eventId}/tasks/${taskId}`, {
      method: 'DELETE',
    });
  },
};

// ============================================================================
// Deliverables & Exports API
// ============================================================================

export const exportsApi = {
  /**
   * Lists deliverable export records generated for the event.
   */
  list(eventId: string): Promise<ApiResponse<ExportRecord[]>> {
    return apiFetch<ExportRecord[]>(`/api/events/${eventId}/exports`);
  },

  /**
   * Retrieves metadata for a specific export record.
   */
  get(eventId: string, exportId: string): Promise<ApiResponse<ExportRecord>> {
    return apiFetch<ExportRecord>(`/api/events/${eventId}/exports/${exportId}`);
  },

  /**
   * Triggers generation of an event deliverable (PDF summary, ICS calendar, CSV budget, JSON backup).
   */
  generate(eventId: string, data: GenerateExportInput): Promise<ApiResponse<ExportRecord>> {
    return apiFetch<ExportRecord>(`/api/events/${eventId}/exports`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Downloads the raw deliverable binary file (PDF, ICS, CSV, JSON) as a Blob.
   */
  download(
    eventId: string,
    exportId: string
  ): Promise<{ blob: Blob; filename?: string; mimeType: string }> {
    return apiDownload(`/api/events/${eventId}/exports/${exportId}/download`);
  },

  /**
   * Deletes an export deliverable record and removes its private storage file.
   */
  delete(eventId: string, exportId: string): Promise<ApiResponse<DeleteResponse>> {
    return apiFetch<DeleteResponse>(`/api/events/${eventId}/exports/${exportId}`, {
      method: 'DELETE',
    });
  },
};
