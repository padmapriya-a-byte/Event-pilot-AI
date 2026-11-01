# EventPilot AI

EventPilot AI is an AI-powered autonomous event management and planning platform. It assists organizers with dynamic scheduling, vendor matching, budget optimization, and timeline execution.

---

## Architecture Overview

```
                      +-----------------------------+
                      |       Next.js 16 (App)      |
                      |   TypeScript + Tailwind     |
                      |     (Vercel Frontend)       |
                      +--------------+--------------+
                                     |
               +---------------------+---------------------+
               |                                           |
      (Direct RLS Queries)                     (AI & Server-Side Logic)
               |                                           |
               v                                           v
+-----------------------------+             +-----------------------------+
|          Supabase           |             |        Flask API            |
|  - PostgreSQL Database      |             |  - Python App Factory       |
|  - Supabase Auth            |             |  - Route Blueprints         |
|  - Row Level Security       |<------------|  - Supabase Admin Client    |
+-----------------------------+ (Admin Key) +--------------+--------------+
                                                           |
                                                           v
                                            +-----------------------------+
                                            |      Google Gemini AI       |
                                            |    (gemini-2.5-flash)       |
                                            +-----------------------------+
```

### Security Boundary
- **Client Tier (`frontend/`)**: Only has access to `NEXT_PUBLIC_` environment variables (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`). All database operations pass through Supabase Row-Level Security (RLS).
- **Backend Tier (`backend/`)**: Google Gemini AI and the Supabase Service Role Key are accessed **strictly** on the Python Flask server. The frontend never communicates with Gemini directly.

---

## Monorepo Directory Structure

```text
EventPilot-AI/
├── frontend/                     # Next.js 16 + TypeScript Frontend (Vercel)
│   ├── src/
│   │   ├── app/                  # App Router pages and layouts
│   │   ├── components/           # Reusable UI components
│   │   ├── lib/                  # Supabase client & API client wrappers
│   │   └── types/                # Shared TypeScript definitions
│   ├── public/                   # Static assets
│   ├── .env.example              # Public frontend environment template
│   ├── package.json
│   ├── tsconfig.json
│   └── next.config.ts
│
├── backend/                      # Python Flask Backend API (Render)
│   ├── app/
│   │   ├── __init__.py           # Flask application factory
│   │   ├── config.py             # Environment configuration loader
│   │   ├── routes/               # Blueprint routes (health, future AI routes)
│   │   ├── services/             # Gemini AI & Supabase admin services
│   │   └── utils/                # Standardized errors & auth middleware
│   ├── .env.example              # Server-side environment template
│   ├── requirements.txt          # Python dependencies
│   ├── Procfile                  # Render deployment process definition
│   ├── render.yaml               # Render blueprint specification
│   └── run.py                    # Local development runner
│
├── supabase/                     # Supabase database configuration
│   ├── migrations/               # Version-controlled SQL migration scripts
│   └── README.md                 # Migration & database guidelines
│
├── docs/                         # Project Documentation
│   ├── architecture.md           # System architecture overview
│   └── api-spec.md               # API endpoints specification
│
├── .gitignore                    # Monorepo gitignore (secrets, venvs, node_modules)
└── README.md                     # This documentation
```

---

## Local Development Setup

### 1. Backend Setup (Flask)

1. Navigate to the `backend/` directory:
   ```bash
   cd backend
   ```
2. Activate the virtual environment:
   - **Windows (PowerShell):**
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     source venv/bin/activate
     ```
3. Copy the environment configuration:
   ```bash
   cp .env.example .env
   ```
4. Populate your `.env` with your development keys (`GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`).
5. Run the development server:
   ```bash
   python run.py
   ```
   The backend will be available at `http://localhost:5000` with the health check at `http://localhost:5000/api/health`.

### 2. Frontend Setup (Next.js)

1. Navigate to the `frontend/` directory:
   ```bash
   cd frontend
   ```
2. Copy the environment configuration:
   ```bash
   cp .env.example .env.local
   ```
3. Populate `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` in `.env.local`.
4. Run the development server:
   ```bash
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) to view the application.

---

## Deployment Configuration

### Frontend: Vercel
- **Root Directory:** `frontend`
- **Framework Preset:** Next.js
- **Build Command:** `npm run build`
- **Environment Variables:**
  - `NEXT_PUBLIC_SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
  - `NEXT_PUBLIC_API_URL` (Set to your Render backend URL)

### Backend: Render
- **Root Directory:** `backend`
- **Environment:** Python
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT`
- **Environment Variables:**
  - `FLASK_ENV=production`
  - `CORS_ORIGINS` (Set to your Vercel frontend URL)
  - `GEMINI_API_KEY`
  - `GEMINI_MODEL=gemini-2.5-flash`
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`
