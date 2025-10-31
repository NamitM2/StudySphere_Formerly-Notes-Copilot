"""
Worksheet Routes - API endpoints for PDF worksheet management and field detection
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from typing import List, Dict, Any
import io
import json

from core.worksheet_analyzer import WorksheetAnalyzer

try:
    from api.auth_supabase import get_current_user
except:
    from api.routes import get_current_user

from api.supa import admin_client

router = APIRouter(prefix="/ide/worksheet", tags=["worksheet"])

@router.post("/upload")
async def upload_worksheet(
    project_id: str,
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    """
    Upload a PDF worksheet, detect fillable fields using Gemini Vision,
    and store both the PDF and detected fields.

    Returns:
        {
            "project_id": str,
            "pdf_url": str,  # Supabase Storage URL
            "fields": List[Dict],  # Detected fillable fields
            "page_count": int
        }
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        print(f"[WORKSHEET_ROUTES] Uploading worksheet for project {project_id}")

        # Read PDF bytes
        pdf_bytes = await file.read()

        # Detect fillable fields using Gemini Vision
        print("[WORKSHEET_ROUTES] Analyzing PDF with Gemini Vision...")
        analyzer = WorksheetAnalyzer()
        detected_fields = analyzer.detect_fields(pdf_bytes)
        validated_fields = analyzer.validate_fields(detected_fields)

        print(f"[WORKSHEET_ROUTES] Detected {len(validated_fields)} fields")

        # Upload PDF to Supabase Storage
        storage_path = f"{user['id']}/worksheets/{project_id}/{file.filename}"

        print(f"[WORKSHEET_ROUTES] Uploading to Supabase: {storage_path}")
        admin_client.storage.from_("worksheets").upload(
            storage_path,
            pdf_bytes,
            file_options={"content-type": "application/pdf"}
        )

        # Get public URL
        pdf_url = admin_client.storage.from_("worksheets").get_public_url(storage_path)

        # Store worksheet metadata in database
        worksheet_data = {
            "project_id": project_id,
            "user_id": user["id"],
            "filename": file.filename,
            "pdf_url": pdf_url,
            "fields": validated_fields,
            "page_count": max(field["page"] for field in validated_fields) if validated_fields else 1
        }

        # Upsert worksheet record
        admin_client.table("worksheets").upsert(worksheet_data).execute()

        print(f"[WORKSHEET_ROUTES] Upload complete, URL: {pdf_url}")

        return {
            "project_id": project_id,
            "pdf_url": pdf_url,
            "fields": validated_fields,
            "page_count": worksheet_data["page_count"]
        }

    except Exception as e:
        print(f"[WORKSHEET_ROUTES] Error uploading worksheet: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload worksheet: {str(e)}")


@router.get("/{project_id}/fields")
async def get_worksheet_fields(
    project_id: str,
    user=Depends(get_current_user)
):
    """
    Retrieve detected fields for a worksheet project.

    Returns:
        {
            "project_id": str,
            "pdf_url": str,
            "fields": List[Dict],
            "answers": Dict[str, str]  # field_id -> answer
        }
    """
    try:
        # Get worksheet data
        result = admin_client.table("worksheets")\
            .select("*")\
            .eq("project_id", project_id)\
            .eq("user_id", user["id"])\
            .single()\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Worksheet not found")

        worksheet = result.data

        # Get saved answers if any
        answers_result = admin_client.table("worksheet_answers")\
            .select("field_id, answer")\
            .eq("project_id", project_id)\
            .execute()

        answers = {row["field_id"]: row["answer"] for row in answers_result.data}

        return {
            "project_id": project_id,
            "pdf_url": worksheet["pdf_url"],
            "fields": worksheet["fields"],
            "answers": answers
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[WORKSHEET_ROUTES] Error fetching worksheet: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch worksheet: {str(e)}")


@router.put("/{project_id}/save")
async def save_worksheet_answers(
    project_id: str,
    answers: Dict[str, str],  # field_id -> answer
    user=Depends(get_current_user)
):
    """
    Save user's answers to worksheet fields.
    Supports autosave functionality.

    Body:
        {
            "page1_field0": "42",
            "page1_field1": "Show work: 97 + 65 = 162"
        }

    Returns:
        {
            "project_id": str,
            "saved_count": int,
            "timestamp": str
        }
    """
    try:
        # Verify worksheet exists and belongs to user
        worksheet = admin_client.table("worksheets")\
            .select("id")\
            .eq("project_id", project_id)\
            .eq("user_id", user["id"])\
            .single()\
            .execute()

        if not worksheet.data:
            raise HTTPException(status_code=404, detail="Worksheet not found")

        # Prepare answer records
        answer_records = [
            {
                "project_id": project_id,
                "user_id": user["id"],
                "field_id": field_id,
                "answer": answer
            }
            for field_id, answer in answers.items()
            if answer  # Only save non-empty answers
        ]

        # Upsert answers (update if exists, insert if new)
        if answer_records:
            admin_client.table("worksheet_answers").upsert(answer_records).execute()

        from datetime import datetime

        return {
            "project_id": project_id,
            "saved_count": len(answer_records),
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[WORKSHEET_ROUTES] Error saving answers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save answers: {str(e)}")


@router.post("/{project_id}/export")
async def export_completed_worksheet(
    project_id: str,
    user=Depends(get_current_user)
):
    """
    Export completed worksheet as a PDF with answers filled in.
    Uses PyMuPDF to overlay answers on the original PDF.

    Returns:
        {
            "download_url": str  # Temporary download URL
        }
    """
    try:
        import fitz  # PyMuPDF
        from datetime import datetime, timedelta

        # Get worksheet and answers
        worksheet = admin_client.table("worksheets")\
            .select("*")\
            .eq("project_id", project_id)\
            .eq("user_id", user["id"])\
            .single()\
            .execute()

        if not worksheet.data:
            raise HTTPException(status_code=404, detail="Worksheet not found")

        answers_result = admin_client.table("worksheet_answers")\
            .select("*")\
            .eq("project_id", project_id)\
            .execute()

        answers = {row["field_id"]: row["answer"] for row in answers_result.data}

        # Download original PDF
        pdf_url = worksheet.data["pdf_url"]
        # TODO: Download PDF from Supabase storage
        # For now, return error as this needs implementation

        raise HTTPException(status_code=501, detail="Export feature coming soon")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[WORKSHEET_ROUTES] Error exporting worksheet: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export worksheet: {str(e)}")


@router.delete("/{project_id}")
async def delete_worksheet(
    project_id: str,
    user=Depends(get_current_user)
):
    """
    Delete a worksheet and all associated data.

    Returns:
        {"message": "Worksheet deleted successfully"}
    """
    try:
        # Get worksheet to find storage path
        worksheet = admin_client.table("worksheets")\
            .select("pdf_url")\
            .eq("project_id", project_id)\
            .eq("user_id", user["id"])\
            .single()\
            .execute()

        if not worksheet.data:
            raise HTTPException(status_code=404, detail="Worksheet not found")

        # Delete from storage
        # Extract path from URL and delete
        # TODO: Implement storage deletion

        # Delete answers
        admin_client.table("worksheet_answers")\
            .delete()\
            .eq("project_id", project_id)\
            .execute()

        # Delete worksheet record
        admin_client.table("worksheets")\
            .delete()\
            .eq("project_id", project_id)\
            .eq("user_id", user["id"])\
            .execute()

        return {"message": "Worksheet deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[WORKSHEET_ROUTES] Error deleting worksheet: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete worksheet: {str(e)}")
