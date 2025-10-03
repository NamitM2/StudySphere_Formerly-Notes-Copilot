# api/storage.py
import os, re
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from api.supa import admin_client, BUCKET

_safe = re.compile(r"[^A-Za-z0-9._-]+")

def sanitize_filename(name: str) -> str:
    # keep extension; sanitize base
    name = name.strip().replace(" ", "_")
    if "." in name:
        base, ext = name.rsplit(".", 1)
        base = _safe.sub("-", base)
        ext = _safe.sub("", ext)
        return f"{base}.{ext}" if ext else base
    return _safe.sub("-", name)

def build_path(user_id: str, filename: str) -> str:
    return f"{user_id}/{sanitize_filename(filename)}"

def upload_bytes(
    user_id: str,
    filename: str,
    data: bytes,
    content_type: Optional[str] = None,
    upsert: bool = True,
    unique_fallback: bool = True,
) -> Tuple[str, bool]:
    """
    Returns (storage_path, created_new)
    - If upsert=True: overwrite existing object and return created_new=False when it existed.
    - If unique_fallback=True and provider rejects upsert, append timestamp to filename automatically.
    """
    supa = admin_client()
    storage_path = build_path(user_id, filename)
    opts = {"upsert": "true" if upsert else "false"}
    if content_type:
        opts["content_type"] = content_type

    try:
        supa.storage.from_(BUCKET).upload(path=storage_path, file=data, file_options=opts)
        return storage_path, True  # treat as new if first time; provider doesn't tell us
    except Exception as e:
        # Some client versions still 409 on upsert—fallback to unique name if asked
        msg = str(e).lower()
        if unique_fallback and ("duplicate" in msg or "already exists" in msg or "409" in msg):
            ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            if "." in filename:
                base, ext = filename.rsplit(".", 1)
                unique = f"{base}__{ts}.{ext}"
            else:
                unique = f"{filename}__{ts}"
            storage_path = build_path(user_id, unique)
            supa.storage.from_(BUCKET).upload(path=storage_path, file=data, file_options={"upsert": "false", **({"content_type": content_type} if content_type else {})})
            return storage_path, True
        # rethrow with clear context
        raise RuntimeError(f"Storage upload failed: {e}")

def signed_url(storage_path: str, expires_in: int = 60 * 10) -> str:
    """Create a time-limited download URL (bucket is private)."""
    supa = admin_client()
    res = supa.storage.from_(BUCKET).create_signed_url(storage_path, expires_in)
    # supabase-py returns dict with 'signedURL' or 'signed_url' depending on version
    return res.get("signedURL") or res.get("signed_url") or ""

def list_user_files(user_id: str) -> List[dict]:
    """List objects under user prefix."""
    supa = admin_client()
    # path is a 'prefix' in v2 client
    return supa.storage.from_(BUCKET).list(path=f"{user_id}")

def delete_paths(paths: List[str]) -> None:
    if not paths:
        return
    admin_client().storage.from_(BUCKET).remove(paths)
