"""
Tools endpoints — real web search + URL fetch for the agent and chat.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.web_tools import ToolError, fetch_url, web_search

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    max_results: int = Field(default=5, ge=1, le=8)


class FetchRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    max_chars: int = Field(default=12000, ge=200, le=50000)


@router.post("/search")
async def search_web(request: SearchRequest):
    """Real web search via DuckDuckGo HTML — no API key, FREE MODE."""
    try:
        return await web_search(request.query, max_results=request.max_results)
    except ToolError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/fetch")
async def fetch_page(request: FetchRequest):
    """Fetch a public URL and return readable text (SSRF-protected)."""
    try:
        return await fetch_url(request.url, max_chars=request.max_chars)
    except ToolError as e:
        status = 400 if "blocked" in str(e).lower() or "only http" in str(e).lower() else 502
        raise HTTPException(status_code=status, detail=str(e))
