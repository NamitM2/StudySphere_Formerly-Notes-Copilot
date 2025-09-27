# api/main.py

from fastapi import FastAPI
from api.routes import health, search

app = FastAPI(
    title="Notes Copilot API",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(search.router, prefix="/v1")