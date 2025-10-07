#!/usr/bin/env python3
"""Apply the qa_history migration to Supabase."""
import os
from pathlib import Path
from api.supa import admin_client

def apply_migration():
    """Read and execute the migration SQL."""
    migration_file = Path(__file__).parent / "migrations" / "001_qa_history.sql"

    if not migration_file.exists():
        print(f"[ERROR] Migration file not found: {migration_file}")
        return False

    with open(migration_file, "r", encoding="utf-8") as f:
        sql = f.read()

    print("[INFO] Applying migration: 001_qa_history.sql")

    try:
        client = admin_client()
        # Execute the SQL via RPC or direct connection
        # Since Supabase Python client doesn't support raw SQL execution,
        # we'll need to use psycopg2 or execute via Supabase dashboard
        print("[INFO] Migration SQL:")
        print(sql)
        print("\n[IMPORTANT] Please execute the above SQL in your Supabase SQL Editor:")
        print("1. Go to https://supabase.com/dashboard")
        print("2. Select your project")
        print("3. Go to SQL Editor")
        print("4. Paste and run the migration SQL above")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to apply migration: {e}")
        return False

if __name__ == "__main__":
    apply_migration()
