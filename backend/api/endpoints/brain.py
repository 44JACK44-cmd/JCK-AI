"""
Brain endpoints — real-time event stream and task execution state.
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import Depends

from core.events import event_bus
from database.models import Task, TaskEvent, TaskStatus
from database.session import get_db

router = APIRouter()


@router.get("/events")
async def stream_events(limit: int = 50, task_id: Optional[int] = None):
    """SSE stream of real execution events (history + live)."""
    return StreamingResponse(
        event_bus.stream(limit=limit, task_id=task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events/history")
async def event_history(limit: int = 100, task_id: Optional[int] = None):
    """Non-streaming view of recent events."""
    return {"events": event_bus.history(limit=limit, task_id=task_id)}


@router.get("/state")
async def brain_state(db: Session = Depends(get_db)):
    """Current system state: tasks, statuses, memory, providers."""
    tasks = db.execute(select(Task).order_by(Task.created_at.desc()).limit(20)).scalars().all()
    status_counts: Dict[str, int] = {}
    for t in tasks:
        key = t.status.value if isinstance(t.status, TaskStatus) else str(t.status)
        status_counts[key] = status_counts.get(key, 0) + 1

    from config import settings
    providers = settings.available_providers

    return {
        "tasks": [
            {
                "id": t.id,
                "objective": t.objective[:200],
                "mode": t.mode,
                "status": t.status.value if isinstance(t.status, TaskStatus) else str(t.status),
                "providers": t.providers,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
        "status_counts": status_counts,
        "providers": providers,
        "free_mode": {
            "enabled": settings.free_mode_enabled,
            "strict": settings.free_mode_strict,
        },
        "memory_enabled": settings.memory_enabled,
        "recent_events": len(event_bus.history(limit=100)),
    }


@router.post("/events/publish")
async def publish_event(payload: Dict[str, Any]):
    """Publish an event (used by local agent and internal services)."""
    event = event_bus.publish(
        payload.get("type", "custom"),
        payload.get("data", {}),
        task_id=payload.get("task_id"),
        status=payload.get("status"),
    )
    return event


@router.get("/routing")
async def routing_metrics(task_class: Optional[str] = None):
    """Adaptive routing metrics (Level 2 learning): per-provider performance."""
    from services.routing import routing_metrics
    if task_class:
        return routing_metrics.recommend(task_class, ["deepseek", "google", "anthropic", "openai"])
    return routing_metrics.snapshot()


@router.post("/routing/recommend")
async def routing_recommend(payload: Dict[str, Any]):
    """Recommend the best provider for a task class based on observed evidence."""
    from services.routing import routing_metrics
    task_class = payload.get("task_class", "general")
    candidates = payload.get("candidates", ["deepseek", "google", "anthropic", "openai"])
    return routing_metrics.recommend(task_class, candidates)
