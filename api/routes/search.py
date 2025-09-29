# api/routes/search.py
from __future__ import annotations
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.dependencies import embed_chunks, vector_index
from core.generation import generate_json_answer

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    enrich: bool = True
    debug: bool = False


@router.post("/search")
def search(req: SearchRequest):
    """
    Semantic search + LLM answer.
    Returns {"answer": str} and, when debug=True, also {"contexts": [str]}.
    """
    # 1) embed the query
    qv = embed_chunks([req.query])[0]

    # 2) retrieve contexts with MMR inside the index
    contexts: List[str] = vector_index.search(query_vector=qv, k=5, diversity=0.75)

    # 3) generate
    answer = generate_json_answer(
        question=req.query,
        contexts=contexts,
        allow_enrichment=req.enrich,
    )

    if req.debug:
        return {"answer": answer, "contexts": contexts}
    return {"answer": answer}
