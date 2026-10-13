"""
Real subprocess execution for the local terminal agent.
Enforces timeouts, output size caps, and cancellation.
"""
import asyncio
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional

from config import settings
from core.events import event_bus
from database.models import ExecutionLog, TaskStatus
from database.session import SessionLocal

MAX_OUTPUT_BYTES = settings.windows_max_output_size_kb * 1024
TIMEOUT_SECONDS = settings.windows_max_command_time_seconds


async def run_command(
    argv: list,
    cwd: str,
    task_id: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Execute an already-validated argv in cwd.
    Returns execution record including exit code, stdout, stderr, duration.
    """
    timeout = timeout or TIMEOUT_SECONDS
    started = time.monotonic()
    started_at = datetime.utcnow()

    event_bus.publish("terminal.started", {"argv": argv, "cwd": cwd}, task_id=task_id, status=TaskStatus.RUNNING.value)

    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except FileNotFoundError:
        # e.g. shell built-ins like `dir`/`cat` are not standalone executables on Windows
        duration_ms = int((time.monotonic() - started) * 1000)
        result = {
            "command": " ".join(argv),
            "cwd": cwd,
            "exit_code": 127,
            "stdout": "",
            "stderr": f"Executable not found: {argv[0]}. Usa un programa real instalado en el sistema.",
            "status": TaskStatus.FAILED.value,
            "duration_ms": duration_ms,
            "timed_out": False,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            "task_id": task_id,
        }
        event_bus.publish("terminal.finished", {"command": result["command"], "exit_code": 127, "status": result["status"]}, task_id=task_id, status=result["status"])
        return result

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
        cancelled = False
    except asyncio.TimeoutError:
        process.kill()
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=5)
        except asyncio.TimeoutError:
            stdout_bytes, stderr_bytes = b"", b""
        cancelled = False
        timed_out = True
    else:
        timed_out = False

    duration_ms = int((time.monotonic() - started) * 1000)

    stdout = (stdout_bytes or b"")[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    stderr = (stderr_bytes or b"")[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")

    if timed_out:
        status = TaskStatus.FAILED.value
        stderr = (stderr + f"\n[TIMEOUT] Command exceeded {timeout}s and was killed").strip()
        exit_code = -1
    else:
        exit_code = process.returncode
        status = TaskStatus.SUCCEEDED.value if exit_code == 0 else TaskStatus.FAILED.value

    result = {
        "command": " ".join(argv),
        "cwd": cwd,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "status": status,
        "duration_ms": duration_ms,
        "timed_out": timed_out,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
        "task_id": task_id,
    }

    # Persist execution log (best-effort; never block the response on DB issues)
    try:
        db = SessionLocal()
        db.add(ExecutionLog(
            task_id=task_id,
            command=result["command"],
            cwd=cwd,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            status=status,
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=datetime.utcnow(),
        ))
        db.commit()
        db.close()
    except Exception:
        pass

    event_bus.publish("terminal.finished", {
        "command": result["command"],
        "exit_code": exit_code,
        "status": status,
        "duration_ms": duration_ms,
    }, task_id=task_id, status=status)

    return result
