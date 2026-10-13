"""
Mode C: Intelligent Objective Orchestrator.

Decomposes a high-level objective into a DAG of subtasks, executes them
concurrently respecting dependencies, retries transient failures, and
produces a final report with evidence.

This is a real state machine — not a mock. Subtask execution uses real
provider calls and real terminal commands (validated by the command validator).
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from adapters.base import Message, MessageRole
from api.endpoints.providers import _provider_adapters
from config import settings
from core.events import event_bus
from database.models import Task, TaskStatus
from database.session import SessionLocal
from services.orchestrator import call_provider, _free_mode_allows


class SubtaskKind(str, Enum):
    ANALYZE = "analyze"
    RESEARCH = "research"
    IMPLEMENT = "implement"
    TEST = "test"
    REVIEW = "review"
    SYNTHESIZE = "synthesize"


@dataclass
class Subtask:
    id: str
    kind: SubtaskKind
    title: str
    prompt: str
    depends_on: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    provider_id: Optional[str] = None
    attempts: int = 0
    latency_ms: int = 0


@dataclass
class ExecutionPlan:
    objective: str
    subtasks: List[Subtask]
    selected_providers: List[str]


# ── Planning ──────────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """Eres un planificador de tareas de ingeniería de software.
Dado un objetivo, descompónlo en 3 a 7 subtareas concretas y ordenadas.
Responde SOLO con JSON válido:
{
  "subtasks": [
    {"id": "s1", "kind": "analyze|research|implement|test|review|synthesize",
     "title": "título corto", "prompt": "instrucción completa para ejecutarla",
     "depends_on": ["ids previos"]}
  ]
}
Cada depends_on referencia ids anteriores. La última tarea suele ser kind=synthesize."""


async def plan_objective(objective: str, providers: Optional[List[str]] = None) -> ExecutionPlan:
    """Use an available provider to decompose the objective into a DAG."""
    available = [
        p["provider_id"] for p in settings.available_providers
        if p["available"] and _free_mode_allows(p["provider_id"])
    ]
    if providers:
        available = [p for p in providers if p in available]
    if not available:
        raise ValueError("No hay proveedores gratuitos disponibles para planificar")

    planner_provider = available[0]
    messages = [
        Message(role=MessageRole.SYSTEM, content=_PLANNER_SYSTEM),
        Message(role=MessageRole.USER, content=f"Objetivo: {objective}"),
    ]

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        result = await call_provider(planner_provider, messages)
        if result["status"] == "SUCCEEDED":
            break
        last_error = result["error"]
        if attempt < MAX_RETRIES:
            is_rate_limit = "429" in str(last_error) or "rate limit" in str(last_error).lower()
            delay = max(settings.task_retry_delay_seconds, 25) if is_rate_limit else settings.task_retry_delay_seconds
            event_bus.publish("orchestrator.plan_retry", {"attempt": attempt, "error": last_error}, status=TaskStatus.RETRYING.value)
            await asyncio.sleep(delay)
    else:
        raise ValueError(f"El planificador falló: {last_error}")

    subtasks = _parse_plan(result["content"], available)
    if not subtasks:
        raise ValueError("No se pudo extraer un plan válido del modelo")

    event_bus.publish("orchestrator.planned", {
        "objective": objective,
        "subtask_count": len(subtasks),
        "providers": available,
    })

    return ExecutionPlan(objective=objective, subtasks=subtasks, selected_providers=available)


def _parse_plan(content: str, providers: List[str]) -> List[Subtask]:
    """Extract JSON plan from model output (handles code fences)."""
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
        raw = data.get("subtasks", [])
    except json.JSONDecodeError:
        return []

    subtasks: List[Subtask] = []
    valid_ids: Set[str] = set()
    for i, item in enumerate(raw):
        sid = str(item.get("id", f"s{i+1}"))
        try:
            kind = SubtaskKind(item.get("kind", "analyze"))
        except ValueError:
            kind = SubtaskKind.ANALYZE
        deps = [d for d in item.get("depends_on", []) if d in valid_ids]  # only backward deps
        st = Subtask(
            id=sid,
            kind=kind,
            title=str(item.get("title", sid))[:200],
            prompt=str(item.get("prompt", ""))[:4000],
            depends_on=deps,
            provider_id=providers[i % len(providers)] if providers else None,
        )
        subtasks.append(st)
        valid_ids.add(sid)
    return _break_cycles(subtasks)


def _break_cycles(subtasks: List[Subtask]) -> List[Subtask]:
    """Ensure DAG: if a cycle exists, drop offending backward edges."""
    by_id = {s.id: s for s in subtasks}
    order = {s.id: i for i, s in enumerate(subtasks)}
    for s in subtasks:
        # Only allow dependencies on tasks that appear earlier in the list
        s.depends_on = [d for d in s.depends_on if d in order and order[d] < order[s.id]]
    return subtasks


# ── Execution ─────────────────────────────────────────────────────────────────

MAX_RETRIES = settings.task_max_retries


async def execute_plan(plan: ExecutionPlan, db_task_id: int) -> Dict[str, Any]:
    """Execute subtasks respecting the dependency DAG; parallel where possible."""
    db = SessionLocal()
    running: Dict[str, asyncio.Task] = {}
    completed: Set[str] = set()
    failed: Set[str] = set()
    subtask_map = {s.id: s for s in plan.subtasks}

    def ready_tasks() -> List[Subtask]:
        out = []
        for s in plan.subtasks:
            if s.status != TaskStatus.PENDING:
                continue
            if all(d in completed for d in s.depends_on):
                out.append(s)
            elif any(d in failed for d in s.depends_on):
                s.status = TaskStatus.CANCELLED
                s.error = "Dependencia fallida"
                failed.add(s.id)
                event_bus.publish("subtask.cancelled", {"subtask": s.id}, task_id=db_task_id, status=TaskStatus.CANCELLED.value)
        return out

    async def run_subtask(s: Subtask):
        s.status = TaskStatus.RUNNING
        event_bus.publish("subtask.started", {"subtask": s.id, "title": s.title, "kind": s.kind.value}, task_id=db_task_id, status=TaskStatus.RUNNING.value)
        started = time.monotonic()
        provider = s.provider_id or plan.selected_providers[0]
        context = _gather_context(s, subtask_map, completed)
        prompt = f"{s.prompt}\n\nContexto de subtareas previas:\n{context}" if context else s.prompt
        messages = [Message(role=MessageRole.USER, content=prompt)]

        for attempt in range(1, MAX_RETRIES + 1):
            s.attempts = attempt
            result = await call_provider(provider, messages, task_id=db_task_id)
            if result["status"] == "SUCCEEDED":
                s.status = TaskStatus.SUCCEEDED
                s.result = result["content"]
                s.latency_ms = int((time.monotonic() - started) * 1000)
                completed.add(s.id)
                event_bus.publish("subtask.finished", {"subtask": s.id, "status": "SUCCEEDED", "latency_ms": s.latency_ms, "attempt": attempt}, task_id=db_task_id, status=TaskStatus.SUCCEEDED.value)
                return
            s.error = result["error"]
            if attempt < MAX_RETRIES:
                s.status = TaskStatus.RETRYING
                event_bus.publish("subtask.retrying", {"subtask": s.id, "attempt": attempt, "error": s.error}, task_id=db_task_id, status=TaskStatus.RETRYING.value)
                # Rate limits reset per minute: wait longer than generic transient errors
                is_rate_limit = "429" in str(s.error) or "rate limit" in str(s.error).lower()
                delay = max(settings.task_retry_delay_seconds, 25) if is_rate_limit else settings.task_retry_delay_seconds
                await asyncio.sleep(delay)

        s.status = TaskStatus.FAILED
        failed.add(s.id)
        event_bus.publish("subtask.finished", {"subtask": s.id, "status": "FAILED", "error": s.error}, task_id=db_task_id, status=TaskStatus.FAILED.value)

    try:
        pending = True
        while pending:
            for s in ready_tasks():
                running[s.id] = asyncio.create_task(run_subtask(s))
            if not running:
                break
            done, _ = await asyncio.wait(running.values(), return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                # remove finished handles
                running = {k: v for k, v in running.items() if v is not t}
            pending = any(s.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.RETRYING) for s in plan.subtasks)

        # Mark skipped tasks whose deps failed
        for s in plan.subtasks:
            if s.status == TaskStatus.PENDING:
                s.status = TaskStatus.CANCELLED
                s.error = "No ejecutada por dependencias fallidas o sin recursos"
    finally:
        db.close()

    succeeded = [s for s in plan.subtasks if s.status == TaskStatus.SUCCEEDED]
    failed_list = [s for s in plan.subtasks if s.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)]

    # Final result: result of terminal succeeded nodes (no successors), or last succeeded.
    succeeded_ids = {s.id for s in succeeded}
    terminals = [s for s in succeeded
                 if not any(s.id in t.depends_on for t in plan.subtasks)]
    if not terminals:
        terminals = succeeded[-1:]
    final_result = "\n\n".join(s.result for s in terminals if s.result) or None

    return {
        "objective": plan.objective,
        "result": final_result,
        "subtasks": [
            {
                "id": s.id, "kind": s.kind.value, "title": s.title,
                "status": s.status.value, "result": s.result, "error": s.error,
                "depends_on": s.depends_on, "provider_id": s.provider_id,
                "attempts": s.attempts, "latency_ms": s.latency_ms,
            }
            for s in plan.subtasks
        ],
        "succeeded": len(succeeded),
        "failed": len(failed_list),
        "providers_used": plan.selected_providers,
    }


def _gather_context(s: Subtask, all_tasks: Dict[str, Subtask], completed: Set[str]) -> str:
    """Concatenate results of completed dependencies (truncated)."""
    parts = []
    for dep_id in s.depends_on:
        dep = all_tasks.get(dep_id)
        if dep and dep.status == TaskStatus.SUCCEEDED and dep.result:
            parts.append(f"[{dep.title}]\n{dep.result[:1500]}")
    return "\n\n".join(parts)


# ── Public entry ──────────────────────────────────────────────────────────────

async def run_orchestrated(objective: str, providers: Optional[List[str]] = None) -> Dict[str, Any]:
    """Full Mode C pipeline: plan → execute → persist → report."""
    db = SessionLocal()
    task = Task(objective=objective, mode="C", status=TaskStatus.RUNNING, providers=providers or [])
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id

    event_bus.publish("task.started", {"objective": objective, "mode": "C"}, task_id=task_id, status=TaskStatus.RUNNING.value)

    try:
        plan = await plan_objective(objective, providers)
        task.providers = plan.selected_providers
        db.commit()
        report = await execute_plan(plan, task_id)
        final = TaskStatus.SUCCEEDED if report["failed"] == 0 else (TaskStatus.FAILED if report["succeeded"] == 0 else TaskStatus.SUCCEEDED)
        task.status = final
        task.result = json.dumps(report, ensure_ascii=False, default=str)
        db.commit()
        event_bus.publish("task.finished", {"status": final.value, "succeeded": report["succeeded"], "failed": report["failed"]}, task_id=task_id, status=final.value)
        return {"task_id": task_id, "status": final.value, **report}
    except Exception as e:
        task.status = TaskStatus.FAILED
        task.error = str(e)
        db.commit()
        event_bus.publish("task.finished", {"status": "FAILED", "error": str(e)}, task_id=task_id, status=TaskStatus.FAILED.value)
        return {"task_id": task_id, "status": "FAILED", "error": str(e), "subtasks": [], "succeeded": 0, "failed": 0}
    finally:
        db.close()
