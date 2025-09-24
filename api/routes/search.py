from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel

router = APIRouter()

class Query(BaseModel):
    q: str
    k: int = 5

@router.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    # We'll implement this after the server runs
    return {"ok": True, "filename": file.filename}

@router.post("/search")
async def search(query: Query):
    # We'll implement retrieval next
    return {"answer": "TODO", "citations": []}
