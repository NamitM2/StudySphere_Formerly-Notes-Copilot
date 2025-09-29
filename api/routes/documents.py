# api/routes/documents.py
from __future__ import annotations
from typing import List, Dict
from fastapi import APIRouter, UploadFile, File, HTTPException

from core.pdf import extract_text_from_pdf
from core.chunk import split_text
from api.dependencies import embed_chunks, vector_index

router = APIRouter()

# super-simple in-memory catalog for dev
DOCUMENTS: List[Dict] = []


@router.get("/documents")
def list_documents():
    return {"documents": DOCUMENTS}


@router.delete("/documents")
def clear_documents():
    DOCUMENTS.clear()
    vector_index.index.reset()
    vector_index.chunks.clear()
    return {"ok": True}


@router.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    if file.content_type not in ("application/pdf", "application/x-pdf", "binary/octet-stream"):
        raise HTTPException(status_code=400, detail="Please upload a PDF.")

    pdf_bytes = await file.read()
    pages = extract_text_from_pdf(pdf_bytes)
    if not pages or not any(p.strip() for p in pages):
        raise HTTPException(status_code=400, detail="No extractable text found in PDF.")

    full_text = "\n".join(pages)
    chunks = split_text(full_text)
    if not chunks:
        raise HTTPException(status_code=400, detail="Failed to chunk text.")

    vecs = embed_chunks(chunks)           # shape [N, dim]
    vector_index.add(vecs, chunks)        # add to FAISS + store chunk texts

    doc = {"id": f"doc_{len(DOCUMENTS)+1}", "filename": file.filename, "num_chunks": len(chunks)}
    DOCUMENTS.append(doc)
    return {"document": doc, "added_chunks": len(chunks)}
