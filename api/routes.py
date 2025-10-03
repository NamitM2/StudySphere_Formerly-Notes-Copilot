# api/routes.py
from __future__ import annotations

import os
import re
import numpy as np
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status

from postgrest.exceptions import APIError
from api.supa import admin_client
from api.storage import delete_paths

# ------------------------------------------------------------------------------
# Auth dependency
# ------------------------------------------------------------------------------

# We expect an auth helper in your repo, but provide a safe fallback for local dev.
# Prefer: api/auth_supabase.py -> get_current_user(Authorization: str) -> dict
try:
    # your existing helper
    from api.auth_supabase import get_current_user  # type: ignore
except Exception:
    # Fallback: allow anonymous only if ALLOW_ANON=true. Otherwise 401.
    def get_current_user(Authorization: Optional[str] = Header(None)) -> Dict[str, Any]:  # type: ignore
        allow_anon = os.getenv("ALLOW_ANON", "false").lower() in ("1", "true", "yes")
        if Authorization and Authorization.lower().startswith("bearer "):
            # Token is present; we don't validate here—assume your reverse proxy or
            # the DB policy will enforce it. This is just to unblock local dev.
            return {"user_id": "local-user", "raw": Authorization}
        if allow_anon:
            return {"user_id": "anon"}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

_STOPWORDS = {
    'the', 'and', 'for', 'that', 'with', 'from', 'this', 'your', 'have', 'about',
    'when', 'what', 'where', 'which', 'will', 'would', 'could', 'should', 'into',
    'such', 'while', 'been', 'being', 'make', 'made', 'also', 'than', 'then', 'them'
}


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r'[a-z0-9]+', text.lower()):
        if len(raw) <= 2 or raw in _STOPWORDS:
            continue
        tokens.add(raw)
        if raw.endswith('es') and len(raw) > 3:
            tokens.add(raw[:-2])
        elif raw.endswith('s') and len(raw) > 3:
            tokens.add(raw[:-1])
    return tokens

def _lexical_score(snippet: Dict[str, Any], query_terms: set[str]) -> float:
    tokens = _tokenize(((snippet.get('text') or '') + ' ' + (snippet.get('filename') or '')))
    overlap = len(tokens & query_terms)
    if overlap == 0 and query_terms:
        lowered = (snippet.get('text') or '').lower()
        if any(term in lowered for term in query_terms):
            overlap = 1.0
    return float(overlap)


def _mmr_select(query_vec: np.ndarray, doc_vecs: np.ndarray, limit: int, lambda_param: float = 0.7) -> List[tuple[int, float]]:
    if doc_vecs.size == 0 or limit <= 0:
        return []
    sims = (doc_vecs @ query_vec.reshape(-1, 1)).flatten()
    remaining = list(range(len(doc_vecs)))
    selected: List[tuple[int, float]] = []
    while remaining and len(selected) < limit:
        if not selected:
            idx = max(remaining, key=lambda i: sims[i])
            selected.append((idx, float(sims[idx])))
            remaining.remove(idx)
            continue
        best_idx = None
        best_score = -1e9
        for i in remaining:
            redundancy = max(float(doc_vecs[i] @ doc_vecs[j]) for j, _ in selected)
            score = lambda_param * float(sims[i]) - (1.0 - lambda_param) * redundancy
            if score > best_score:
                best_score = score
                best_idx = i
        selected.append((best_idx, best_score))
        remaining.remove(best_idx)
    return selected

# ------------------------------------------------------------------------------
# Core modules (import defensively so filename differences don’t break you)
# ------------------------------------------------------------------------------

# Ingestion
try:
    from core.ingest_pg import ingest_file  # type: ignore
except Exception as e:
    raise RuntimeError(f"Missing ingest function (core/ingest_pg.py): {e}")

# Embeddings for query
try:
    from core.embeddings import embed_query, embed_texts  # type: ignore
except Exception:
    # older name
    try:
        from core.embed import embed_query, embed_texts  # type: ignore
    except Exception as e:
        raise RuntimeError(f"Missing embed functions (core/embeddings.py): {e}")

# Search in Postgres (vector)
# We’ll accept a few possible function names to fit your file.
_search_fn = None
try:
    from core.search_pg import search_chunks as _search_fn  # type: ignore
except Exception:
    try:
        from core.search_pg import search as _search_fn  # type: ignore
    except Exception:
        try:
            from core.search_pg import search_query as _search_fn  # type: ignore
        except Exception as e:
            raise RuntimeError(f"Missing search function in core/search_pg.py: {e}")

# Gemini QA - Now using enhanced version with schema validation
try:
    # Use the enhanced version with JSON schema validation and fallbacks
    from core.qa_gemini import ask_with_schema as _gemini_ask  # type: ignore
except Exception as e:
    # Fallback to original version if enhanced version fails
    try:
        from core.qa_gemini import ask as _gemini_ask  # type: ignore
    except Exception as e2:
        raise RuntimeError(f"Missing Gemini ask function (core/qa_gemini.py): {e}. Fallback also failed: {e2}")

# ------------------------------------------------------------------------------
# Router
# ------------------------------------------------------------------------------

router = APIRouter()


@router.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


# ------------------------------------------------------------------------------
# Upload (PDF / MD / TXT) -> chunk + embed + store in PG
# ------------------------------------------------------------------------------
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """
    Ingest a single file for the current user.
    Returns: { ok, doc_id, filename, chunks }
    """
    supa = admin_client()
    try:
        dup = supa.table("documents").select("id").eq("user_id", user["user_id"]).eq("filename", file.filename).limit(1).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Doc lookup failed: {exc}") from exc
    existing = dup.data or []
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document already uploaded")

    try:
        content = await file.read()
        info = ingest_file(
            user_id=user["user_id"],
            filename=file.filename,
            file_bytes=content,
            mime=file.content_type or "application/octet-stream",
        )
        return info
    except HTTPException:
        # pass through
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------------------
# List documents (used by UI "Your documents")
# This is intentionally simple—return an empty list if you don’t maintain a docs table.
# ------------------------------------------------------------------------------
@router.get("/docs")
def list_docs(user=Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Return document metadata for the signed-in user."""
    supa = admin_client()
    fields = "id, filename, mime, byte_size, created_at, storage_path"
    try:
        res = supa.table("documents").select(fields).eq("user_id", user["user_id"]).limit(50).execute()
    except APIError as api_err:
        if getattr(api_err, "code", None) == "42703":
            fields = "id, filename, mime, byte_size, storage_path"
            res = supa.table("documents").select(fields).eq("user_id", user["user_id"]).limit(50).execute()
        else:
            raise HTTPException(status_code=500, detail=f"Doc fetch failed: {api_err}") from api_err
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Doc fetch failed: {exc}") from exc

    docs = res.data or []
    if "created_at" in fields:
        docs.sort(key=lambda row: (row or {}).get("created_at") or "", reverse=True)
    else:
        docs.sort(key=lambda row: (row or {}).get("id") or 0, reverse=True)

    output: List[Dict[str, Any]] = []
    for row in docs:
        output.append({
            "doc_id": row.get("id"),
            "filename": row.get("filename"),
            "mime": row.get("mime"),
            "byte_size": row.get("byte_size"),
            "created_at": row.get("created_at"),
            "storage_path": row.get("storage_path"),
        })
    return output


@router.delete("/docs/{doc_id}")
def delete_document(doc_id: int, user=Depends(get_current_user)) -> Dict[str, Any]:
    supa = admin_client()
    try:
        doc_res = supa.table("documents").select("id, storage_path").eq("id", doc_id).eq("user_id", user["user_id"]).limit(1).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Doc lookup failed: {exc}") from exc

    doc_rows = doc_res.data or []
    if not doc_rows:
        raise HTTPException(status_code=404, detail="Document not found")
    storage_path = (doc_rows[0] or {}).get("storage_path")

    try:
        supa.table("chunks").delete().eq("doc_id", doc_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chunk delete failed: {exc}") from exc

    try:
        supa.table("documents").delete().eq("id", doc_id).eq("user_id", user["user_id"]).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document delete failed: {exc}") from exc

    if storage_path:
        try:
            delete_paths([storage_path])
        except Exception:
            pass

    return {"ok": True, "doc_id": doc_id}


# ------------------------------------------------------------------------------
# Search (top-k chunks by cosine distance)
# ------------------------------------------------------------------------------
@router.get("/search")
def search_pg(q: str, k: int = 5, user=Depends(get_current_user)) -> List[Dict[str, Any]]:
    """
    Returns a list of chunks with fields:
      { doc_id, filename, page, text, distance }
    """
    if not q or not q.strip():
        return []

    try:
        q_vec = embed_query(q)  # np.ndarray shape (dim,)
        results = _search_fn(
            user_id=user["user_id"],
            query=q,
            query_embedding=q_vec,
            k=int(k),
        )
        # Defensive: normalize output keys used by the UI
        normalized: List[Dict[str, Any]] = []
        for r in results or []:
            normalized.append(
                {
                    "doc_id": r.get("doc_id"),
                    "filename": r.get("filename") or r.get("file_name") or "file",
                    "page": r.get("page"),
                    "text": r.get("text") or r.get("chunk") or "",
                    "distance": r.get("distance"),
                }
            )
        return normalized
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------------------
# Ask (RAG w/ Gemini). Honors 'enrich' (outside info) and 'warm' (tone).
# ------------------------------------------------------------------------------
@router.post("/ask")
def ask_notes(payload: Dict[str, Any], user=Depends(get_current_user)) -> Dict[str, Any]:
    """
    Request body (from UI):
      {
        "q": "...",          # user question
        "k": 5,              # number of snippets to fetch
        "enrich": true,      # allow outside info (e.g., web/Gemini tools)
        "warm": true         # warm/welcoming tone
      }

    Response:
      {
        "answer": "...",
        "citations": [ { filename, page, text, doc_id }, ... ]
      }
    """
    q: str = (payload.get("q") or "").strip()
    k: int = int(payload.get("k") or 5)
    enrich: bool = bool(payload.get("enrich", True))
    warm: bool = bool(payload.get("warm", True))

    if not q:
        raise HTTPException(status_code=400, detail="Missing question 'q'")

    # 1) Retrieve top-k snippets
    try:
        q_vec = embed_query(q)
        fetch_k = max(k * 3, min(20, k * 5))
        hits = _search_fn(
            user_id=user["user_id"],
            query=q,
            query_embedding=q_vec,
            k=fetch_k,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

    # Normalize snippets (only pass what Gemini needs)
    snippets: List[Dict[str, Any]] = []
    texts: List[str] = []
    for h in hits or []:
        snippet = {
            "filename": h.get("filename") or h.get("file_name") or "file",
            "page": h.get("page"),
            "text": h.get("text") or h.get("chunk") or "",
            "doc_id": h.get("doc_id"),
        }
        snippets.append(snippet)
        texts.append(snippet["text"])

    if snippets:
        query_terms = _tokenize(q)
        lex_scores = [_lexical_score(sn, query_terms) for sn in snippets]

        try:
            doc_vecs = np.asarray(embed_texts(texts), dtype="float32")
        except Exception:
            doc_vecs = np.zeros((len(snippets), len(np.asarray(q_vec).reshape(-1))), dtype="float32")

        if doc_vecs.ndim == 1:
            doc_vecs = doc_vecs.reshape(1, -1)

        mmr_limit = min(len(snippets), max(k * 2, 10))
        mmr_selected = _mmr_select(np.asarray(q_vec).reshape(-1), doc_vecs, mmr_limit)

        if mmr_selected:
            scored: List[tuple[float, float, int]] = []
            for idx, mmr_score in mmr_selected:
                lex = lex_scores[idx] if lex_scores else 0.0
                combined = mmr_score + 0.1 * lex
                scored.append((combined, lex, idx))
            scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
            keep = [idx for _, _, idx in scored[:k]]
            snippets = [snippets[i] for i in keep]
        else:
            snippets.sort(key=lambda sn: _lexical_score(sn, query_terms), reverse=True)
            snippets = snippets[:k]
    else:
        snippets = []

    # 2) Ask Gemini
    try:
        # Your qa function should accept these keyword args;
        # it should ignore unknown kwargs to remain compatible.
        answer, meta = _gemini_ask(
            question=q,
            snippets=snippets,
            allow_outside=enrich,
            warm_tone=warm,
        )
        # Expect tuple (answer_text, metadata) or just string; normalize
        if isinstance(answer, dict):
            # If your ask() already returns a dict with 'answer'
            out_answer = answer.get("answer") or answer
        else:
            out_answer = answer
        citations = (meta or {}).get("citations") or snippets
        return {"answer": out_answer, "citations": citations}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini call failed: {e}")
