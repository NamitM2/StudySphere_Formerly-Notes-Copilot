# api/main.py
# Path: api/main.py
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Notes Copilot API",
    docs_url="/api/swagger",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

# ✅ IMPORTANT: explicit origins when allow_credentials=True
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],      # GET, POST, DELETE, OPTIONS, ...
    allow_headers=["*"],      # include Authorization, Content-Type, etc.
    expose_headers=[],        # optional
    max_age=600,              # optional; cache preflight for 10 min
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# your existing router with /health, /upload, /docs, /search, /ask
from api.routes import router as api_router

app = FastAPI(
    title="Notes Copilot API",
    docs_url="/api/swagger",        # Swagger moved under /api
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IMPORTANT: this puts ALL your existing routes under /api/...
# e.g. /health -> /api/health, /docs -> /api/docs
app.include_router(api_router, prefix="/api")
