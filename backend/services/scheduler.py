"""
In-process periodic task scheduler (Phase 5.5).
Runs enabled ScheduledTask rows whose interval has elapsed; stores last outcome.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from adapters.base import Message, MessageRole
from sqlalchemy import select

from database.models import ScheduledTask, Task, TaskStatus
from database.session import SessionLocal
from services.orchestrator import call_provider, run_multi_ai_task

logger = logging.getLogger(__name__)

# In-flight guard: never overlap a single scheduled task
_running_ids: set = set()
_loop_task: Optional[asyncio.Task] = None
_tick_seconds = 30


async def _execute_one(sched: ScheduledTask) -> Dict[str, Any]:
    """Run one scheduled objective (mode A single or mode B multi)."""
    if sched.mode == "B" and sched.providers:
        result = await run_multi_ai_task(sched.objective, sched.providers)
        status = result.get("status", "FAILED")
        preview = (result.get("synthesis") or result.get("error") or "")[:2000]
    else:
        provider = (sched.providers or [None])[0]
        result = await call_provider(
            provider or "google",
            [Message(role=MessageRole.USER, content=sched.objective)],
            task_class="scheduled",
        )
        status = result.get("status", "FAILED")
        preview = (result.get("content") or result.get("error") or "")[:2000]
    return {"status": status, "preview": preview}


async def tick() -> List[Dict[str, Any]]:
    """Check due tasks and run them. Returns run summaries (for tests/cron UI)."""
    now = datetime.utcnow()
    due: List[int] = []
    try:
        db = SessionLocal()
        try:
            rows = db.execute(
                select(ScheduledTask).where(ScheduledTask.enabled == True)  # noqa: E712
            ).scalars().all()
            for row in rows:
                if row.id in _running_ids:
                    continue
                if row.interval_minutes < 1:
                    continue
                due_at = (row.last_run_at or datetime.min) + timedelta(minutes=row.interval_minutes)
                if due_at <= now:
                    due.append(row.id)
        finally:
            db.close()
    except Exception:
        logger.exception("scheduler tick: due check failed")
        return []

    runs: List[Dict[str, Any]] = []
    for sched_id in due:
        _running_ids.add(sched_id)
        try:
            db = SessionLocal()
            try:
                sched = db.get(ScheduledTask, sched_id)
                if not sched:
                    continue
                name = sched.name
                outcome = await _execute_one(sched)
                sched = db.get(ScheduledTask, sched_id)  # refresh after await
                sched.last_run_at = datetime.utcnow()
                sched.last_status = outcome["status"]
                sched.last_result = outcome["preview"]
                sched.run_count = (sched.run_count or 0) + 1
                db.commit()
                runs.append({"id": sched_id, "name": name, **outcome})
                logger.info("scheduled '%s' → %s", name, outcome["status"])
            finally:
                db.close()
        except Exception as e:
            logger.exception("scheduled task %s failed", sched_id)
            runs.append({"id": sched_id, "status": "FAILED", "preview": str(e)})
        finally:
            _running_ids.discard(sched_id)
    return runs


async def _loop():
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduler loop error")
        await asyncio.sleep(_tick_seconds)


def start_scheduler():
    global _loop_task
    if _loop_task is None or _loop_task.done():
        _loop_task = asyncio.get_event_loop().create_task(_loop())
        logger.info("scheduler started (tick=%ss)", _tick_seconds)


def stop_scheduler():
    global _loop_task
    if _loop_task and not _loop_task.done():
        _loop_task.cancel()
    _loop_task = None
