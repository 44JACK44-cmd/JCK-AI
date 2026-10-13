"""
Streaming service for real-time chat responses via SSE.
Works with any registered adapter; falls back to buffered chunks when
the provider does not support native streaming.
"""
import asyncio
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from adapters.base import AIProvider, Message, MessageRole, ProviderError
from api.endpoints.providers import _provider_adapters
from services.orchestrator import _free_mode_allows


async def stream_chat(
    provider_id: str,
    messages: List[Message],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    conversation_id: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """
    Yield SSE-formatted events for a chat completion.
    Event types: start, chunk, done, error.
    When conversation_id is given, the user message is stored at the start and
    the assistant reply at the end, so the conversation history survives.
    """
    adapter: Optional[AIProvider] = _provider_adapters.get(provider_id)
    if adapter is None:
        yield _sse("error", {"message": f"Proveedor '{provider_id}' no registrado"})
        return
    if not _free_mode_allows(provider_id):
        yield _sse("error", {"message": "Bloqueado por la política FREE MODE"})
        return

    # Persist the user turn BEFORE streaming (survives connection errors)
    if conversation_id is not None and messages and messages[-1].role == MessageRole.USER:
        _persist_message(conversation_id, "user", messages[-1].content)

    started = time.monotonic()
    yield _sse("start", {"provider_id": provider_id, "model": model})

    full_content: List[str] = []
    usage: Dict[str, int] = {}
    finish_reason: Optional[str] = None
    used_model: Optional[str] = model

    try:
        # Prefer native streaming when the adapter exposes a stream generator
        stream_fn = getattr(adapter, "chat_completion_stream", None)
        native_stream = getattr(adapter, "supports_native_stream", False)

        if native_stream and stream_fn is not None:
            async for chunk in stream_fn(
                messages, model=model, temperature=temperature, max_tokens=max_tokens
            ):
                if isinstance(chunk, dict):
                    delta = chunk.get("delta", "")
                    finish_reason = chunk.get("finish_reason") or finish_reason
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    if chunk.get("model"):
                        used_model = chunk["model"]
                else:
                    delta = str(chunk)
                if delta:
                    full_content.append(delta)
                    yield _sse("chunk", {"delta": delta})
        else:
            # Buffered fallback: single completion split into pseudo-chunks
            response = await adapter.chat_completion(
                messages, model=model, temperature=temperature,
                max_tokens=max_tokens, stream=False,
            )
            content = response.content or ""
            usage = response.usage or {}
            finish_reason = response.finish_reason
            used_model = response.model or used_model
            # Split into ~40-char chunks for progressive UI rendering
            step = 40
            for i in range(0, len(content), step):
                full_content.append(content[i:i + step])
                yield _sse("chunk", {"delta": content[i:i + step]})
                await asyncio.sleep(0.01)  # allow client render between chunks

        latency_ms = int((time.monotonic() - started) * 1000)
        final_content = "".join(full_content)
        if conversation_id is not None and final_content:
            _persist_message(
                conversation_id, "assistant", final_content,
                provider_id=provider_id, model=used_model,
                metadata={"latency_ms": latency_ms, "usage": usage},
            )
        yield _sse("done", {
            "provider_id": provider_id,
            "model": used_model,
            "content": final_content,
            "usage": usage,
            "finish_reason": finish_reason,
            "latency_ms": latency_ms,
        })

    except ProviderError as e:
        yield _sse("error", {"message": e.message, "status_code": e.status_code})
    except Exception as e:
        yield _sse("error", {"message": str(e)})


def _persist_message(
    conversation_id: int,
    role: str,
    content: str,
    provider_id: Optional[str] = None,
    model: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort persistence of a chat turn (never breaks the stream)."""
    try:
        from database.models import Conversation, Message as MessageRow
        from database.session import SessionLocal
        db = SessionLocal()
        try:
            conv = db.get(Conversation, conversation_id)
            if not conv:
                return
            row = MessageRow(
                conversation_id=conversation_id,
                role=role,
                content=content,
                provider_id=provider_id,
                model=model,
                metadata_json=metadata,
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception:
        pass  # persistence must never break streaming


def _sse(event_type: str, data: Dict[str, Any]) -> str:
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
