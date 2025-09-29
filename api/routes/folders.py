# api/routes/folders.py
from __future__ import annotations
from typing import List, Dict
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()
FOLDERS: List[Dict] = []

class NewFolder(BaseModel):
    name: str = Field(..., min_length=1)

@router.get("/folders")
def get_folders():
    return {"folders": FOLDERS}

@router.post("/folders")
def create_folder(body: NewFolder):
    f = {"id": f"fld_{len(FOLDERS)+1}", "name": body.name}
    FOLDERS.append(f)
    return {"folder": f}
