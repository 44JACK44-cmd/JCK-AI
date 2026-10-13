"""
Multi-AI collaboration and orchestration service (Modes B and C).
Calls real provider adapters concurrently, then synthesizes.
"""
import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from adapters.base import AIProvider, Message, MessageRole, ProviderError
from api.endpoints.providers import _provider_adapters
from config import settings
from core.events import event_bus
from database.models import Task, TaskStatus
from database.session import SessionLocal


def _free_mode_allows(provider_id: str) -> bool:
    if not (settings.free_mode_enabled and settings.free_mode_strict):
        return True
    # Only providers classified as free are permitted in strict FREE MODE
    for p in settings.available_providers:
        if p["provider_id"] == provider_id:
            return bool(p["free"])
    return False


async def call_provider(
    provider_id: str,
    messages: List[Message],
    model: Optional[str] = None,
    task_id: Optional[int] = None,
    task_class: str = "general",
) -> Dict[str, Any]:
    """Invoke a single provider adapter and capture result/error + latency.
    Records outcomes to adaptive routing metrics (Level 2 learning)."""
    started = time.monotonic()
    adapter: Optional[AIProvider] = _provider_adapters.get(provider_id)
    if adapter is None:
        return {
            "provider_id": provider_id,
            "status": "UNAVAILABLE",
            "content": None,
            "error": f"No adapter registered for '{provider_id}'",
            "latency_ms": 0,
        }
    if not _free_mode_allows(provider_id):
        return {
            "provider_id": provider_id,
            "status": "PAID_ROUTE_BLOCKED",
            "content": None,
            "error": "Bloqueado por la política FREE MODE",
            "latency_ms": 0,
        }
    try:
        event_bus.publish("provider.call.started", {"provider_id": provider_id}, task_id=task_id, status=TaskStatus.RUNNING.value)
        response = await adapter.chat_completion(messages, model=model)
        latency = int((time.monotonic() - started) * 1000)
        event_bus.publish("provider.call.finished", {"provider_id": provider_id, "latency_ms": latency}, task_id=task_id, status=TaskStatus.SUCCEEDED.value)
        # Record success for adaptive routing (memory + metrics)
        try:
            from services.routing import persist_outcome
            await persist_outcome(provider_id, task_class, True, latency,
                                  objective=messages[-1].content[:200] if messages else "")
        except Exception:
            pass
        return {
            "provider_id": provider_id,
            "status": "SUCCEEDED",
            "content": response.content,
            "model": response.model,
            "usage": response.usage,
            "error": None,
            "latency_ms": latency,
        }
    except ProviderError as e:
        latency = int((time.monotonic() - started) * 1000)
        event_bus.publish("provider.call.failed", {"provider_id": provider_id, "error": e.message}, task_id=task_id, status=TaskStatus.FAILED.value)
        try:
            from services.routing import persist_outcome
            await persist_outcome(provider_id, task_class, False, latency,
                                  objective=messages[-1].content[:200] if messages else "",
                                  error=e.message)
        except Exception:
            pass
        return {"provider_id": provider_id, "status": "FAILED", "content": None, "error": e.message, "latency_ms": latency}
    except Exception as e:
        latency = int((time.monotonic() - started) * 1000)
        event_bus.publish("provider.call.failed", {"provider_id": provider_id, "error": str(e)}, task_id=task_id, status=TaskStatus.FAILED.value)
        try:
            from services.routing import persist_outcome
            await persist_outcome(provider_id, task_class, False, latency,
                                  objective=messages[-1].content[:200] if messages else "",
                                  error=str(e))
        except Exception:
            pass
        return {"provider_id": provider_id, "status": "FAILED", "content": None, "error": str(e), "latency_ms": latency}


def _find_disagreements(responses: List[Dict[str, Any]]) -> List[str]:
    """Simple disagreement detector: distinct first-line claims / different answers."""
    contents = [r["content"].strip() for r in responses if r.get("content")]
    if len(set(contents)) <= 1:
        return []
    disagreements = []
    if len(set(contents)) == len(contents):
        disagreements.append("Las respuestas difieren entre sí en el contenido completo.")
    # keyword-level overlap
    words = [set(c.lower().split()) for c in contents]
    if words:
        common = set.intersection(*words) if len(words) > 1 else words[0]
        if len(common) < 10:
            disagreements.append("Baja superposición léxica entre respuestas: revisar afirmaciones contradictorias manualmente.")
    return disagreements


async def run_multi_ai_task(objective: str, providers: List[str], model: Optional[str] = None) -> Dict[str, Any]:
    """Mode B: run the same objective across multiple providers concurrently."""
    db = SessionLocal()
    task = Task(objective=objective, mode="B", status=TaskStatus.RUNNING, providers=providers)
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id

    event_bus.publish("task.started", {"objective": objective, "providers": providers}, task_id=task_id, status=TaskStatus.RUNNING.value)

    messages = [Message(role=MessageRole.USER, content=objective)]
    results = await asyncio.gather(
        *[call_provider(p, messages, model=model, task_id=task_id) for p in providers]
    )
    results = list(results)

    successful = [r for r in results if r["status"] == "SUCCEEDED"]
    failed = [r for r in results if r["status"] != "SUCCEEDED"]

    synthesis = None
    disagreements = _find_disagreements(successful)

    if successful:
        synthesis_prompt = (
            "Eres un sintetizador experto. A continuación recibes respuestas de varios modelos de IA "
            "a la misma pregunta. Produce una respuesta consolidada: indica acuerdos, discrepancias "
            "relevantes y limitaciones. No votes por mayoría como única verdad.\n\n"
            + "\n\n".join(
                f"### Modelo {r['provider_id']} ({r.get('model', '?')}):\n{r['content']}" for r in successful
            )
        )
        synth_result = await call_provider(
            successful[0]["provider_id"],
            [Message(role=MessageRole.USER, content=synthesis_prompt)],
            model=model,
            task_id=task_id,
        )
        if synth_result["status"] == "SUCCEEDED":
            synthesis = synth_result["content"]
            disagreements_from_model = None
        else:
            # Local fallback synthesis (concatenation, explicitly labeled)
            synthesis = (
                "**Síntesis local (el modelo de síntesis falló; se muestran respuestas sin fusionar):**\n\n"
                + "\n\n---\n\n".join(
                    f"**{r['provider_id']}**: {r['content']}" for r in successful
                )
            )

    final_status = TaskStatus.SUCCEEDED if successful else TaskStatus.FAILED
    task.status = final_status
    task.result = synthesis
    task.error = "; ".join(f"{r['provider_id']}: {r['error']}" for r in failed) or None
    db.commit()
    db.close()

    event_bus.publish("task.finished", {"status": final_status.value, "successful": len(successful), "failed": len(failed)}, task_id=task_id, status=final_status.value)

    return {
        "task_id": task_id,
        "status": final_status.value,
        "responses": results,
        "synthesis": synthesis,
        "disagreements": disagreements,
        "limitations": [f"{r['provider_id']}: {r['error']}" for r in failed] + (
            ["Solo un proveedor disponible: la colaboración multi-IA completa no está activa."]
            if len(successful) == 1 else []
        ),
    }
