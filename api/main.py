# api/main.py
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Notes Copilot API", version="1.0.0")

# CORS for local UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from api.routes.health import router as health_router
from api.routes.search import router as search_router
from api.routes.documents import router as documents_router

# (Optional) folders router if you created it
try:
    from api.routes.folders import router as folders_router
except Exception:
    folders_router = None

app.include_router(health_router,   prefix="/v1")
app.include_router(search_router,   prefix="/v1")
app.include_router(documents_router, prefix="/v1")
if folders_router:
    app.include_router(folders_router, prefix="/v1")


