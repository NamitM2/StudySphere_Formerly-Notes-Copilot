"""
Worksheet Routes - API endpoints for PDF worksheet management and field detection
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import io
import json
from copy import deepcopy

from core.worksheet_analyzer import WorksheetAnalyzer, BOUNDS_VERSION
from core.ide.ai_assistant import IDEAssistant
from api.db import get_repo
from api.logger import get_logger

try:
    from api.auth_supabase import get_current_user
except:
    from api.routes import get_current_user

router = APIRouter(prefix="/ide/worksheet", tags=["worksheet"])
logger = get_logger(__name__)

# Singleton analyzer instance (lazy-loaded, cached)
_analyzer: Optional[WorksheetAnalyzer] = None
assistant = IDEAssistant()
LEGACY_IMAGE_SCALE = 2.0  # Older detections rendered pages at 2x scale during analysis


def normalize_worksheet_bounds(worksheet: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize worksheet field bounds to the latest coordinate system (PDF user space).
    Legacy uploads stored bounds either as 2x image pixels (version 1) or as ratios (version 2).
    """
    if not worksheet:
        return worksheet

    bounds_version = worksheet.get("bounds_version", 1)
    fields = worksheet.get("fields") or []
    if not fields or bounds_version >= BOUNDS_VERSION:
        return worksheet

    page_dims_raw = worksheet.get("page_dimensions") or {}

    def get_page_dims(page: Any) -> tuple[float, float]:
        dims = page_dims_raw.get(str(page)) or page_dims_raw.get(page) or {}
        width = float(dims.get("width") or 612.0)  # Default to US Letter width
        height = float(dims.get("height") or 792.0)  # Default to US Letter height
        return width, height

    normalized_fields: List[Dict[str, Any]] = []

    for field in fields:
        field_copy = deepcopy(field)
        bounds = field_copy.get("bounds") or {}
        page = field_copy.get("page")

        try:
            raw_x = float(bounds.get("x", 0))
            raw_y = float(bounds.get("y", 0))
            raw_w = float(bounds.get("width", 0))
            raw_h = float(bounds.get("height", 0))
        except (TypeError, ValueError):
            normalized_fields.append(field_copy)
            continue

        page_width, page_height = get_page_dims(page)

        if bounds_version == 1:
            # Coordinates stored in 2x image pixels.
            scale = 1.0 / LEGACY_IMAGE_SCALE
            pdf_width = raw_w * scale
            pdf_height = raw_h * scale
            pdf_x = raw_x * scale
            top = raw_y * scale
        elif bounds_version == 2:
            # Coordinates stored as ratios of page width/height.
            pdf_width = raw_w * page_width
            pdf_height = raw_h * page_height
            pdf_x = raw_x * page_width
            top = raw_y * page_height
        else:
            normalized_fields.append(field_copy)
            continue

        pdf_y = page_height - top - pdf_height

        field_copy["bounds"] = {
            "x": round(pdf_x, 2),
            "y": round(pdf_y, 2),
            "width": round(pdf_width, 2),
            "height": round(pdf_height, 2)
        }
        field_copy["bounds_version"] = BOUNDS_VERSION
        normalized_fields.append(field_copy)

    normalized = dict(worksheet)
    normalized["fields"] = normalized_fields
    normalized["bounds_version"] = BOUNDS_VERSION
    normalized.setdefault("page_dimensions", page_dims_raw)
    return normalized

def get_analyzer() -> WorksheetAnalyzer:
    """Get or create cached WorksheetAnalyzer instance."""
    global _analyzer
    if _analyzer is None:
        if not WorksheetAnalyzer.is_available():
            raise HTTPException(
                status_code=503,
                detail="Worksheet field detection unavailable: GOOGLE_API_KEY not configured"
            )
        _analyzer = WorksheetAnalyzer()
    return _analyzer


class FieldSuggestionRequest(BaseModel):
    current_answer: Optional[str] = None
    instructions: Optional[str] = None

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

        logger.info(f"Uploading worksheet for project {project_id}, filename: {file.filename}")

        # Read PDF bytes
        pdf_bytes = await file.read()

        # Detect fillable fields using Gemini Vision
        logger.info("Analyzing PDF with Gemini Vision...")
        analyzer = get_analyzer()
        detected_fields, page_dimensions = analyzer.detect_fields(pdf_bytes)
        validated_fields = analyzer.validate_fields(detected_fields)

        logger.info(f"Detected {len(validated_fields)} fillable fields")

        # Upload PDF to Supabase Storage
        repo = get_repo()
        storage_path = f"{user['user_id']}/worksheets/{project_id}/{file.filename}"

        logger.info(f"Uploading to Supabase storage: {storage_path}")
        pdf_url = repo.upload_to_storage(
            bucket="worksheets",
            path=storage_path,
            data=pdf_bytes,
            content_type="application/pdf"
        )

        # Store worksheet metadata in database
        worksheet_data = {
            "project_id": project_id,
            "user_id": user["user_id"],
            "filename": file.filename,
            "pdf_url": pdf_url,
            "fields": validated_fields,
            "bounds_version": BOUNDS_VERSION,
            "page_count": max(field["page"] for field in validated_fields) if validated_fields else 1,
            "page_dimensions": {str(k): v for k, v in page_dimensions.items()}
        }

        # Upsert worksheet record
        repo.create_worksheet(worksheet_data)

        logger.info(f"Worksheet upload complete, PDF URL: {pdf_url}")

        return {
            "project_id": project_id,
            "pdf_url": pdf_url,
            "fields": validated_fields,
            "bounds_version": BOUNDS_VERSION,
            "page_count": worksheet_data["page_count"],
            "page_dimensions": worksheet_data["page_dimensions"]
        }

    except Exception as e:
        logger.error(f"Error uploading worksheet: {e}", exc_info=True)
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
        repo = get_repo()

        # Get worksheet data
        worksheet = repo.get_worksheet(project_id, user["user_id"])
        if not worksheet:
            raise HTTPException(status_code=404, detail="Worksheet not found")
        worksheet = normalize_worksheet_bounds(worksheet)

        # Get saved answers
        answers = repo.get_worksheet_answers(project_id)

        return {
            "project_id": project_id,
            "pdf_url": worksheet["pdf_url"],
            "fields": worksheet["fields"],
            "bounds_version": worksheet.get("bounds_version", BOUNDS_VERSION),
            "page_dimensions": worksheet.get("page_dimensions"),
            "answers": answers
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching worksheet fields: {e}", exc_info=True)
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
        repo = get_repo()

        # Verify worksheet exists and belongs to user
        worksheet = repo.get_worksheet(project_id, user["user_id"])
        if not worksheet:
            raise HTTPException(status_code=404, detail="Worksheet not found")
        worksheet = normalize_worksheet_bounds(worksheet)

        # Prepare answer records
        answer_records = [
            {
                "project_id": project_id,
                "user_id": user["user_id"],
                "field_id": field_id,
                "answer": answer
            }
            for field_id, answer in answers.items()
            if answer  # Only save non-empty answers
        ]

        # Upsert answers (update if exists, insert if new)
        saved_count = repo.save_worksheet_answers(answer_records)

        from datetime import datetime

        return {
            "project_id": project_id,
            "saved_count": saved_count,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving worksheet answers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save answers: {str(e)}")


@router.post("/{project_id}/fields/{field_id}/suggest")
async def suggest_field_answer(
    project_id: str,
    field_id: str,
    payload: FieldSuggestionRequest,
    user=Depends(get_current_user)
):
    """
    Generate an AI suggestion for a specific worksheet field.
    """
    try:
        if not assistant.is_available():
            raise HTTPException(
                status_code=503,
                detail="AI assistant unavailable: configure GOOGLE_API_KEY to enable suggestions."
            )

        repo = get_repo()
        worksheet = repo.get_worksheet(project_id, user["user_id"])
        if not worksheet:
            raise HTTPException(status_code=404, detail="Worksheet not found")
        worksheet = normalize_worksheet_bounds(worksheet)

        fields = worksheet.get("fields") or []
        field_meta = next((f for f in fields if f.get("id") == field_id), None)
        if not field_meta:
            raise HTTPException(status_code=404, detail="Worksheet field not found")

        existing_answers = repo.get_worksheet_answers(project_id)

        assignment_context: Dict[str, Any] = {
            "title": worksheet.get("filename"),
            "assignment_type": "worksheet",
            "assignment_prompt": worksheet.get("filename"),
        }

        lookup_id: Any = project_id
        try:
            lookup_id = int(project_id)
        except (ValueError, TypeError):
            pass

        try:
            result = repo.client.table("assignment_projects") \
                .select("id, title, assignment_type, assignment_prompt, subject_area, key_requirements") \
                .eq("user_id", user["user_id"]) \
                .eq("id", lookup_id) \
                .limit(1) \
                .execute()
            project_row = result.data[0] if result.data else None
            if project_row:
                assignment_context.update(project_row)
        except Exception as db_exc:
            logger.warning(f"Failed to load assignment context for project {project_id}: {db_exc}")

        suggestion = assistant.suggest_field_answer(
            assignment_context=assignment_context,
            field_metadata=field_meta,
            current_answer=payload.current_answer or existing_answers.get(field_id, ""),
            other_answers=existing_answers,
            instructions=payload.instructions,
        )

        return {
            "project_id": project_id,
            "field_id": field_id,
            "suggestion": suggestion.get("suggestion", ""),
            "explanation": suggestion.get("explanation", ""),
            "confidence": suggestion.get("confidence", "medium"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating worksheet field suggestion: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestion: {str(e)}")


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

        repo = get_repo()

        # Get worksheet and answers
        worksheet = repo.get_worksheet(project_id, user["user_id"])
        if not worksheet:
            raise HTTPException(status_code=404, detail="Worksheet not found")
        worksheet = normalize_worksheet_bounds(worksheet)

        answers = repo.get_worksheet_answers(project_id)

        # Download original PDF
        pdf_url = worksheet["pdf_url"]
        # TODO: Download PDF from Supabase storage
        # For now, return error as this needs implementation

        raise HTTPException(status_code=501, detail="Export feature coming soon")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting worksheet: {e}", exc_info=True)
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
        repo = get_repo()

        # Get worksheet to find storage path
        worksheet = repo.get_worksheet(project_id, user["user_id"])
        if not worksheet:
            raise HTTPException(status_code=404, detail="Worksheet not found")
        worksheet = normalize_worksheet_bounds(worksheet)

        # Delete from storage
        # Extract path from URL and delete
        # TODO: Implement storage deletion

        # Delete answers
        repo.delete_worksheet_answers(project_id)

        # Delete worksheet record
        repo.delete_worksheet(project_id, user["user_id"])

        return {"message": "Worksheet deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting worksheet: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete worksheet: {str(e)}")


