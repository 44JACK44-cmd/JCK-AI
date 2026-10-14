"""
Memory endpoints — Level 1 of progressive learning: experience store.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database.models import MemoryEntry
from database.session import get_db

router = APIRouter()


class MemoryCreate(BaseModel):
    task_id: Optional[str] = None
    objective: Optional[str] = None
    outcome: Optional[str] = None
    evaluation: Optional[str] = Field(default=None, pattern="^(positive|negative|neutral)$")
    evidence: Dict[str, Any] = Field(default_factory=dict)
    tools_used: List[str] = Field(default_factory=list)
    models_used: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class MemoryResponse(BaseModel):
    id: int
    task_id: Optional[str]
    objective: Optional[str]
    outcome: Optional[str]
    evaluation: Optional[str]
    evidence: Dict[str, Any]
    tools_used: List[str]
    models_used: List[str]
    errors: List[str]
    system_version: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


@router.get("/", response_model=List[MemoryResponse])
async def list_memory(
    q: Optional[str] = None,
    evaluation: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List/search memory entries."""
    query = select(MemoryEntry).order_by(MemoryEntry.created_at.desc())
    if q:
        like = f"%{q}%"
        query = query.where(
            (MemoryEntry.objective.ilike(like)) | (MemoryEntry.outcome.ilike(like))
        )
    if evaluation:
        query = query.where(MemoryEntry.evaluation == evaluation)
    entries = db.execute(query.offset(offset).limit(limit)).scalars().all()
    return [
        MemoryResponse(
            id=e.id,
            task_id=e.task_id,
            objective=e.objective,
            outcome=e.outcome,
            evaluation=e.evaluation,
            evidence=e.evidence or {},
            tools_used=e.tools_used or [],
            models_used=e.models_used or [],
            errors=e.errors or [],
            system_version=e.system_version,
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in entries
    ]


@router.post("/", status_code=201)
async def create_memory(entry: MemoryCreate, db: Session = Depends(get_db)):
    """Store a new experience. Secrets and full file contents must not be included."""
    count = db.execute(select(MemoryEntry)).scalars().all()
    if len(count) >= settings.memory_max_entries:
        raise HTTPException(status_code=429, detail="Memory capacity reached")
    row = MemoryEntry(
        task_id=entry.task_id,
        objective=entry.objective,
        outcome=entry.outcome,
        evaluation=entry.evaluation,
        evidence=entry.evidence,
        tools_used=entry.tools_used,
        models_used=entry.models_used,
        errors=entry.errors,
        system_version=settings.app_version,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        from services.semantics import invalidate_index
        invalidate_index()
    except Exception:
        pass
    return {"id": row.id, "created_at": row.created_at.isoformat()}


@router.delete("/{memory_id}")
async def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    row = db.get(MemoryEntry, memory_id)
    if not row:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    db.delete(row)
    db.commit()
    try:
        from services.semantics import invalidate_index
        invalidate_index()
    except Exception:
        pass
    return {"deleted": memory_id}


@router.get("/search")
async def semantic_search(
    q: str,
    top_k: int = 5,
):
    """Okapi BM25 semantic search over experience memory (local, free)."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Empty query")
    from services.semantics import search_memory
    return search_memory(q, top_k=max(1, min(top_k, 20)))
