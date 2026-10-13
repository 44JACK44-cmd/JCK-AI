"""
Projects endpoints — workspace browsing and file operations
restricted to authorized directories.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import workspace

router = APIRouter()


class WriteFileRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str = ""


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    root: Optional[str] = None
    max_results: int = Field(default=50, ge=1, le=500)


@router.get("/")
async def list_roots():
    """List authorized workspace roots."""
    return workspace.list_directory()


@router.get("/browse")
async def browse(path: Optional[str] = None):
    """Browse a directory inside the authorized workspace."""
    try:
        return workspace.list_directory(path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/file")
async def get_file(path: str):
    """Read a file inside the authorized workspace."""
    try:
        return workspace.read_file(path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))


@router.post("/file")
async def put_file(request: WriteFileRequest):
    """Create or overwrite a file inside the authorized workspace."""
    try:
        return workspace.write_file(request.path, request.content)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))


@router.delete("/file")
async def remove_file(path: str):
    """Delete a file inside the authorized workspace (requires prior authorization)."""
    try:
        return workspace.delete_file(path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/search")
async def search_files(request: SearchRequest):
    """Search file names and contents inside the authorized workspace."""
    try:
        results = workspace.search(request.query, request.root, request.max_results)
        return {"query": request.query, "count": len(results), "results": results}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
