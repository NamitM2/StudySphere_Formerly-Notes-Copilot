# api/routes/search.py

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from core.pdf import extract_text_from_pdf
from core.chunk import split_text
from core.embed import embed_chunks
from api.dependencies import vector_index

class SearchRequest(BaseModel):
    query: str

router = APIRouter()

@router.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    try:
        pdf_bytes = await file.read()
        pages = extract_text_from_pdf(pdf_bytes)
        if not pages:
            raise HTTPException(status_code=404, detail="No text found in PDF.")
        
        full_text = "\n".join(pages)
        chunks = split_text(full_text)
        embeddings = embed_chunks(chunks)
        
        vector_index.add(embeddings=embeddings, chunks=chunks)
        
        return {
            "ok": True,
            "filename": file.filename,
            "chunks_added": len(chunks),
            "vectors_in_index": vector_index.index.ntotal
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@router.post("/search")
async def search(request: SearchRequest):
    """
    Receives a query, embeds it, searches the index, and returns the top results.
    """
    # 1. Embed the user's query.
    query_embedding = embed_chunks([request.query])[0]
    
    # 2. Search the vector index for the top 3 most similar chunks.
    results = vector_index.search(query_vector=query_embedding, k=3)
    
    # 3. Return the results.
    return {
        "ok": True,
        "results": results
    }