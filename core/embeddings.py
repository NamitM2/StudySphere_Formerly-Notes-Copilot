# core/embeddings.py
# Path: core/embeddings.py
from __future__ import annotations
import os
from typing import List, Any, Iterable
import numpy as np

PROVIDER = os.getenv("EMBED_PROVIDER", "gemini").lower()          # "gemini" | "local"
_EMBED_MODEL_RAW = os.getenv("EMBED_MODEL", "text-embedding-004")
# Ensure model name has proper prefix for Gemini API
EMBED_MODEL = _EMBED_MODEL_RAW if _EMBED_MODEL_RAW.startswith(("models/", "tunedModels/")) else f"models/{_EMBED_MODEL_RAW}"
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

_sbert = None
_gem = None

# ----------------- backends -----------------

def _ensure_sbert():
    global _sbert
    if _sbert is None:
        from sentence_transformers import SentenceTransformer
        _sbert = SentenceTransformer(os.getenv("SBERT_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    return _sbert

def _ensure_gemini():
    global _gem
    if _gem is None:
        import google.generativeai as genai
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY or GEMINI_API_KEY is not set for Gemini embeddings. "
                "Please check your .env file and ensure you have a valid API key from Google AI Studio."
            )
        try:
            genai.configure(api_key=api_key)
            _gem = genai
        except Exception as e:
            raise RuntimeError(f"Failed to configure Gemini API: {e}")
    return _gem

# ----------------- utils -----------------

def _to_float32(arr: np.ndarray) -> np.ndarray:
    return np.asarray(arr, dtype="float32")

def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    if arr.size == 0:
        return arr.astype("float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
    return (arr / norms).astype("float32")

def _flatten_iter(x: Any) -> Iterable[float]:
    if isinstance(x, (list, tuple, np.ndarray)):
        for y in x:
            yield from _flatten_iter(y)
    else:
        try:
            yield float(x)
        except Exception:
            return

def _coerce_1d_vector(v: Any, dim: int) -> List[float]:
    if isinstance(v, dict) and "values" in v:
        base = v["values"]
    else:
        base = v
    flat = list(_flatten_iter(base))
    if not flat:
        return [0.0] * dim
    if len(flat) < dim:
        flat += [0.0] * (dim - len(flat))
    elif len(flat) > dim:
        flat = flat[:dim]
    return flat

def _extract_vectors_gemini_response(res: Any) -> List[List[float]]:
    """
    Normalize google-generativeai return shapes into list[list[float]]:
      - {'embeddings':[{'values':[...]}]}
      - {'embedding': {'values':[...]} }
      - [{'embedding':{'values':[...]}}, ...] or [{'values':[...]} , ...] or [[...], ...]
      - object with .embedding(.values)
    """
    out: List[List[float]] = []

    def _add(item: Any):
        out.append(_coerce_1d_vector(item, EMBED_DIM))

    if isinstance(res, dict):
        embs = res.get("embeddings")
        if isinstance(embs, list):
            for item in embs:
                if isinstance(item, dict) and "embedding" in item:
                    _add(item["embedding"])
                else:
                    _add(item)
        else:
            emb = res.get("embedding")
            if emb is not None:
                _add(emb)
    elif isinstance(res, list):
        for item in res:
            if isinstance(item, dict) and "embedding" in item:
                _add(item["embedding"])
            else:
                _add(item)
    else:
        emb = getattr(res, "embedding", None)
        if emb is not None:
            val = getattr(emb, "values", emb)
            _add(val)

    return out

# ----------------- public API -----------------

def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Return (N, EMBED_DIM) L2-normalized vectors, robust to SDK shape quirks.
    Ensures one vector per input string.
    """
    texts = [t.strip() for t in texts if (t or "").strip()]
    if not texts:
        return _to_float32(np.zeros((0, EMBED_DIM)))

    if PROVIDER == "gemini":
        genai = _ensure_gemini()
        vecs: List[List[float]] = []

        # Process texts individually (google-generativeai doesn't support batch embedding)
        BATCH = 20
        num_batches = (len(texts) + BATCH - 1) // BATCH
        for batch_idx, i in enumerate(range(0, len(texts), BATCH), 1):
            batch = texts[i:i + BATCH]
            print(f"[EMBED] Processing batch {batch_idx}/{num_batches} ({len(batch)} texts)...")

            for t in batch:
                r = genai.embed_content(
                    model=EMBED_MODEL,
                    content=t,
                    task_type="retrieval_document",
                )
                vecs.extend(_extract_vectors_gemini_response(r))

        arr = np.asarray(vecs, dtype="float32")

    else:
        # Local/SBERT path
        m = _ensure_sbert()
        arr = _to_float32(m.encode(texts, show_progress_bar=False))
        if arr.ndim != 2:
            arr = arr.reshape(len(texts), -1).astype("float32")
        # Coerce to EMBED_DIM if model dim differs
        if arr.shape[1] != EMBED_DIM:
            if arr.shape[1] < EMBED_DIM:
                pad = np.zeros((arr.shape[0], EMBED_DIM - arr.shape[1]), dtype="float32")
                arr = np.hstack([arr, pad])
            else:
                arr = arr[:, :EMBED_DIM]

    # Safety: if somehow a weird shape appears, coerce row-wise
    if arr.ndim != 2:
        arr = np.vstack([_coerce_1d_vector(v, EMBED_DIM) for v in arr])

    # Final sanity: must match counts
    if arr.shape[0] != len(texts):
        raise RuntimeError(
            f"Embedding count mismatch: have {len(texts)} texts but embed_texts returned {arr.shape[0]} vectors"
        )

    return _l2_normalize(arr)

def embed_query(text: str) -> np.ndarray:
    """1 text -> (1, EMBED_DIM) L2-normalized."""
    return embed_texts([text])
