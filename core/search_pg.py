# core/search_pg.py
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from supabase import Client as SupabaseClient

from api.supa import admin_client

__all__ = ["search_chunks"]


def _prepare_query_embedding(vec: Any) -> List[float]:
    arr = np.asarray(vec, dtype="float32")
    if arr.size == 0:
        raise ValueError("query_embedding is empty")
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    return arr.tolist()


def search_chunks(
    *,
    user_id: str,
    query: str | None = None,
    query_embedding: Any | None = None,
    k: int = 5,
    supa: SupabaseClient | None = None,
) -> List[Dict[str, Any]]:
    """
    Call the Postgres function `public.search_chunks` and return matches.

    Accepts either a raw query string (for SQL-side embedding) or a precomputed
    embedding. When both are provided we send the embedding first and fall back
    to the raw query if the RPC rejects it.
    """
    if not user_id:
        raise ValueError("search_chunks: user_id is required")
    if not query and query_embedding is None:
        return []

    if supa is None:
        supa = admin_client()

    payload = {
        "p_user_id": user_id,
        "p_match_count": int(k),
    }

    fallback_payload: Dict[str, Any] | None = None

    if query_embedding is not None:
        try:
            payload["p_query_embedding"] = _prepare_query_embedding(query_embedding)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"search_chunks: could not coerce query_embedding: {exc}") from exc
        if query:
            fallback_payload = {
                "p_user_id": user_id,
                "p_query": query,
                "p_match_count": int(k),
            }
    else:
        payload["p_query"] = query or ""

    def _execute(body: Dict[str, Any]):
        return supa.rpc("search_chunks", body).execute()

    try:
        res = _execute(payload)
    except Exception as exc:
        if fallback_payload is None:
            raise RuntimeError(f"search_chunks RPC failed: {exc}") from exc
        res = _execute(fallback_payload)

    data = getattr(res, "data", None)
    if data is None:
        if fallback_payload and payload is not fallback_payload:
            res = _execute(fallback_payload)
            data = getattr(res, "data", None)
        if data is None:
            raise RuntimeError(f"search_chunks RPC returned no data: {res}")

    if not isinstance(data, list):
        raise RuntimeError(f"search_chunks RPC returned unexpected type: {type(data)}")

    data.sort(key=lambda r: r.get("distance", 0.0))
    return data
