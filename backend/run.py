"""EventPilot AI - Local Development Runner.

Usage:
    python run.py
"""

from app import create_app
from app.config import Config

app = create_app()

if __name__ == "__main__":
    print(f"Starting EventPilot AI backend on port {Config.PORT}...")
    print(f"CORS origins allowed: {Config.CORS_ORIGINS}")
    print(f"Gemini configured: {Config.is_gemini_configured()}")
    print(f"Supabase configured: {Config.is_supabase_configured()}")
    app.run(
        host="0.0.0.0",
        port=Config.PORT,
        debug=Config.DEBUG,
    )
