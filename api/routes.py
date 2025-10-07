# api/routes.py
# Enrichment support with mode detection
from __future__ import annotations

import os
import re
import numpy as np
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from postgrest.exceptions import APIError

from api.supa import admin_client
from api.storage import delete_paths

# ----------------------------------------------------------------------
# Auth dependency
# ----------------------------------------------------------------------
try:
    # Prefer your real helper (HS256/RS256/hybrid).
    from api.auth_supabase import get_current_user  # type: ignore
except Exception:
    # Safe local fallback (dev only). DO NOT ship to prod.
    from typing import Optional, Dict, Any
    from fastapi import Header, HTTPException, status, Request

    ALLOW_ANON = os.getenv("ALLOW_ANON", "false").lower() in ("1", "true", "yes")
    DEV_ENV = os.getenv("ENV", "dev").lower() in ("dev", "development")

    def _is_localhost(req: Request) -> bool:
        host = (req.client.host if req and req.client else None) or ""
        return host in ("127.0.0.1", "::1", "localhost")

    def _die(detail: str) -> None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    async def get_current_user(
        Authorization: Optional[str] = Header(None),
        request: Request = None,
) -> Dict[str, Any]:  # type: ignore
        if Authorization:
            _die("Bearer token present but validator unavailable")

        if ALLOW_ANON and DEV_ENV and _is_localhost(request):
            return {"user_id": "anon", "raw": None}
        _die("Missing bearer token")



_STOPWORDS = {
    "the","and","for","that","with","from","this","your","have","about",
    "when","what","where","which","will","would","could","should","into",
    "such","while","been","being","make","made","also","than","then","them"
}

def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[a-z0-9]+", text.lower()):
        if len(raw) <= 2 or raw in _STOPWORDS:
            continue
        tokens.add(raw)
        if raw.endswith("es") and len(raw) > 3:
            tokens.add(raw[:-2])
        elif raw.endswith("s") and len(raw) > 3:
            tokens.add(raw[:-1])
    return tokens

def _lexical_score(snippet: Dict[str, Any], query_terms: set[str]) -> float:
    tokens = _tokenize(((snippet.get("text") or "") + " " + (snippet.get("filename") or "")))
    overlap = len(tokens & query_terms)
    if overlap == 0 and query_terms:
        lowered = (snippet.get("text") or "").lower()
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
        selected.append((best_idx, best_score))  # type: ignore[arg-type]
        remaining.remove(best_idx)               # type: ignore[arg-type]
    return selected

def _detect_answer_mode(answer: str, min_distance: float) -> str:
    """
    Detect the answer mode based on content and document relevance.

    Returns:
    - "notes_only": Answer from notes only (show "From Notes" tag)
    - "mixed": Answer with notes + enrichment (show both tags)
    - "model_only": Answer from model knowledge only (show "Model Knowledge" tag)
    """
    answer_lower = answer.lower() if isinstance(answer, str) else ""

    # Check if answer explicitly says it's not in notes
    has_not_found_phrase = (
        ("couldn't find" in answer_lower or "could not find" in answer_lower or
         "can't find" in answer_lower or "cannot find" in answer_lower)
        and "notes" in answer_lower
    )

    # Check if answer has enrichment marker
    has_enrichment = "<<<ENRICHMENT_START>>>" in answer

    # Check if retrieved documents are actually relevant (distance < 0.5 = reasonably similar)
    # Note: Lower distance = more similar. Typical range: 0.0 (identical) to 1.0 (completely different)
    has_relevant_docs = min_distance < 0.5

    # Determine mode
    if has_not_found_phrase or not has_relevant_docs:
        return "model_only"
    elif has_enrichment:
        return "mixed"
    else:
        return "notes_only"

# ----------------------------------------------------------------------
# Core modules (import defensively)
# ----------------------------------------------------------------------
try:
    from core.ingest_pg import ingest_file  # type: ignore
except Exception as e:
    raise RuntimeError(f"Missing ingest function (core/ingest_pg.py): {e}")

try:
    from core.embeddings import embed_query, embed_texts  # type: ignore
except Exception:
    try:
        from core.embed import embed_query, embed_texts  # type: ignore
    except Exception as e:
        raise RuntimeError(f"Missing embed functions (core/embeddings.py): {e}")

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

try:
    from core.qa_gemini import ask_with_schema as _gemini_ask  # type: ignore
except Exception:
    try:
        from core.qa_gemini import ask as _gemini_ask  # type: ignore
    except Exception as e2:
        raise RuntimeError(f"Missing Gemini ask function (core/qa_gemini.py): {e2}")

# ----------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------
router = APIRouter()

@router.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}

# ----------------------------------------------------------------------
# Upload -> chunk + embed + store in PG
# ----------------------------------------------------------------------
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """
    Ingest a single file for the current user.
    Returns: { ok, doc_id, filename, chunks }
    """
    # Basic content-type check (extension fallback is handled in ingest_file)
    allowed_types = {"application/pdf", "text/markdown", "text/plain"}
    if (file.content_type not in allowed_types
        and not (file.filename or "").lower().endswith((".pdf", ".md", ".txt"))):
        raise HTTPException(status_code=400, detail="Only PDF, Markdown (.md), and Text (.txt) files are supported.")

    # Ensure DB is reachable
    try:
        supa = admin_client()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {exc}") from exc

    # Block duplicate filename for same user (optional policy)
    try:
        dup = supa.table("documents").select("id").eq("user_id", user["user_id"]).eq("filename", file.filename).limit(1).execute()
        if (dup.data or []):
            raise HTTPException(status_code=409, detail="Document already uploaded")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database lookup failed: {exc}") from exc

    # Read file and enforce size (200MB) after read
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(content) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 200MB)")

    try:
        info = ingest_file(
            user_id=user["user_id"],
            filename=file.filename,
            file_bytes=content,
            mime=file.content_type or "application/octet-stream",
        )
        # Expect info like: {"ok":True,"doc_id":..,"filename":..,"chunks":..}
        return info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File processing failed: {e}")

# ----------------------------------------------------------------------
# List documents
# ----------------------------------------------------------------------
@router.get("/docs")
def list_docs(user=Depends(get_current_user)) -> List[Dict[str, Any]]:
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

    out: List[Dict[str, Any]] = []
    for row in docs:
        out.append({
            "doc_id": row.get("id"),
            "filename": row.get("filename"),
            "mime": row.get("mime"),
            "byte_size": row.get("byte_size"),
            "created_at": row.get("created_at"),
            "storage_path": row.get("storage_path"),
        })
    return out

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
        supa.table("documents").delete().eq("id", doc_id).eq("user_id", user["user_id"]).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}") from exc

    if storage_path:
        try:
            delete_paths([storage_path])
        except Exception:
            pass

    return {"ok": True, "doc_id": doc_id}

# ----------------------------------------------------------------------
# Search (top-k chunks by cosine distance)
# ----------------------------------------------------------------------
@router.get("/search")
def search_pg(q: str, k: int = 5, user=Depends(get_current_user)) -> List[Dict[str, Any]]:
    if not q or not q.strip():
        return []
    if len(q.strip()) > 1000:
        raise HTTPException(status_code=400, detail="Query too long (max 1000)")
    if len(q.strip()) < 3:
        raise HTTPException(status_code=400, detail="Query too short (min 3)")
    if k < 1 or k > 20:
        raise HTTPException(status_code=400, detail="k must be between 1 and 20")

    try:
        q_vec = embed_query(q)  # np.ndarray (dim,)
        results = _search_fn(
            user_id=user["user_id"],
            query=q,
            query_embedding=q_vec,
            k=int(k),
        )
        normalized: List[Dict[str, Any]] = []
        for r in results or []:
            normalized.append({
                "doc_id": r.get("doc_id"),
                "filename": r.get("filename") or r.get("file_name") or "file",
                "page": r.get("page"),
                "text": r.get("text") or r.get("chunk") or "",
                "distance": r.get("distance"),
            })
        return normalized
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------------------------------------------------------
# History endpoints
# ----------------------------------------------------------------------
@router.get("/history")
def get_history(limit: int = 50, user=Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Get user's Q&A history, most recent first."""
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")

    supa = admin_client()
    try:
        res = supa.table("qa_history")\
            .select("id, question, answer, citations, created_at")\
            .eq("user_id", user["user_id"])\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()

        history = res.data or []
        return history
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"History fetch failed: {exc}") from exc

# ----------------------------------------------------------------------
# Ask (RAG w/ Gemini)
# ----------------------------------------------------------------------
@router.post("/ask")
def ask_notes(payload: Dict[str, Any], user=Depends(get_current_user)) -> Dict[str, Any]:
    q: str = (payload.get("q") or "").strip()
    k: int = int(payload.get("k") or 5)
    enrich: bool = bool(payload.get("enrich", True))
    warm: bool = bool(payload.get("warm", True))

    if not q:
        raise HTTPException(status_code=400, detail="Missing question 'q'")
    if len(q) > 1000:
        raise HTTPException(status_code=400, detail="Question too long (max 1000)")
    if len(q) < 3:
        raise HTTPException(status_code=400, detail="Question too short (min 3)")
    if k < 1 or k > 20:
        raise HTTPException(status_code=400, detail="k must be between 1 and 20")

    try:
        q_vec = embed_query(q)
        fetch_k = max(k * 3, min(20, k * 5))
        hits = _search_fn(user_id=user["user_id"], query=q, query_embedding=q_vec, k=fetch_k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

    snippets: List[Dict[str, Any]] = []
    texts: List[str] = []
    min_distance = float('inf')  # Track minimum distance for citation detection

    for h in hits or []:
        distance = h.get("distance")
        if distance is not None and distance < min_distance:
            min_distance = distance
        sn = {
            "filename": h.get("filename") or h.get("file_name") or "file",
            "page": h.get("page"),
            "text": h.get("text") or h.get("chunk") or "",
            "doc_id": h.get("doc_id"),
        }
        snippets.append(sn)
        texts.append(sn["text"])

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

    try:
        answer, meta = _gemini_ask(
            question=q,
            snippets=snippets,
            allow_outside=enrich,
            warm_tone=warm,
        )
        out_answer = answer.get("answer") if isinstance(answer, dict) else answer

        # Determine answer mode based on content and relevance
        effective_min_distance = min_distance if min_distance != float('inf') else 1.0
        answer_mode = _detect_answer_mode(out_answer, effective_min_distance)

        # Process answer based on mode
        notes_part = ""
        enrichment_part = ""

        if answer_mode == "mixed" and "<<<ENRICHMENT_START>>>" in out_answer:
            # Split answer into notes and enrichment parts
            parts = out_answer.split("<<<ENRICHMENT_START>>>", 1)
            notes_part = parts[0].strip()
            enrichment_part = parts[1].strip() if len(parts) > 1 else ""
            # Clean answer removes the marker
            out_answer = notes_part + "\n\n" + enrichment_part if enrichment_part else notes_part

        # Determine citations based on mode
        citations = []
        if answer_mode in ("notes_only", "mixed"):
            citations = (meta or {}).get("citations") or snippets

        # Extract unique PDF filenames from citations
        pdf_sources = []
        if citations:
            seen_files = set()
            for cit in citations:
                filename = cit.get("filename", "")
                if filename and filename not in seen_files:
                    pdf_sources.append(filename)
                    seen_files.add(filename)

        # Save to history
        supa = admin_client()
        try:
            supa.table("qa_history").insert({
                "user_id": user["user_id"],
                "question": q,
                "answer": out_answer,
                "citations": citations,
            }).execute()
        except Exception:
            # Don't fail the request if history save fails
            pass

        result = {
            "answer": out_answer,
            "citations": citations,
            "pdf_sources": pdf_sources,
            "mode": answer_mode,  # Include mode for frontend
            "notes_part": notes_part if answer_mode == "mixed" else "",
            "enrichment_part": enrichment_part if answer_mode == "mixed" else "",
        }

        # Debug logging
        import sys
        print(f"[DEBUG] Answer mode: {answer_mode}", file=sys.stderr)
        print(f"[DEBUG] Notes part length: {len(notes_part)}", file=sys.stderr)
        print(f"[DEBUG] Enrichment part length: {len(enrichment_part)}", file=sys.stderr)
        print(f"[DEBUG] Response keys: {list(result.keys())}", file=sys.stderr)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini call failed: {e}")

