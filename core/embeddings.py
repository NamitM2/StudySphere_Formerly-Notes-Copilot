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

# Log configuration at module load
print(f"[EMBED CONFIG] Provider: {PROVIDER}")
print(f"[EMBED CONFIG] Model: {EMBED_MODEL}")
print(f"[EMBED CONFIG] Dimension: {EMBED_DIM}")

_sbert = None
_gem = None

# ----------------- backends -----------------

def _ensure_sbert():
    global _sbert
    if _sbert is None:
        print("[EMBED] Loading local embedding model (first time may take 30-60s to download)...")
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("SBERT_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        print(f"[EMBED] Model: {model_name}")
        _sbert = SentenceTransformer(model_name)
        print("[EMBED] Local embedding model loaded successfully!")
    return _sbert

def _ensure_gemini():
    global _gem
    if _gem is None:
        import time
        start = time.time()
        print("[EMBED] Initializing Gemini SDK (first time only)...")
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
            elapsed = time.time() - start
            print(f"[EMBED] Gemini SDK initialized in {elapsed:.2f}s")
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
      - {'embeddings':[{'values':[...]}]}  (batch response)
      - {'embedding': {'values':[...]} }    (single response)
      - [{'embedding':{'values':[...]}}, ...] or [{'values':[...]} , ...] or [[...], ...]
      - object with .embedding(.values)
      - object with ['embedding'] attribute that has list of embeddings
    """
    out: List[List[float]] = []

    def _add(item: Any):
        out.append(_coerce_1d_vector(item, EMBED_DIM))

    # Check if result has an 'embedding' attribute (genai SDK response object)
    if hasattr(res, 'embedding'):
        embedding_attr = getattr(res, 'embedding', None)
        # If embedding is a list of embeddings (batch response)
        if isinstance(embedding_attr, list):
            for emb in embedding_attr:
                if hasattr(emb, 'values'):
                    _add(emb.values)
                else:
                    _add(emb)
            return out
        # Single embedding with values
        elif hasattr(embedding_attr, 'values'):
            _add(embedding_attr.values)
            return out
        else:
            _add(embedding_attr)
            return out

    # Dictionary responses
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

    return out

# ----------------- public API -----------------

def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Return (N, EMBED_DIM) L2-normalized vectors, robust to SDK shape quirks.
    Ensures one vector per input string.
    """
    import time
    texts = [t.strip() for t in texts if (t or "").strip()]
    if not texts:
        return _to_float32(np.zeros((0, EMBED_DIM)))

    print(f"[EMBED] Using provider: {PROVIDER}")

    if PROVIDER == "gemini":
        start_time = time.time()
        genai = _ensure_gemini()
        vecs: List[List[float]] = []

        # Use concurrent requests for speed
        import concurrent.futures

        def embed_single(text: str, idx: int) -> tuple[int, List[float]]:
            """Embed a single text and return (index, vector) for ordering."""
            try:
                r = genai.embed_content(
                    model=EMBED_MODEL,
                    content=text,
                    task_type="retrieval_document",
                )
                individual_vecs = _extract_vectors_gemini_response(r)
                if individual_vecs:
                    return (idx, individual_vecs[0])
                else:
                    return (idx, [0.0] * EMBED_DIM)
            except Exception as e:
                print(f"[EMBED] Failed to embed text {idx} (len={len(text)}): {e}")
                return (idx, [0.0] * EMBED_DIM)

        # Process with ThreadPoolExecutor for I/O-bound API calls
        # Use up to 10 concurrent workers for speed
        max_workers = min(10, len(texts))
        print(f"[EMBED] Embedding {len(texts)} texts with {max_workers} concurrent workers...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all embedding tasks
            futures = [executor.submit(embed_single, text, idx) for idx, text in enumerate(texts)]

            # Collect results as they complete with progress updates
            results = []
            completed = 0
            total = len(futures)
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
                completed += 1
                if completed % 10 == 0 or completed == total:
                    print(f"[EMBED] Progress: {completed}/{total} chunks ({int(completed/total*100)}%)")

        # Sort by original index to maintain order
        results.sort(key=lambda x: x[0])
        vecs = [vec for _, vec in results]

        elapsed = time.time() - start_time
        print(f"[EMBED] Embedded {len(texts)} texts in {elapsed:.2f}s ({len(texts)/elapsed:.1f} texts/sec)")

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


def warmup_embeddings():
    """
    Pre-warm the embedding system by initializing the provider.
    Call this at app startup to avoid first-request delays.
    """
    print("[EMBED] Warming up embedding system...")
    if PROVIDER == "gemini":
        # Initialize Gemini SDK
        _ensure_gemini()
        # Do a test embedding to fully warm up the API connection
        try:
            import time
            start = time.time()
            test_vec = embed_texts(["Warmup test"])
            elapsed = time.time() - start
            print(f"[EMBED] Warmup complete! Test embedding took {elapsed:.2f}s")
            print(f"[EMBED] Subsequent uploads will be faster (no initialization delay)")
        except Exception as e:
            print(f"[EMBED] Warmup test failed (non-critical): {e}")
    else:
        # Initialize local model
        _ensure_sbert()
        print("[EMBED] Warmup complete! Local model ready.")
    print("[EMBED] Ready for fast uploads!")

def embed_query(text: str) -> np.ndarray:
    """1 text -> (1, EMBED_DIM) L2-normalized."""
    return embed_texts([text])
