"""
Tasks endpoints — multi-IA collaboration (Mode B) and task history.
"""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.base import Message, MessageRole
from api.endpoints.providers import _provider_adapters
from api.endpoints.auth import get_current_user_optional
from config import settings
from core.events import event_bus
from database.models import Task, TaskStatus, User
from database.session import get_db
from services.orchestrator import run_multi_ai_task, call_provider
from services.streaming import stream_chat
from services.orchestrator_c import run_orchestrated

router = APIRouter()


class MultiAITaskRequest(BaseModel):
    objective: str = Field(min_length=3, max_length=8000)
    providers: Optional[List[str]] = None  # None => all free available
    model: Optional[str] = None


class OrchestrateRequest(BaseModel):
    objective: str = Field(min_length=10, max_length=8000)
    providers: Optional[List[str]] = None


class TaskResponse(BaseModel):
    id: int
    objective: str
    mode: str
    status: str
    providers: List[str]
    result: Optional[str]
    error: Optional[str]
    created_at: Optional[str]


class SingleChatRequest(BaseModel):
    provider_id: str
    message: str = Field(min_length=1, max_length=8000)
    model: Optional[str] = None
    history: List[dict] = Field(default_factory=list)


@router.post("/multi", response_model=dict)
async def create_multi_ai_task(request: MultiAITaskRequest):
    """Mode B: run one objective across multiple providers concurrently."""
    providers = request.providers
    if not providers:
        providers = [
            p["provider_id"] for p in settings.available_providers
            if p["available"] and (p["free"] or not settings.free_mode_strict)
        ]
    if not providers:
        raise HTTPException(status_code=400, detail="No hay proveedores disponibles en FREE MODE. Configura una API key gratuita.")
    unknown = [p for p in providers if p not in _provider_adapters]
    if unknown:
        raise HTTPException(status_code=404, detail=f"Proveedores desconocidos: {', '.join(unknown)}")

    result = await run_multi_ai_task(request.objective, providers, model=request.model)
    return result


@router.post("/orchestrate")
async def orchestrate_objective(request: OrchestrateRequest):
    """Mode C: decompose an objective into a DAG of subtasks and execute them."""
    result = await run_orchestrated(request.objective, request.providers)
    if result.get("status") == "FAILED" and result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@router.post("/chat")
async def single_provider_chat(request: SingleChatRequest):
    """Mode A: chat with a single provider."""
    if request.provider_id not in _provider_adapters:
        raise HTTPException(status_code=404, detail=f"Proveedor '{request.provider_id}' no disponible")
    messages = []
    for h in request.history[-20:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append(Message(role=MessageRole(h["role"]), content=h["content"]))
    messages.append(Message(role=MessageRole.USER, content=request.message))

    result = await call_provider(request.provider_id, messages, model=request.model)
    if result["status"] != "SUCCEEDED":
        raise HTTPException(status_code=502, detail=result["error"] or "Proveedor falló")
    return result


class StreamChatRequest(BaseModel):
    provider_id: str
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: Optional[int] = None
    model: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    history: List[dict] = Field(default_factory=list)


@router.post("/chat/stream")
async def stream_provider_chat(request: StreamChatRequest):
    """Mode A with SSE streaming: real-time token delivery from the provider."""
    if request.provider_id not in _provider_adapters:
        raise HTTPException(status_code=404, detail=f"Proveedor '{request.provider_id}' no disponible")
    messages = []
    for h in request.history[-20:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append(Message(role=MessageRole(h["role"]), content=h["content"]))
    messages.append(Message(role=MessageRole.USER, content=request.message))

    return StreamingResponse(
        stream_chat(
            request.provider_id, messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            conversation_id=request.conversation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/", response_model=List[TaskResponse])
async def list_tasks(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    tasks = db.execute(select(Task).order_by(Task.created_at.desc()).offset(offset).limit(limit)).scalars().all()
    return [
        TaskResponse(
            id=t.id,
            objective=t.objective,
            mode=t.mode,
            status=t.status.value if isinstance(t.status, TaskStatus) else str(t.status),
            providers=t.providers or [],
            result=t.result,
            error=t.error,
            created_at=t.created_at.isoformat() if t.created_at else None,
        )
        for t in tasks
    ]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(
        id=task.id,
        objective=task.objective,
        mode=task.mode,
        status=task.status.value if isinstance(task.status, TaskStatus) else str(task.status),
        providers=task.providers or [],
        result=task.result,
        error=task.error,
        created_at=task.created_at.isoformat() if task.created_at else None,
    )


@router.get("/{task_id}/events")
async def task_events(task_id: int, db: Session = Depends(get_db)):
    """Stored events for a task plus live-event history."""
    from database.models import TaskEvent
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    events = db.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at)).scalars().all()
    return {
        "stored": [
            {"type": e.event_type, "status": e.status, "data": e.data, "created_at": e.created_at.isoformat()}
            for e in events
        ],
        "live": event_bus.history(limit=200, task_id=task_id),
    }


@router.delete("/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if isinstance(task.status, TaskStatus) and task.status == TaskStatus.RUNNING:
        task.status = TaskStatus.CANCELLED
        db.commit()
        event_bus.publish("task.cancelled", {}, task_id=task_id, status=TaskStatus.CANCELLED.value)
        return {"cancelled": task_id}
    db.delete(task)
    db.commit()
    return {"deleted": task_id}
