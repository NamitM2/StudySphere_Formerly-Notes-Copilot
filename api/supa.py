# api/supa.py
import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
BUCKET = os.getenv("SUPABASE_DOCS_BUCKET", "user-docs")

def admin_client() -> Client:
    # server-side: full access (still verify JWT in our code)
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

def anon_client() -> Client:
    # if you ever need client-side calls
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
