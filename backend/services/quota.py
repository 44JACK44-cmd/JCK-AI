"""
Free-tier quota tracking (Copilot-style message counter).

Tracks how many messages were served per model in the current window and,
when Google returns a 429 with its official details, parses the exact limit
and the exact reset time so the UI can show "X messages remaining" honestly.
"""
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Sliding window for counting served messages (Google windows we observed: ~2h)
WINDOW_SECONDS = 7200

# model -> timestamps of served (HTTP 200) messages inside the window
_served: Dict[str, List[float]] = defaultdict(list)
# model -> {"limit": int, "resets_at": float (epoch), "retry_after_text": str}
_exhausted: Dict[str, Dict[str, Any]] = {}

# Google 429 body: "limit: 20, model: gemini-3.8-flash"
_LIMIT_RE = re.compile(r"limit:\s*(\d+)[,\s]+model:\s*([A-Za-z0-9._-]+)")
# Google 429 body: "Please retry in 2h10m36.122573403s."
_RETRY_RE = re.compile(r"retry in (\d+)h(\d+)m(\d+(?:\.\d+)?)s", re.IGNORECASE)


def record_served(model: str):
    """Record one successfully served message for a model."""
    now = time.time()
    bucket = _served[model]
    bucket.append(now)
    # Also a known 429 again means still exhausted — nothing to clear here
    ex = _exhausted.get(model)
    if ex and now >= ex.get("resets_at", 0):
        _exhausted.pop(model, None)


def record_error(model: str, status_code: int, body: str = ""):
    """Record a failed call; on 429 parse Google's limit and reset time."""
    if status_code != 429:
        return
    now = time.time()
    entry = _exhausted.setdefault(model, {})

    m = _LIMIT_RE.search(body)
    if m:
        target_model = m.group(2).rstrip(".")
        limit = int(m.group(1))
        _exhausted.setdefault(target_model, {})["limit"] = limit
        if target_model != model:
            entry = _exhausted[target_model]

    r = _RETRY_RE.search(body)
    if r:
        seconds = int(r.group(1)) * 3600 + int(r.group(2)) * 60 + float(r.group(3))
        entry["resets_at"] = now + seconds
        entry["retry_text"] = f"{r.group(1)}h{r.group(2)}m"
    else:
        entry["resets_at"] = now + 300  # unknown: assume 5 min
        entry["retry_text"] = "5m"


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def snapshot() -> List[Dict[str, Any]]:
    """Per-model quota state for the UI (Copilot-style counter)."""
    now = time.time()
    models = sorted(set(list(_served.keys()) + list(_exhausted.keys())))
    rows: List[Dict[str, Any]] = []
    for model in models:
        served = [t for t in _served.get(model, []) if now - t < WINDOW_SECONDS]
        ex = _exhausted.get(model, {})
        resets_at = ex.get("resets_at", 0)
        available = now >= resets_at
        rows.append({
            "model": model,
            "messages_used": len(served),
            "known_limit": ex.get("limit"),
            "available": available,
            "resets_at": _iso(resets_at) if resets_at and not available else None,
            "seconds_until_reset": int(resets_at - now) if resets_at > now else None,
            "retry_text": ex.get("retry_text") if not available else None,
        })
    return rows


def is_exhausted(model: str) -> bool:
    ex = _exhausted.get(model)
    if not ex:
        return False
    if time.time() >= ex.get("resets_at", 0):
        _exhausted.pop(model, None)
        return False
    return True


def reset_for_tests():
    """Clear all state (used by the test suite)."""
    _served.clear()
    _exhausted.clear()
