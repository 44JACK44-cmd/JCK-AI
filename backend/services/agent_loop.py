"""
Autonomous agent loop (Phase 5): plan → act → observe → repeat.

The LLM receives the objective plus live tool results and must answer with a
single JSON object deciding the next action. Tools are real: filesystem ops
restricted to authorized roots, validated terminal, web search, URL fetch.
Events stream to the client as SSE.
"""
import asyncio
import json
import os
import re
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from adapters.base import Message, MessageRole
from api.endpoints.providers import _provider_adapters
from config import settings
from core.events import event_bus
from database.models import Task, TaskStatus
from database.session import SessionLocal
from services.command_validator import (
    is_sensitive_path,
    resolve_and_check_cwd,
    validate_command,
)
from services.orchestrator import _free_mode_allows, call_provider
from services.process_runner import run_command
from services.web_tools import ToolError, fetch_url, web_search

DEFAULT_MAX_STEPS = 8
MAX_TOOL_OUTPUT = 6000

SYSTEM_PROMPT = """Eres un agente autónomo de desarrollo en Windows. Trabajas paso a paso.
En CADA turno debes responder EXCLUSIVAMENTE con un objeto JSON (sin texto extra, sin markdown) de esta forma:

{"thought": "<tu razonamiento breve>", "action": "<acción>", "params": {...}}

Acciones disponibles:
- list_dir: {"action":"list_dir","params":{"path":"."}}  (ruta relativa o absoluta dentro de raíces autorizadas)
- read_file: {"action":"read_file","params":{"path":"archivo.py"}}
- write_file: {"action":"write_file","params":{"path":"archivo.py","content":"..."}}
- terminal: {"action":"terminal","params":{"command":"pytest -q"}}  (solo programas permitidos: git, python, npm, pytest, etc.; sin ; | > &&)
- web_search: {"action":"web_search","params":{"query":"texto"}}
- fetch_url: {"action":"fetch_url","params":{"url":"https://..."}}
- final: {"action":"final","params":{"answer":"respuesta final completa"}}

Reglas:
1. Usa final SOLO cuando el objetivo esté resuelto o agotado.
2. Máximo 8 pasos; sé eficiente.
3. No inventes salidas de herramientas; lee las observaciones reales.
4. Nunca toques archivos .env, claves ni rutas sensibles.
5. Responde en el idioma del objetivo (español por defecto)."""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract the first JSON object from an LLM reply (tolerates code fences)."""
    if not text:
        return None
    cleaned = re.sub(r"(?is)```(?:json)?", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _clip(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "\n…[truncated]"


def _default_provider() -> Optional[str]:
    """Pick the first FREE-mode-allowed provider with a registered adapter."""
    for pid in ("google", "deepseek", "anthropic", "openai"):
        if pid in _provider_adapters and _free_mode_allows(pid):
            return pid
    for pid, adapter in _provider_adapters.items():
        if _free_mode_allows(pid):
            return pid
    return None


async def _exec_tool(action: str, params: Dict[str, Any], cwd: str) -> str:
    """Execute one tool and return a text observation for the LLM."""
    params = params or {}

    if action == "list_dir":
        path = params.get("path") or "."
        ok, resolved = resolve_and_check_cwd(
            path if os.path.isabs(path) else f"{cwd}/{path}"
        )
        if not ok:
            return f"ERROR: {resolved}"

        if not os.path.isdir(resolved):
            return f"ERROR: not a directory: {resolved}"
        entries = sorted(os.scandir(resolved), key=lambda e: (not e.is_dir(), e.name.lower()))
        lines = []
        for e in entries[:80]:
            kind = "dir " if e.is_dir() else "file"
            size = e.stat().st_size if e.is_file() else 0
            lines.append(f"{kind} {e.name}" + (f" ({size} B)" if kind == "file" else ""))
        return _clip("\n".join(lines) or "(empty)")

    if action == "read_file":
        path = params.get("path") or ""
        ok, resolved = resolve_and_check_cwd(
            path if os.path.isabs(path) else f"{cwd}/{path}"
        )
        if not ok:
            return f"ERROR: {resolved}"
        if is_sensitive_path(resolved):
            return "ERROR: sensitive file, access denied"
        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(settings.agent_max_file_size_mb * 1024 * 1024)
            return _clip(content)
        except OSError as e:
            return f"ERROR reading file: {e}"

    if action == "write_file":
        path = params.get("path") or ""
        content = params.get("content") or ""
        ok, resolved = resolve_and_check_cwd(
            path if os.path.isabs(path) else f"{cwd}/{path}"
        )
        if not ok:
            return f"ERROR: {resolved}"
        if is_sensitive_path(resolved):
            return "ERROR: sensitive file, access denied"
        try:
            os.makedirs(os.path.dirname(resolved) or resolved, exist_ok=True)
            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)
            return f"WROTE {len(content)} chars to {resolved}"
        except OSError as e:
            return f"ERROR writing file: {e}"

    if action == "terminal":
        command = params.get("command") or ""
        ok, msg, argv = validate_command(command)
        if not ok:
            return f"ERROR: {msg}"
        result = await run_command(argv, cwd=cwd)
        out = result.get("stdout", "")
        err = result.get("stderr", "")
        return _clip(
            f"exit={result['exit_code']}\nSTDOUT:\n{out}\nSTDERR:\n{err}".strip()
        )

    if action == "web_search":
        try:
            data = await web_search(params.get("query") or "", max_results=5)
            lines = [f"{i+1}. {r['title']} — {r['url']}\n   {r['snippet']}" for i, r in enumerate(data["results"])]
            return _clip("\n".join(lines))
        except ToolError as e:
            return f"ERROR: {e}"

    if action == "fetch_url":
        try:
            data = await fetch_url(params.get("url") or "", max_chars=8000)
            return _clip(data["text"])
        except ToolError as e:
            return f"ERROR: {e}"

    return f"ERROR: unknown action '{action}'"


async def run_agent(
    objective: str,
    provider_id: Optional[str] = None,
    cwd: Optional[str] = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Autonomous loop. Yields event dicts:
    {event: start|step|tool|observation|final|error|done, ...}
    """
    provider = provider_id or _default_provider()
    started = time.monotonic()
    max_steps = max(1, min(max_steps, 16))

    if not provider or provider not in _provider_adapters:
        yield {"event": "error", "detail": "No hay proveedor disponible en FREE MODE"}
        return
    if not _free_mode_allows(provider):
        yield {"event": "error", "detail": f"Proveedor '{provider}' bloqueado por FREE MODE"}
        return

    ok, resolved_cwd = resolve_and_check_cwd(cwd)
    if not ok:
        yield {"event": "error", "detail": resolved_cwd}
        return

    db = SessionLocal()
    task = Task(objective=objective, mode="AGENT", status=TaskStatus.RUNNING, providers=[provider])
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()

    event_bus.publish(
        "agent.started",
        {"objective": objective, "provider": provider, "cwd": resolved_cwd},
        task_id=str(task_id),
        status=TaskStatus.RUNNING.value,
    )
    yield {
        "event": "start",
        "task_id": task_id,
        "provider": provider,
        "cwd": resolved_cwd,
        "max_steps": max_steps,
    }

    history: List[Message] = [
        Message(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
        Message(
            role=MessageRole.USER,
            content=(
                f"Objetivo: {objective}\n"
                f"Directorio de trabajo: {resolved_cwd}\n"
                f"Pasos disponibles: {max_steps}\n"
                "Empieza. Responde solo con el JSON de la acción."
            ),
        ),
    ]

    final_answer: Optional[str] = None
    error_text: Optional[str] = None
    steps_used = 0
    tool_names: List[str] = []

    for step in range(1, max_steps + 1):
        steps_used = step
        yield {"event": "step", "step": step, "max_steps": max_steps}

        result = await call_provider(
            provider, history, task_id=str(task_id), task_class="agent"
        )
        if result["status"] != "SUCCEEDED":
            error_text = result.get("error") or "Proveedor falló"
            yield {"event": "error", "detail": error_text}
            break

        reply = (result.get("content") or "").strip()
        action_obj = _extract_json(reply)

        if action_obj is None:
            # Model replied free text — treat as final if long enough, else nudge
            if len(reply) > 40 and step >= 2:
                final_answer = reply
                yield {"event": "final", "answer": reply, "step": step}
                break
            history.append(Message(role=MessageRole.ASSISTANT, content=reply or "(vacío)"))
            history.append(
                Message(
                    role=MessageRole.USER,
                    content="Respuesta inválida. Debes responder SOLO con el JSON de la acción siguiente.",
                )
            )
            yield {"event": "tool", "action": "_reprompt", "params": {}, "step": step}
            continue

        action = (action_obj.get("action") or "").strip().lower()
        params = action_obj.get("params") or {}
        thought = action_obj.get("thought") or ""

        yield {
            "event": "step",
            "step": step,
            "thought": thought,
            "action": action,
            "params": {k: (str(v)[:200] if not isinstance(v, (dict, list)) else v) for k, v in params.items()},
        }

        if action == "final":
            final_answer = params.get("answer") or reply
            yield {"event": "final", "answer": final_answer, "step": step}
            break

        yield {"event": "tool", "action": action, "params": params, "step": step}
        tool_names.append(action)

        observation = await _exec_tool(action, params, resolved_cwd)
        yield {"event": "observation", "action": action, "output": observation[:2000], "step": step}

        history.append(Message(role=MessageRole.ASSISTANT, content=json.dumps(action_obj, ensure_ascii=False)))
        history.append(
            Message(
                role=MessageRole.TOOL,
                content=f"[{action}] → {observation}",
            )
        )
        history.append(
            Message(
                role=MessageRole.USER,
                content="Observación recibida. Decide la siguiente acción (JSON) o final.",
            )
        )
    else:
        # loop exhausted without final
        final_answer = (
            "Se alcanzó el máximo de pasos sin acción final. "
            "Última observación disponible en los eventos del agente."
        )
        yield {"event": "final", "answer": final_answer, "step": steps_used, "exhausted": True}

    duration_ms = int((time.monotonic() - started) * 1000)
    status = TaskStatus.SUCCEEDED if final_answer and not error_text else TaskStatus.FAILED
    try:
        db = SessionLocal()
        task = db.get(Task, task_id)
        if task:
            task.status = status
            task.result = final_answer
            task.error = error_text
            db.commit()
        db.close()
    except Exception:
        pass

    event_bus.publish(
        "agent.finished",
        {"status": status.value, "steps": steps_used, "duration_ms": duration_ms},
        task_id=str(task_id),
        status=status.value,
    )
    yield {
        "event": "done",
        "task_id": task_id,
        "status": status.value,
        "steps": steps_used,
        "tools_used": tool_names,
        "duration_ms": duration_ms,
    }
