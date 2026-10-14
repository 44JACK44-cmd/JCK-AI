"""
Agent endpoints — autonomous loop (plan → act → observe) with SSE streaming.
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.agent_loop import DEFAULT_MAX_STEPS, run_agent

router = APIRouter()


class AgentRunRequest(BaseModel):
    objective: str = Field(min_length=5, max_length=8000)
    provider_id: Optional[str] = None
    cwd: Optional[str] = None
    max_steps: int = Field(default=DEFAULT_MAX_STEPS, ge=1, le=16)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/run")
async def run_autonomous_agent(request: AgentRunRequest):
    """Run the autonomous agent loop; streams SSE events in real time."""

    async def event_stream():
        try:
            async for event in run_agent(
                objective=request.objective,
                provider_id=request.provider_id,
                cwd=request.cwd,
                max_steps=request.max_steps,
            ):
                yield _sse(event)
        except asyncio.CancelledError:
            yield _sse({"event": "error", "detail": "Cancelled"})
            raise
        except Exception as e:  # pragma: no cover — defensive
            yield _sse({"event": "error", "detail": str(e)})
        yield _sse({"event": "end"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
