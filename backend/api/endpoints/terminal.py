"""
Terminal endpoints — validated real command execution on the local machine.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc

from services.command_validator import validate_command, resolve_and_check_cwd
from services.process_runner import run_command
from database.models import ExecutionLog
from database.session import get_db
from fastapi import Depends
from sqlalchemy.orm import Session

router = APIRouter()


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    cwd: Optional[str] = None
    task_id: Optional[str] = None
    timeout: Optional[int] = Field(default=None, ge=1, le=600)


class CommandResponse(BaseModel):
    command: str
    cwd: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    status: str
    duration_ms: int
    timed_out: bool
    started_at: str
    finished_at: str
    task_id: Optional[str] = None


@router.post("/execute", response_model=CommandResponse)
async def execute_command(request: CommandRequest):
    """Execute an allowlisted command inside an authorized directory."""
    ok, cwd = resolve_and_check_cwd(request.cwd)
    if not ok:
        raise HTTPException(status_code=403, detail=cwd)

    ok, message, argv = validate_command(request.command)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    result = await run_command(argv, cwd=cwd, task_id=request.task_id, timeout=request.timeout)
    return CommandResponse(**result)


@router.get("/allowed")
async def list_allowed_commands():
    """Return the current command policy so the UI can show what is permitted."""
    from services.command_validator import ALLOWED_COMMANDS, FORBIDDEN_COMMANDS
    from config import settings
    return {
        "allowed": sorted(ALLOWED_COMMANDS),
        "forbidden": sorted(FORBIDDEN_COMMANDS),
        "max_timeout_seconds": settings.windows_max_command_time_seconds,
        "max_output_kb": settings.windows_max_output_size_kb,
        "authorized_roots": settings.agent_allowed_directories,
    }


class HistoryItem(BaseModel):
    id: int
    command: str
    cwd: str
    exit_code: Optional[int]
    status: str
    duration_ms: Optional[int]
    started_at: Optional[str]
    stdout: Optional[str] = None
    stderr: Optional[str] = None


@router.get("/history", response_model=List[HistoryItem])
async def command_history(limit: int = 50, db: Session = Depends(get_db)):
    """Persisted execution history (terminal log) for the UI."""
    limit = max(1, min(limit, 200))
    rows = db.execute(
        select(ExecutionLog).order_by(desc(ExecutionLog.started_at)).limit(limit)
    ).scalars().all()
    return [
        HistoryItem(
            id=r.id,
            command=r.command,
            cwd=r.cwd,
            exit_code=r.exit_code,
            status=r.status,
            duration_ms=r.duration_ms,
            started_at=r.started_at.isoformat() if r.started_at else None,
            stdout=(r.stdout or "")[-4000:] or None,
            stderr=(r.stderr or "")[-2000:] or None,
        )
        for r in rows
    ]
