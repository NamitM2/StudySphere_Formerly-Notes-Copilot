from fastapi import FastAPI
from api.routes.health import router as health_router
from api.routes.search import router as search_router

app = FastAPI(title="Notes Copilot API", version="0.1.0")

# routes
app.include_router(health_router)
app.include_router(search_router, prefix="/v1")
