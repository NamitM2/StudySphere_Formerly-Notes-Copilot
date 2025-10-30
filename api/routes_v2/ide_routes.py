# api/routes_v2/ide_routes.py
# IDE Routes for Assignment workspace

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

try:
    from api.auth_supabase import get_current_user
except:
    from api.routes import get_current_user

from api.supa import admin_client
from core.ide.assignment_analyzer import AssignmentAnalyzer
from core.ide.ai_assistant import IDEAssistant

router = APIRouter(prefix="/ide", tags=["ide"])

# Initialize services
analyzer = AssignmentAnalyzer()
assistant = IDEAssistant()

# ======== REQUEST/RESPONSE MODELS ========

class CreateProjectRequest(BaseModel):
    assignment_prompt: str = Field(..., min_length=10)
    title: Optional[str] = None
    due_date: Optional[datetime] = None
    initial_content: Optional[str] = None

class ProjectResponse(BaseModel):
    id: int
    title: str
    assignment_type: str
    subject_area: str
    status: str
    progress_percentage: int
    workspace_structure: Dict[str, Any]
    current_content: str
    created_at: datetime
    last_edited_at: datetime

class UpdateContentRequest(BaseModel):
    project_id: int
    content: str

class AutocompleteRequest(BaseModel):
    project_id: int
    current_text: str
    cursor_position: int

class SuggestNextRequest(BaseModel):
    project_id: int
    current_text: str
    current_section: Optional[str] = None

class GenerateContentRequest(BaseModel):
    project_id: int
    user_request: str
    current_text: str
    generation_mode: str = "scaffold"

class ReviewRequest(BaseModel):
    project_id: int
    content: str
    focus_areas: Optional[List[str]] = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    project_id: int
    message: str
    current_text: str
    chat_history: List[ChatMessage] = []

class ImproveContentRequest(BaseModel):
    project_id: int
    current_text: str

# ======== PROJECT ENDPOINTS ========

@router.post("/projects/create", response_model=ProjectResponse)
async def create_project(
    request: CreateProjectRequest,
    user=Depends(get_current_user)
):
    """Create a new assignment project from a text prompt."""
    supa = admin_client()

    print(f"[IDE] Creating project for user {user['user_id']}")

    # Analyze assignment
    try:
        analysis = analyzer.analyze_assignment(request.assignment_prompt)
        print(f"[IDE] Analysis complete: {analysis['assignment_type']} - {analysis['title']}")
    except Exception as e:
        raise HTTPException(500, f"Failed to analyze: {str(e)}")

    # Create project
    initial_content = request.initial_content or ""
    word_count = len(initial_content.split()) if initial_content else 0

    project_data = {
        "user_id": user["user_id"],
        "title": request.title or analysis["title"],
        "assignment_prompt": request.assignment_prompt,
        "assignment_type": analysis["assignment_type"],
        "subject_area": analysis.get("subject_area", "general"),
        "workspace_structure": analysis["suggested_structure"],
        "current_content": initial_content,
        "ai_instructions": f"This is a {analysis['assignment_type']} assignment about {analysis['title']}.",
        "rubric": analysis.get("rubric", {}),
        "key_requirements": analysis.get("key_requirements", []),
        "status": "in_progress",
        "progress_percentage": 0,
        "word_count": word_count,
        "ai_contribution_percentage": 0,
        "due_date": request.due_date.isoformat() if request.due_date else None,
        "estimated_time_minutes": analysis.get("estimated_time_minutes", 120),
        "has_template": bool(initial_content)
    }

    try:
        result = supa.table("assignment_projects").insert(project_data).execute()
        project = result.data[0]

        return ProjectResponse(
            id=project["id"],
            title=project["title"],
            assignment_type=project["assignment_type"],
            subject_area=project["subject_area"],
            status=project["status"],
            progress_percentage=project["progress_percentage"],
            workspace_structure=project["workspace_structure"],
            current_content=project["current_content"],
            created_at=project["created_at"],
            last_edited_at=project["last_edited_at"]
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to create project: {str(e)}")


@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(user=Depends(get_current_user)):
    """List all projects for the current user."""
    supa = admin_client()

    result = supa.table("assignment_projects").select("*").eq("user_id", user["user_id"]).order("last_edited_at", desc=True).execute()

    return [
        ProjectResponse(
            id=p["id"],
            title=p["title"],
            assignment_type=p["assignment_type"],
            subject_area=p["subject_area"],
            status=p["status"],
            progress_percentage=p["progress_percentage"],
            workspace_structure=p["workspace_structure"],
            current_content=p["current_content"],
            created_at=p["created_at"],
            last_edited_at=p["last_edited_at"]
        )
        for p in result.data
    ]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, user=Depends(get_current_user)):
    """Get a specific project."""
    supa = admin_client()

    result = supa.table("assignment_projects").select("*").eq("id", project_id).eq("user_id", user["user_id"]).execute()

    if not result.data:
        raise HTTPException(404, "Project not found")

    p = result.data[0]
    return ProjectResponse(
        id=p["id"],
        title=p["title"],
        assignment_type=p["assignment_type"],
        subject_area=p["subject_area"],
        status=p["status"],
        progress_percentage=p["progress_percentage"],
        workspace_structure=p["workspace_structure"],
        current_content=p["current_content"],
        created_at=p["created_at"],
        last_edited_at=p["last_edited_at"]
    )


@router.put("/projects/{project_id}/content")
async def update_content(project_id: int, request: UpdateContentRequest, user=Depends(get_current_user)):
    """Update project content (autosave)."""
    supa = admin_client()

    # Verify ownership
    check = supa.table("assignment_projects").select("id").eq("id", project_id).eq("user_id", user["user_id"]).execute()
    if not check.data:
        raise HTTPException(404, "Project not found")

    # Calculate metrics
    word_count = len(request.content.split())
    progress = min(100, int((word_count / 500) * 100))

    # Update
    supa.table("assignment_projects").update({
        "current_content": request.content,
        "word_count": word_count,
        "progress_percentage": progress,
        "last_edited_at": datetime.utcnow().isoformat()
    }).eq("id", project_id).execute()

    return {"success": True, "word_count": word_count, "progress": progress}


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, user=Depends(get_current_user)):
    """Delete a project."""
    supa = admin_client()

    result = supa.table("assignment_projects").select("id").eq("id", project_id).eq("user_id", user["user_id"]).execute()
    if not result.data:
        raise HTTPException(404, "Project not found")

    supa.table("assignment_projects").delete().eq("id", project_id).execute()
    return {"success": True}


# ======== AI ASSISTANT ENDPOINTS ========

@router.post("/autocomplete")
async def autocomplete(request: AutocompleteRequest, user=Depends(get_current_user)):
    """Get autocomplete suggestion."""
    supa = admin_client()

    project = supa.table("assignment_projects").select("*").eq("id", request.project_id).eq("user_id", user["user_id"]).execute()
    if not project.data:
        raise HTTPException(404, "Project not found")

    p = project.data[0]
    context = {
        "assignment_type": p["assignment_type"],
        "title": p["title"],
        "assignment_prompt": p.get("assignment_prompt", ""),
        "subject_area": p.get("subject_area", ""),
        "key_requirements": p["key_requirements"]
    }

    try:
        completion = assistant.autocomplete(
            current_text=request.current_text,
            cursor_position=request.cursor_position,
            assignment_context=context
        )
        return {"completion": completion}
    except Exception as e:
        raise HTTPException(500, f"Autocomplete failed: {str(e)}")


@router.post("/suggest-next")
async def suggest_next(request: SuggestNextRequest, user=Depends(get_current_user)):
    """Get next step suggestions."""
    supa = admin_client()

    project = supa.table("assignment_projects").select("*").eq("id", request.project_id).eq("user_id", user["user_id"]).execute()
    if not project.data:
        raise HTTPException(404, "Project not found")

    p = project.data[0]
    context = {
        "assignment_type": p["assignment_type"],
        "title": p["title"],
        "assignment_prompt": p.get("assignment_prompt", ""),
        "subject_area": p.get("subject_area", ""),
        "key_requirements": p["key_requirements"],
        "suggested_structure": p["workspace_structure"],
        "rubric": p.get("rubric", {})
    }

    try:
        suggestions = assistant.suggest_next_steps(
            current_text=request.current_text,
            assignment_context=context,
            current_section=request.current_section
        )
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(500, f"Suggestions failed: {str(e)}")


@router.post("/generate")
async def generate(request: GenerateContentRequest, user=Depends(get_current_user)):
    """Generate content."""
    supa = admin_client()

    project = supa.table("assignment_projects").select("*").eq("id", request.project_id).eq("user_id", user["user_id"]).execute()
    if not project.data:
        raise HTTPException(404, "Project not found")

    p = project.data[0]
    context = {
        "assignment_type": p["assignment_type"],
        "title": p["title"],
        "assignment_prompt": p.get("assignment_prompt", ""),
        "subject_area": p.get("subject_area", ""),
        "key_requirements": p["key_requirements"],
        "suggested_structure": p["workspace_structure"],
        "rubric": p.get("rubric", {})
    }

    try:
        result = assistant.generate_content(
            user_request=request.user_request,
            current_text=request.current_text,
            assignment_context=context,
            generation_mode=request.generation_mode
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {str(e)}")


@router.post("/review")
async def review(request: ReviewRequest, user=Depends(get_current_user)):
    """Review work and provide feedback."""
    supa = admin_client()

    project = supa.table("assignment_projects").select("*").eq("id", request.project_id).eq("user_id", user["user_id"]).execute()
    if not project.data:
        raise HTTPException(404, "Project not found")

    p = project.data[0]
    context = {
        "assignment_type": p["assignment_type"],
        "title": p["title"],
        "assignment_prompt": p.get("assignment_prompt", ""),
        "subject_area": p.get("subject_area", ""),
        "key_requirements": p["key_requirements"],
        "rubric": p.get("rubric", {})
    }

    try:
        feedback = assistant.review_work(
            content=request.content,
            assignment_context=context,
            focus_areas=request.focus_areas
        )
        return feedback
    except Exception as e:
        raise HTTPException(500, f"Review failed: {str(e)}")


@router.post("/chat")
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    """Chat with AI assistant - no restrictions."""
    supa = admin_client()

    project = supa.table("assignment_projects").select("*").eq("id", request.project_id).eq("user_id", user["user_id"]).execute()
    if not project.data:
        raise HTTPException(404, "Project not found")

    p = project.data[0]
    context = {
        "assignment_type": p["assignment_type"],
        "title": p["title"],
        "assignment_prompt": p.get("assignment_prompt", ""),
        "subject_area": p.get("subject_area", ""),
        "key_requirements": p["key_requirements"],
        "rubric": p.get("rubric", {})
    }

    try:
        result = assistant.chat(
            user_message=request.message,
            current_text=request.current_text,
            assignment_context=context,
            chat_history=[{"role": m.role, "content": m.content} for m in request.chat_history]
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Chat failed: {str(e)}")


@router.post("/improve-content")
async def improve_content(request: ImproveContentRequest, user=Depends(get_current_user)):
    """Get content improvement suggestions (like Grammarly)."""
    supa = admin_client()

    project = supa.table("assignment_projects").select("*").eq("id", request.project_id).eq("user_id", user["user_id"]).execute()
    if not project.data:
        raise HTTPException(404, "Project not found")

    p = project.data[0]
    context = {
        "assignment_type": p["assignment_type"],
        "title": p["title"],
        "assignment_prompt": p.get("assignment_prompt", ""),
        "subject_area": p.get("subject_area", "")
    }

    try:
        result = assistant.improve_content(
            current_text=request.current_text,
            assignment_context=context
        )
        return {"suggestions": result}
    except Exception as e:
        raise HTTPException(500, f"Content improvement failed: {str(e)}")
