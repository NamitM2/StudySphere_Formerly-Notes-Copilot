# api/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router
from api.routes_v2.ide_routes import router as ide_router
from api.routes_v2.worksheet_routes import router as worksheet_router
from core.background_worker import start_worker
from api.config_validator import validate_startup_config

# Validate configuration on startup
validate_startup_config(exit_on_failure=True)

# Get frontend origin from environment variable
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://notes-copilot.vercel.app")

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    FRONTEND_ORIGIN,
]

app = FastAPI(
    title="StudySphere API",
    description="Intelligent document analysis and learning platform with AI-powered Q&A, visual understanding, and assignment assistance",
    version="1.0.0",
    docs_url="/api/swagger",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[],
    max_age=600,
)

# IMPORTANT: this puts ALL your existing routes under /api/...
# e.g. /health -> /api/health, /docs -> /api/docs
app.include_router(api_router, prefix="/api")

# NEW: Assignment IDE routes
app.include_router(ide_router, prefix="/api")

# NEW: Worksheet routes
app.include_router(worksheet_router, prefix="/api")

# Start background worker for async document processing
start_worker()

# Warm up critical dependencies to avoid cold start on first request
@app.on_event("startup")
async def startup_warmup():
    """
    Pre-initialize expensive dependencies during server startup.
    This eliminates the ~5-10 second cold start penalty on first request.
    """
    import asyncio

    def _warmup():
        print("[STARTUP] Warming up Gemini SDK and embeddings...")
        try:
            # Import and fully warm up embedding system with test API call
            from core.embeddings import warmup_embeddings
            # This will initialize Gemini SDK AND make a test API call
            # to fully warm up the connection for fast first upload
            warmup_embeddings()
        except Exception as e:
            print(f"[STARTUP] Warning: Failed to warm up embeddings: {e}")

        try:
            # Pre-configure Gemini text generation
            import google.generativeai as genai
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                print("[STARTUP] Gemini text generation ready!")
        except Exception as e:
            print(f"[STARTUP] Warning: Failed to warm up text generation: {e}")

    # Run warmup in background thread to not block startup
    await asyncio.to_thread(_warmup)
    print("[STARTUP] Server warmup complete!")
