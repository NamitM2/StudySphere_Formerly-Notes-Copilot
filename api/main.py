# api/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router

# Get frontend origin from environment variable
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://notes-copilot.vercel.app")

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    FRONTEND_ORIGIN,
]

app = FastAPI(
    title="Notes Copilot API",
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
