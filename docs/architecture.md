# EventPilot AI Architecture Overview

## 1. System Components

EventPilot AI is structured as a decoupled monorepo designed for serverless/cloud-native hosting.

```
+-----------------------------------------------------------+
|                    Client / Browser                       |
|               (Next.js App Router Frontend)               |
+-----------------------------+-----------------------------+
                              |
              +---------------+---------------+
              |                               |
       (Direct Auth & RLS Data)     (AI & Complex Operations)
              |                               |
              v                               v
+-----------------------------+ +-----------------------------+
|          Supabase           | |        Flask Backend        |
|  - PostgreSQL Database      | |  - App Factory (run.py)     |
|  - Supabase Auth            | |  - Route Blueprints         |
|  - Row Level Security (RLS) | |  - Supabase Admin Client    |
|  - Storage & Realtime       | |  - Gemini AI Client         |
+-----------------------------+ +--------------+--------------+
                                               |
                                               v
                                +-----------------------------+
                                |      Google Gemini AI       |
                                |  (gemini-2.5-flash / pro)   |
                                +-----------------------------+
```

## 2. Security & Credential Boundary

- **Client Tier (`frontend/`)**:
  - Only accesses `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
  - All database queries performed from the frontend pass through Supabase Row Level Security (RLS).
  - Never handles Gemini API keys or the Supabase Service Role key.

- **Server Tier (`backend/`)**:
  - The Python Flask backend is the single authorized gateway to the Google Gemini AI API.
  - Maintains `GEMINI_API_KEY` and `SUPABASE_SERVICE_ROLE_KEY` in environment variables strictly server-side.
  - Validates Supabase JWT bearer tokens forwarded from Next.js requests before processing protected actions.

## 3. Deployment Targets

- **Frontend**: Vercel
  - Framework preset: Next.js
  - Root directory: `frontend`
- **Backend**: Render
  - Environment: Python
  - Build command: `pip install -r requirements.txt`
  - Start command: `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT`
  - Root directory: `backend`
