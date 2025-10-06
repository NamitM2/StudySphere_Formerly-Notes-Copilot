# api/storage.py
"""
Supabase Storage helpers used by ingestion:
- upload_bytes(user_id, filename, data, content_type=None, upsert=False, unique_fallback=False)
    -> returns (storage_path, created_bool)
- delete_paths(paths)
- create_signed_url(path, expires_in_seconds=3600)

Bucket selection (in order):
  SUPABASE_DOCS_BUCKET  (preferred; e.g. "user-docs")
  SUPABASE_STORAGE_BUCKET  (legacy fallback)
  "notes"  (final fallback)
"""

from __future__ import annotations

import os
import re
import time
from typing import List, Optional, Tuple
from supabase import create_client, Client


# -------- env / client --------

def _bucket_name() -> str:
    return (
        os.getenv("SUPABASE_DOCS_BUCKET")
        or os.getenv("SUPABASE_STORAGE_BUCKET")
        or "notes"
    )

def _client() -> Client:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


# -------- path helpers --------

_name_strip = re.compile(r"[^A-Za-z0-9._-]+")

def _safe_filename(name: str, maxlen: int = 140) -> str:
    """
    Keep alnum, dot, dash, underscore. Collapse spaces and trim length.
    """
    name = (name or "file").strip().replace(" ", "-")
    name = _name_strip.sub("-", name)
    # avoid hidden files / weird prefixes
    name = name.lstrip(".-_") or "file"
    if len(name) > maxlen:
        # keep extension if present
        parts = name.rsplit(".", 1)
        if len(parts) == 2:
            stem, ext = parts
            keep = maxlen - len(ext) - 1
            name = f"{stem[:keep]}." + ext
        else:
            name = name[:maxlen]
    return name

def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


# -------- public API --------

def upload_bytes(
    *,
    user_id: str,
    filename: str,
    data: bytes,
    content_type: Optional[str] = None,
    upsert: bool = False,
    unique_fallback: bool = False,
) -> Tuple[str, bool]:
    """
    Store `data` under a per-user prefix:
        <user_id>/<YYYYmmdd-HHMMSS>-<safe-filename>

    If `upsert=True`, existing objects are overwritten.
    If `unique_fallback=True` and the name collides, we try:
        <ts>-<name>, <ts>-<name>-1, <ts>-<name>-2, ... up to 10 attempts

    Returns: (storage_path, created_bool)
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("upload_bytes: data must be bytes-like")

    user_id = (user_id or "anon").strip() or "anon"
    c = _client()
    bucket = _bucket_name()

    base_name = _safe_filename(filename or "file")
    ts = _timestamp()

    def build_name(suffix: Optional[int]) -> str:
        if suffix is None:
            return f"{user_id}/{ts}-{base_name}"
        # insert before extension if any
        parts = base_name.rsplit(".", 1)
        if len(parts) == 2:
            stem, ext = parts
            return f"{user_id}/{ts}-{stem}-{suffix}.{ext}"
        return f"{user_id}/{ts}-{base_name}-{suffix}"

    attempts = 1 if (upsert or not unique_fallback) else 10
    last_err: Optional[Exception] = None
    for i in range(attempts):
        path = build_name(None if i == 0 else i)
        try:
            # IMPORTANT: Supabase Python client expects header-ish strings
            opts = {
                "contentType": content_type or "application/octet-stream",
                "upsert": "true" if upsert else "false",
            }
            c.storage.from_(bucket).upload(path=path, file=data, file_options=opts)
            return path, True
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if unique_fallback and ("exist" in msg or "already" in msg):
                continue
            raise


    # If we exit loop without success, raise last error (should be collision-related)
    if last_err:
        raise last_err
    raise RuntimeError("upload_bytes: unknown failure")

def delete_paths(paths: List[str]) -> None:
    """Delete a list of object paths from the current bucket."""
    if not paths:
        return
    c = _client()
    c.storage.from_(_bucket_name()).remove(paths)

def create_signed_url(path: str, expires_in_seconds: int = 3600) -> str:
    """Create a signed URL for a private object path."""
    c = _client()
    res = c.storage.from_(_bucket_name()).create_signed_url(path, expires_in_seconds)
    return res.get("signedURL") if isinstance(res, dict) else res
# inside api/storage.py
def _client():
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE")
        or ""
    )
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)
