# EventPilot AI API Specification (Phase 1 Baseline)

Base URL (Local): `http://localhost:5000`
Base URL (Production): Configured via Render host

## 1. Conventions
- All response bodies are formatted as JSON with a consistent envelope:
  ```json
  {
    "success": true,
    "data": {},
    "message": "Optional descriptive message",
    "timestamp": "2026-10-22T21:00:00Z"
  }
  ```
- Error responses:
  ```json
  {
    "success": false,
    "error": {
      "code": "ERROR_CODE",
      "message": "Human-readable description",
      "details": null
    },
    "timestamp": "2026-10-22T21:00:00Z"
  }
  ```

## 2. Health & Foundation Endpoints

### GET `/api/health`
Checks backend operational status, runtime info, and environment configuration health.

- **Request**:
  - Method: `GET`
  - Headers: None required
- **Response `200 OK`**:
  ```json
  {
    "success": true,
    "data": {
      "status": "healthy",
      "service": "EventPilot-AI Backend",
      "environment": "development",
      "version": "1.0.0",
      "gemini_configured": false,
      "supabase_configured": false
    },
    "timestamp": "2026-10-22T21:00:00Z"
  }
  ```

## 3. Planned Endpoints (Phase 2+)
- `POST /api/ai/plan-event`: AI-assisted event schedule and milestone generation (Gemini)
- `POST /api/ai/budget-optimize`: AI budget breakdown and recommendation (Gemini)
- `POST /api/ai/vendor-match`: Vendor recommendation and RFQ drafting (Gemini)
