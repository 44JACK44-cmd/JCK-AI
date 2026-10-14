"""
Scheduler endpoints — CRUD for periodic tasks + manual tick.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import ScheduledTask
from database.session import get_db

router = APIRouter()


class SchedulerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    objective: str = Field(min_length=5, max_length=8000)
    mode: str = Field(default="A", pattern="^(A|B)$")
    providers: List[str] = Field(default_factory=list)
    interval_minutes: int = Field(default=60, ge=1, le=10080)
    enabled: bool = True


class SchedulerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=128)
    objective: Optional[str] = Field(default=None, min_length=5, max_length=8000)
    mode: Optional[str] = Field(default=None, pattern="^(A|B)$")
    providers: Optional[List[str]] = None
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    enabled: Optional[bool] = None


def _row_out(row: ScheduledTask) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "objective": row.objective,
        "mode": row.mode,
        "providers": row.providers or [],
        "interval_minutes": row.interval_minutes,
        "enabled": row.enabled,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_status": row.last_status,
        "last_result": (row.last_result or "")[:500] or None,
        "run_count": row.run_count or 0,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/")
async def list_scheduled(db: Session = Depends(get_db)):
    rows = db.execute(select(ScheduledTask).order_by(ScheduledTask.id.desc())).scalars().all()
    return [_row_out(r) for r in rows]


@router.post("/", status_code=201)
async def create_scheduled(body: SchedulerCreate, db: Session = Depends(get_db)):
    row = ScheduledTask(
        name=body.name,
        objective=body.objective,
        mode=body.mode,
        providers=body.providers,
        interval_minutes=body.interval_minutes,
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_out(row)


@router.patch("/{sched_id}")
async def update_scheduled(sched_id: int, body: SchedulerUpdate, db: Session = Depends(get_db)):
    row = db.get(ScheduledTask, sched_id)
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _row_out(row)


@router.delete("/{sched_id}")
async def delete_scheduled(sched_id: int, db: Session = Depends(get_db)):
    row = db.get(ScheduledTask, sched_id)
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    db.delete(row)
    db.commit()
    return {"deleted": sched_id}


@router.post("/tick")
async def manual_tick(background: BackgroundTasks):
    """Force one scheduler pass now (also used by tests)."""
    from services.scheduler import tick
    runs = await tick()
    return {"ran": len(runs), "runs": runs}
