# api/supa.py
# Path: api/supa.py
import os
from supabase import create_client, Client

_URL = os.getenv("SUPABASE_URL", "").rstrip("/")

# accept both SERVICE_ROLE and SERVICE_ROLE_KEY
_ADMIN = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE")
    or ""
)

def admin_client() -> Client:
    if not _URL or not _ADMIN:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    return create_client(_URL, _ADMIN)
