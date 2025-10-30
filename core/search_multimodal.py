# core/search_multimodal.py
"""
Multimodal search that combines text and visual content.
Searches across both text chunks and visual chunks (image descriptions).
"""
from __future__ import annotations

from typing import Any, Dict, List
import numpy as np
from supabase import Client as SupabaseClient

from api.supa import admin_client

__all__ = ["search_multimodal"]


def _prepare_query_embedding(vec: Any) -> List[float]:
    arr = np.asarray(vec, dtype="float32")
    if arr.size == 0:
        raise ValueError("query_embedding is empty")
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    return arr.tolist()


def search_multimodal(
    *,
    user_id: str,
    query: str | None = None,
    query_embedding: Any | None = None,
    k: int = 10,
    include_visual: bool = True,
    visual_boost: float = 1.0,
    supa: SupabaseClient | None = None,
) -> List[Dict[str, Any]]:
    """
    Search across both text chunks and visual chunks.

    Args:
        user_id: User ID for filtering
        query: Raw query string (not used if query_embedding provided)
        query_embedding: Precomputed embedding vector
        k: Number of results to return
        include_visual: Whether to include visual content in results
        visual_boost: Multiplier for visual content relevance (default 1.0)
        supa: Supabase client (optional)

    Returns:
        List of results with both text and visual content, sorted by relevance.
        Each result has:
        - doc_id, chunk_id, filename, page, text, distance
        - content_type: 'text' or 'visual'
        - For visual: image_id, image_description, image_type, storage_path
    """
    if not user_id:
        raise ValueError("search_multimodal: user_id is required")
    if not query and query_embedding is None:
        return []

    if supa is None:
        supa = admin_client()

    # Prepare embedding
    try:
        embedding = _prepare_query_embedding(query_embedding)
    except Exception as exc:
        raise ValueError(f"search_multimodal: could not coerce query_embedding: {exc}") from exc

    # Call the database function
    try:
        res = supa.rpc(
            "search_chunks_multimodal",
            {
                "p_user_id": user_id,
                "p_query_embedding": embedding,
                "p_match_count": int(k),
                "p_include_visual": include_visual,
            }
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"search_multimodal RPC failed: {exc}") from exc

    data = getattr(res, "data", None)
    if data is None:
        raise RuntimeError(f"search_multimodal RPC returned no data: {res}")

    if not isinstance(data, list):
        raise RuntimeError(f"search_multimodal RPC returned unexpected type: {type(data)}")

    # Apply visual boost if needed
    if include_visual and visual_boost != 1.0:
        for item in data:
            if item.get("content_type") == "visual":
                # Boost visual content by reducing distance
                item["distance"] = item.get("distance", 0.0) / visual_boost

    # Sort by distance (lower is better)
    data.sort(key=lambda r: r.get("distance", 0.0))

    # Limit to k results
    return data[:k]


def search_images_only(
    *,
    user_id: str,
    query_embedding: Any,
    k: int = 5,
    supa: SupabaseClient | None = None,
) -> List[Dict[str, Any]]:
    """
    Search only visual content (images).

    Returns list of image results with metadata.
    """
    if supa is None:
        supa = admin_client()

    try:
        embedding = _prepare_query_embedding(query_embedding)
    except Exception as exc:
        raise ValueError(f"could not coerce query_embedding: {exc}") from exc

    try:
        # Search visual_chunks directly
        res = supa.rpc(
            "search_chunks_multimodal",
            {
                "p_user_id": user_id,
                "p_query_embedding": embedding,
                "p_match_count": int(k * 2),  # Get more, then filter
                "p_include_visual": True,
            }
        ).execute()

        data = getattr(res, "data", None) or []

        # Filter to only visual content
        visual_only = [item for item in data if item.get("content_type") == "visual"]

        # Sort and limit
        visual_only.sort(key=lambda r: r.get("distance", 0.0))
        return visual_only[:k]

    except Exception as exc:
        raise RuntimeError(f"search_images_only failed: {exc}") from exc


def get_image_context(image_id: int, supa: SupabaseClient | None = None) -> Dict[str, Any] | None:
    """
    Get full context for an image including surrounding text chunks.

    Args:
        image_id: Image ID
        supa: Supabase client

    Returns:
        Dict with image metadata, description, and nearby text chunks
    """
    if supa is None:
        supa = admin_client()

    try:
        # Get image metadata
        img_res = supa.table("images").select("*").eq("id", image_id).limit(1).execute()
        if not img_res.data:
            return None

        image = img_res.data[0]
        doc_id = image["doc_id"]
        page = image["page"]

        # Get text chunks from same page
        chunks_res = supa.table("chunks").select("text, page").eq("doc_id", doc_id).eq("page", page).execute()
        page_text = " ".join([c["text"] for c in (chunks_res.data or [])])

        return {
            "image": image,
            "page_text": page_text,
            "context": f"{image.get('caption', '')} {page_text}".strip(),
        }

    except Exception as e:
        print(f"Warning: Failed to get image context for image {image_id}: {e}")
        return None
