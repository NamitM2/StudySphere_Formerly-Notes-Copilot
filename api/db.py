# api/db.py
"""
Lightweight Supabase repository utility.
Provides a consistent interface for database operations and makes testing easier.
"""

from typing import Any, Dict, List, Optional
from supabase import Client
from storage3.exceptions import StorageApiError
from postgrest.exceptions import APIError
from api.supa import admin_client


class SupabaseRepo:
    """Repository pattern wrapper around Supabase client."""

    def __init__(self):
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        """Lazy-load Supabase client (can be mocked in tests)."""
        if self._client is None:
            self._client = admin_client()
        return self._client

    # Worksheet operations
    def create_worksheet(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update worksheet metadata."""
        result = self.client.table("worksheets").upsert(data).execute()
        return result.data[0] if result.data else {}

    def get_worksheet(self, project_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get worksheet by project_id and user_id."""
        query = self.client.table("worksheets")\
            .select("*")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .limit(1)
        try:
            result = query.execute()
        except APIError as exc:
            if getattr(exc, "code", None) == "PGRST116":
                # Supabase raises PGRST116 when `.single()` finds no rows. Treat as missing worksheet.
                return None
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_worksheet(self, project_id: str, user_id: str) -> None:
        """Delete worksheet record."""
        self.client.table("worksheets")\
            .delete()\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()

    # Worksheet answers operations
    def get_worksheet_answers(self, project_id: str) -> Dict[str, str]:
        """Get all answers for a worksheet as field_id -> answer dict."""
        result = self.client.table("worksheet_answers")\
            .select("field_id, answer")\
            .eq("project_id", project_id)\
            .execute()
        return {row["field_id"]: row["answer"] for row in (result.data or [])}

    def save_worksheet_answers(self, answers: List[Dict[str, Any]]) -> int:
        """Bulk upsert worksheet answers. Returns count saved."""
        if not answers:
            return 0
        self.client.table("worksheet_answers").upsert(answers).execute()
        return len(answers)

    def delete_worksheet_answers(self, project_id: str) -> None:
        """Delete all answers for a worksheet."""
        self.client.table("worksheet_answers")\
            .delete()\
            .eq("project_id", project_id)\
            .execute()

    # Storage operations
    def _ensure_storage_bucket(self, bucket: str, make_public: bool = True) -> None:
        """
        Ensure the storage bucket exists. If it does not, attempt to create it.
        Safe to call repeatedly; creation errors due to existing buckets are ignored.
        """
        try:
            self.client.storage.create_bucket(
                bucket,
                options={"public": make_public}
            )
        except StorageApiError as exc:
            status = getattr(exc, "status_code", None)
            message = getattr(exc, "message", "") or str(exc)
            if status in (409, 400) and "exists" in message:
                return
            if "already exists" in message:
                return
            # For any other storage error, re-raise so callers can handle it.
            raise

    def upload_to_storage(
        self,
        bucket: str,
        path: str,
        data: bytes,
        content_type: str = "application/octet-stream"
    ) -> str:
        """Upload bytes to Supabase Storage. Returns public URL."""
        # Helpful for fresh dev environments where the bucket might not exist yet.
        self._ensure_storage_bucket(bucket, make_public=True)

        storage = self.client.storage.from_(bucket)

        try:
            storage.upload(
                path,
                data,
                file_options={"content-type": content_type}
            )
        except StorageApiError as exc:
            status = getattr(exc, "status_code", None)
            message = getattr(exc, "message", "") or str(exc)
            if status == 404 and "Bucket not found" in message:
                # Retry once after attempting to create the bucket.
                self._ensure_storage_bucket(bucket, make_public=True)
                storage = self.client.storage.from_(bucket)
                storage.upload(
                    path,
                    data,
                    file_options={"content-type": content_type}
                )
            else:
                raise

        return storage.get_public_url(path)

    def delete_from_storage(self, bucket: str, paths: List[str]) -> None:
        """Delete files from Supabase Storage."""
        if paths:
            self.client.storage.from_(bucket).remove(paths)


# Singleton instance
_repo: Optional[SupabaseRepo] = None

def get_repo() -> SupabaseRepo:
    """Get or create singleton repository instance."""
    global _repo
    if _repo is None:
        _repo = SupabaseRepo()
    return _repo
