# api/routes/search.py

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from core.pdf import extract_text_from_pdf
from core.chunk import split_text
from core.embed import embed_chunks
from core.generation import generate_answer
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
    # Step 1: Retrieve relevant chunks (the "context"). We use k=5 to get more context.
    context_chunks = vector_index.search(query_vector=embed_chunks([request.query])[0], k=5)
    
    # Step 2: Generate a conversational answer using the retrieved context.
    answer = generate_answer(query=request.query, context=context_chunks)
    
    # Step 3: Return the single, generated answer.
    return {
        "ok": True,
        "answer": answer
    }

@router.post("/clear")
async def clear_index():
    vector_index.clear()
    return {"ok": True, "message": "Index cleared successfully."}