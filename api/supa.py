# api/supa.py
# Path: api/supa.py
import os
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

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

    # Configure generous timeouts for large document ingestion
    # Default: 10 minutes (600 seconds) for both database and storage operations
    timeout = int(os.getenv("SUPABASE_TIMEOUT", "600"))

    return create_client(
        _URL,
        _ADMIN,
        options=ClientOptions(
            postgrest_client_timeout=timeout,
            storage_client_timeout=timeout,
        )
    )
