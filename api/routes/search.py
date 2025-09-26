from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
from core.pdf import pdf_bytes_to_texts
from core.chunk import split_text

router = APIRouter()

class Query(BaseModel):
    q: str
    k: int = 5

@router.post("/ingest")
async def ingest(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Upload a PDF or text file.
    - PDF: extract page texts, then split into chunks.
    - TXT/MD: read bytes as utf-8, then split into chunks.
    Returns counts so we can verify the pipeline is alive.
    """
    data = await file.read()
    name = (file.filename or "").lower()

    if name.endswith(".pdf"):
        pages: List[str] = pdf_bytes_to_texts(data)
        if not pages:
            raise HTTPException(status_code=400, detail="No text extracted from PDF.")
        chunks: List[str] = []
        for p in pages:
            chunks.extend(split_text(p, max_chars=800))
        return {
            "ok": True,
            "filename": file.filename,
            "filetype": "pdf",
            "pages": len(pages),
            "chunks": len(chunks)
        }

    elif name.endswith(".txt") or name.endswith(".md"):
        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Decode error: {e}")
        chunks = split_text(text, max_chars=800)
        return {
            "ok": True,
            "filename": file.filename,
            "filetype": "text",
            "chunks": len(chunks)
        }

    else:
        raise HTTPException(status_code=415, detail="Unsupported file type. Use .pdf, .txt, or .md.")

@router.post("/search")
async def search(query: Query):
    # Retrieval + answer composing will be added after we build an index.
    return {"answer": "TODO", "citations": []}
