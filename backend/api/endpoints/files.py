"""
Files endpoints — attachment-style file access within authorized storage.
Delegates path authorization to services.workspace.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import workspace

router = APIRouter()


class FileContentRequest(BaseModel):
    path: str
    content: str = ""


@router.get("/")
async def root():
    return workspace.list_directory()


@router.get("/read")
async def read(path: str):
    try:
        return workspace.read_file(path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/write")
async def write(request: FileContentRequest):
    try:
        return workspace.write_file(request.path, request.content)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
