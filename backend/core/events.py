"""
In-process event bus powering the real-time Brain (SSE).
Events are broadcast to all connected subscribers.
"""
import asyncio
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional


class BrainEventBus:
    """Async pub/sub event bus with bounded history for task/agent events."""

    def __init__(self, history_size: int = 500):
        self._subscribers: List[asyncio.Queue] = []
        self._history: List[Dict[str, Any]] = []
        self._history_size = history_size

    def publish(self, event_type: str, data: Optional[Dict[str, Any]] = None,
                task_id: Optional[Any] = None, status: Optional[str] = None) -> Dict[str, Any]:
        event = {
            "id": f"evt_{int(time.time() * 1000)}_{len(self._history)}",
            "type": event_type,
            "task_id": task_id,
            "status": status,
            "timestamp": time.time(),
            "data": data or {},
        }
        self._history.append(event)
        if len(self._history) > self._history_size:
            self._history.pop(0)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    def history(self, limit: int = 100, task_id: Optional[Any] = None) -> List[Dict[str, Any]]:
        events = self._history
        if task_id is not None:
            events = [e for e in events if e.get("task_id") == task_id]
        return events[-limit:]

    async def subscribe(self) -> AsyncGenerator[Dict[str, Any], None]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscribers.remove(queue)

    async def stream(self, limit: int = 50, task_id: Optional[Any] = None) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted strings: history first, then live events."""
        for event in self.history(limit=limit, task_id=task_id):
            yield f"data: {json.dumps(event, default=str)}\n\n"
        async for event in self.subscribe():
            if task_id is not None and event.get("task_id") != task_id:
                continue
            yield f"data: {json.dumps(event, default=str)}\n\n"


# Global bus instance
event_bus = BrainEventBus()
