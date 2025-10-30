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

    # Check if answer has enrichment marker
    has_enrichment = "<<<ENRICHMENT_START>>>" in answer

    # Check if retrieved documents are actually relevant
    # Stricter threshold: distance < 0.75 for high confidence relevance
    # Note: Lower distance = more similar. Cosine distance range: 0.0 (identical) to 2.0 (opposite)
    has_relevant_docs = min_distance < 0.75

    # Check if answer explicitly says it's not in notes (fallback check)
    has_not_found_phrase = (
        ("couldn't find" in answer_lower or "could not find" in answer_lower or
         "can't find" in answer_lower or "cannot find" in answer_lower)
        and "notes" in answer_lower
    )

    # Check if this is a greeting or casual statement (not a real question)
    is_greeting = any(greeting in answer_lower[:50] for greeting in [
        "hello", "hi there", "hey there", "greetings", "how can i help", "what can i do"
    ])

    # Determine mode - prioritize distance-based detection
    if not has_relevant_docs or has_not_found_phrase or is_greeting:
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

@router.api_route("/health", methods=["GET", "HEAD"])
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

    # Process document synchronously with local embeddings (fast!)
    try:
        from core.ingest_pg import ingest_file

        result = ingest_file(
            user_id=user["user_id"],
            filename=file.filename,
            file_bytes=content,
            mime=file.content_type,
        )

        return {
            "ok": True,
            "doc_id": result.get("doc_id"),
            "filename": result.get("filename"),
            "chunks": result.get("chunks", 0),
            "elapsed_ms": result.get("elapsed_ms", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {e}")

# ----------------------------------------------------------------------
# Get document processing status
# ----------------------------------------------------------------------
@router.get("/docs/{doc_id}/status")
def get_document_status(doc_id: int, user=Depends(get_current_user)) -> Dict[str, Any]:
    """Check the processing status of a document"""
    supa = admin_client()
    try:
        res = supa.table("documents").select(
            "id, filename, status, processing_started_at, processing_completed_at, processing_error"
        ).eq("id", doc_id).eq("user_id", user["user_id"]).limit(1).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Status check failed: {exc}") from exc

    docs = res.data or []
    if not docs:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = docs[0]
    return {
        "doc_id": doc["id"],
        "filename": doc["filename"],
        "status": doc.get("status", "ready"),
        "processing_started_at": doc.get("processing_started_at"),
        "processing_completed_at": doc.get("processing_completed_at"),
        "error": doc.get("processing_error")
    }

# ----------------------------------------------------------------------
# List documents
# ----------------------------------------------------------------------
@router.get("/docs")
def list_docs(user=Depends(get_current_user)) -> List[Dict[str, Any]]:
    supa = admin_client()
    fields = "id, filename, mime, byte_size, created_at, storage_path, status"
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
            "status": row.get("status", "ready"),
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
# Multimodal search (text + images)
# ----------------------------------------------------------------------
@router.get("/search/multimodal")
def search_multimodal_endpoint(
    q: str,
    k: int = 10,
    include_visual: bool = True,
    user=Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Search across both text chunks and visual content (images)."""
    if not q or not q.strip():
        return []
    if len(q.strip()) > 1000:
        raise HTTPException(status_code=400, detail="Query too long (max 1000)")
    if len(q.strip()) < 3:
        raise HTTPException(status_code=400, detail="Query too short (min 3)")
    if k < 1 or k > 30:
        raise HTTPException(status_code=400, detail="k must be between 1 and 30")

    try:
        from core.search_multimodal import search_multimodal
        q_vec = embed_query(q)
        results = search_multimodal(
            user_id=user["user_id"],
            query_embedding=q_vec,
            k=int(k),
            include_visual=include_visual,
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Multimodal search failed: {str(e)}")


@router.get("/images/{doc_id}")
def get_document_images(doc_id: int, user=Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Get all images for a specific document."""
    try:
        from core.ingest_visual import get_images_for_document

        # Verify document belongs to user
        supa = admin_client()
        doc_res = supa.table("documents").select("id").eq("id", doc_id).eq("user_id", user["user_id"]).limit(1).execute()
        if not doc_res.data:
            raise HTTPException(status_code=404, detail="Document not found")

        images = get_images_for_document(doc_id)
        return images
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve images: {str(e)}")


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
    # New: similarity threshold for dynamic chunk selection
    # similarity_threshold of 0.60 = max distance of 0.80 (balanced relevance)
    # Note: cosine distance ranges from 0.0 (identical) to 2.0 (opposite)
    # For resume/notes queries, distances of 0.6-0.8 are typical and relevant
    similarity_threshold: float = float(payload.get("similarity_threshold", 0.60))
    max_chunks: int = int(payload.get("max_chunks", 30))
    include_visual: bool = bool(payload.get("include_visual", True))  # Multimodal by default

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
        # Try multimodal search first (if enabled and tables exist)
        fetch_k = max_chunks
        hits = []

        if include_visual:
            try:
                from core.search_multimodal import search_multimodal
                hits = search_multimodal(
                    user_id=user["user_id"],
                    query_embedding=q_vec,
                    k=fetch_k,
                    include_visual=True,
                )
            except Exception as multimodal_err:
                # Fallback to text-only search if multimodal fails
                print(f"Multimodal search failed, falling back to text-only: {multimodal_err}")
                hits = _search_fn(user_id=user["user_id"], query=q, query_embedding=q_vec, k=fetch_k)
        else:
            hits = _search_fn(user_id=user["user_id"], query=q, query_embedding=q_vec, k=fetch_k)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

    # First pass: collect all hits and filter by similarity threshold
    # Note: distance in vector search is typically 0.0 (identical) to 2.0 (opposite)
    # We convert distance to similarity: similarity = 1 - (distance / 2)
    # So similarity_threshold 0.80 means distance must be <= 0.40
    max_distance = 2.0 * (1.0 - similarity_threshold)

    candidate_snippets: List[Dict[str, Any]] = []
    candidate_texts: List[str] = []
    min_distance = float('inf')  # Track minimum distance for citation detection

    print(f"[ASK] Search returned {len(hits or [])} hits")
    print(f"[ASK] Similarity threshold: {similarity_threshold}, max_distance: {max_distance}")
    for h in hits or []:
        distance = h.get("distance", 1.0)
        print(f"[ASK] Hit distance: {distance}")
        if distance is not None and distance < min_distance:
            min_distance = distance

        # Apply threshold filter
        if distance <= max_distance:
            sn = {
                "filename": h.get("filename") or h.get("file_name") or "file",
                "page": h.get("page"),
                "text": h.get("text") or h.get("chunk") or "",
                "doc_id": h.get("doc_id"),
                "distance": distance,
            }
            candidate_snippets.append(sn)
            candidate_texts.append(sn["text"])
        else:
            print(f"[ASK] Filtered out chunk with distance {distance} (threshold: {max_distance})")

    # Only use chunks that passed the similarity threshold
    # Use all chunks that passed the threshold - let MMR handle diversity
    print(f"[ASK] Candidate snippets after first filter: {len(candidate_snippets)}, min_distance: {min_distance}")

    # Optional: Apply a more relaxed second filter only if we have too many results
    # This keeps chunks within a reasonable range of the best match
    if candidate_snippets and min_distance != float('inf') and len(candidate_snippets) > 20:
        # Only apply secondary filter if we have > 20 candidates
        # More relaxed cutoff: within 0.25 of best match (was 0.15)
        distance_cutoff = min_distance + 0.25
        print(f"[ASK] Too many candidates ({len(candidate_snippets)}), applying secondary filter with cutoff: {distance_cutoff}")
        filtered_snippets = []
        filtered_texts = []
        for i, sn in enumerate(candidate_snippets):
            if sn["distance"] <= distance_cutoff:
                filtered_snippets.append(sn)
                filtered_texts.append(candidate_texts[i])
            else:
                print(f"[ASK] Second filter removed chunk with distance {sn['distance']} (cutoff: {distance_cutoff})")
        snippets = filtered_snippets
        texts = filtered_texts
    else:
        # Use all candidates that passed the threshold
        snippets = candidate_snippets
        texts = candidate_texts

    print(f"[ASK] Final snippets after all filtering: {len(snippets)}")

    # Apply MMR for diversity (limit to top 15 for performance)
    if snippets:
        query_terms = _tokenize(q)
        lex_scores = [_lexical_score(sn, query_terms) for sn in snippets]

        # Limit MMR processing to top 15 snippets for performance
        # More than 15 causes slow embedding generation
        mmr_input_limit = min(15, len(snippets))
        snippets_for_mmr = snippets[:mmr_input_limit]
        texts_for_mmr = texts[:mmr_input_limit]

        try:
            doc_vecs = np.asarray(embed_texts(texts_for_mmr), dtype="float32")
        except Exception:
            doc_vecs = np.zeros((len(snippets_for_mmr), len(np.asarray(q_vec).reshape(-1))), dtype="float32")

        if doc_vecs.ndim == 1:
            doc_vecs = doc_vecs.reshape(1, -1)

        # MMR reranking - select top k diverse chunks
        mmr_limit = min(k * 2, len(snippets_for_mmr))  # 2x k for better diversity
        mmr_selected = _mmr_select(np.asarray(q_vec).reshape(-1), doc_vecs, mmr_limit)

        if mmr_selected:
            scored: List[tuple[float, float, int]] = []
            for idx, mmr_score in mmr_selected:
                lex = lex_scores[idx] if idx < len(lex_scores) else 0.0
                combined = mmr_score + 0.1 * lex
                scored.append((combined, lex, idx))
            scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
            # Reorder the MMR-processed snippets, keep only top results
            snippets = [snippets_for_mmr[idx] for _, _, idx in scored]
        else:
            # Fallback: just use top k by lexical score
            snippets_with_scores = [(sn, _lexical_score(sn, query_terms)) for sn in snippets]
            snippets_with_scores.sort(key=lambda x: x[1], reverse=True)
            snippets = [sn for sn, _ in snippets_with_scores[:k * 2]]
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
            # Use citations from meta if available, otherwise use top k snippets
            citations = (meta or {}).get("citations") or snippets[:k]

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
            "chunks_retrieved": len(snippets),  # Debug: actual number of chunks used
            "similarity_threshold_used": similarity_threshold,
            "max_distance_used": max_distance,
        }

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini call failed: {e}")

