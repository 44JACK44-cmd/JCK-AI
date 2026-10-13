"""
Adaptive routing (Level 2 of progressive learning).

Records per-provider/per-task-class performance metrics and recommends the
best provider for a given task class based on observable evidence:
success rate, latency, and error frequency. Compares against a baseline
(uniform random) to demonstrate measurable improvement.
"""
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import MemoryEntry
from database.session import SessionLocal


class RoutingMetrics:
    """In-memory + persistent metrics store for adaptive routing."""

    def __init__(self):
        # (provider_id, task_class) -> counters
        self._counters: Dict[tuple, Dict[str, float]] = defaultdict(
            lambda: {"attempts": 0, "successes": 0, "total_latency_ms": 0.0, "errors": 0}
        )
        # Baseline: uniform distribution (for improvement comparison)
        self._baseline_total = 0
        self._hydrated = False

    def _ensure_hydrated(self):
        """Rebuild counters from persisted experience memory (survives restarts)."""
        if self._hydrated:
            return
        self._hydrated = True
        try:
            db = SessionLocal()
            try:
                rows = (
                    db.query(MemoryEntry)
                    .filter(MemoryEntry.evidence.isnot(None))
                    .order_by(MemoryEntry.id)
                    .all()
                )
                for row in rows:
                    ev = row.evidence or {}
                    pid, tc = ev.get("provider_id"), ev.get("task_class")
                    if not pid or not tc:
                        continue
                    c = self._counters[(pid, tc)]
                    c["attempts"] += 1
                    self._baseline_total += 1
                    if row.outcome == "ok":
                        c["successes"] += 1
                        c["total_latency_ms"] += float(ev.get("latency_ms") or 0)
                    else:
                        c["errors"] += 1
            finally:
                db.close()
        except Exception:
            pass  # hydration must never block routing

    def record(
        self,
        provider_id: str,
        task_class: str,
        success: bool,
        latency_ms: int = 0,
        error: Optional[str] = None,
    ):
        self._ensure_hydrated()
        key = (provider_id, task_class)
        c = self._counters[key]
        c["attempts"] += 1
        self._baseline_total += 1
        if success:
            c["successes"] += 1
            c["total_latency_ms"] += latency_ms
        else:
            c["errors"] += 1

    def score(self, provider_id: str, task_class: str) -> Dict[str, Any]:
        self._ensure_hydrated()
        c = self._counters.get((provider_id, task_class), {"attempts": 0, "successes": 0, "total_latency_ms": 0, "errors": 0})
        attempts = c["attempts"]
        if attempts == 0:
            return {
                "provider_id": provider_id,
                "task_class": task_class,
                "attempts": 0,
                "success_rate": None,
                "avg_latency_ms": None,
                "score": 0.5,  # neutral prior for untried providers
                "confidence": 0.0,
            }
        success_rate = c["successes"] / attempts
        avg_latency = c["total_latency_ms"] / max(c["successes"], 1)
        # Composite score: 0.7 * success_rate + 0.3 * latency_norm (lower is better)
        latency_norm = max(0.0, 1.0 - (avg_latency / 10000.0))  # 10s → 0
        composite = 0.7 * success_rate + 0.3 * latency_norm
        confidence = min(1.0, attempts / 10.0)  # ramps to 1.0 after 10 samples
        return {
            "provider_id": provider_id,
            "task_class": task_class,
            "attempts": attempts,
            "success_rate": round(success_rate, 4),
            "avg_latency_ms": round(avg_latency, 1),
            "score": round(composite, 4),
            "confidence": round(confidence, 4),
        }

    def recommend(self, task_class: str, candidates: List[str]) -> Dict[str, Any]:
        """Rank candidates for a task class; compare to uniform baseline."""
        self._ensure_hydrated()
        if not candidates:
            return {"recommended": None, "ranking": [], "baseline_success_rate": None, "expected_improvement": None}

        scores = [self.score(p, task_class) for p in candidates]
        scores.sort(key=lambda s: s["score"], reverse=True)
        recommended = scores[0]["provider_id"]

        # Baseline: average success rate across candidates (uniform random choice)
        attempted = [s for s in scores if s["attempts"] > 0]
        baseline = sum(s["success_rate"] for s in attempted) / len(attempted) if attempted else None
        rec = scores[0]
        improvement = None
        if baseline is not None and rec["success_rate"] is not None:
            improvement = round(rec["success_rate"] - baseline, 4)

        return {
            "task_class": task_class,
            "recommended": recommended,
            "ranking": scores,
            "baseline_success_rate": round(baseline, 4) if baseline is not None else None,
            "expected_improvement": improvement,
            "total_observations": self._baseline_total,
        }

    def snapshot(self) -> Dict[str, Any]:
        """All recorded metrics with scores and recommendations (learning dashboard)."""
        self._ensure_hydrated()
        classes = sorted({tc for (_, tc) in self._counters.keys()})
        scores = [self.score(p, tc) for (p, tc) in sorted(self._counters.keys())]
        recommendations = {
            tc: self.recommend(tc, sorted({p for (p, c) in self._counters.keys() if c == tc}))
            for tc in classes
        }
        return {
            "counters": {
                f"{p}|{tc}": dict(c) for (p, tc), c in self._counters.items()
            },
            "scores": scores,
            "recommendations": recommendations,
            "task_classes": classes,
            "total_observations": self._baseline_total,
        }


# Global instance
routing_metrics = RoutingMetrics()


def record_outcome(provider_id: str, task_class: str, success: bool, latency_ms: int = 0, error: Optional[str] = None):
    """Record an observed provider outcome for adaptive routing."""
    routing_metrics.record(provider_id, task_class, success, latency_ms, error)


async def persist_outcome(
    provider_id: str,
    task_class: str,
    success: bool,
    latency_ms: int,
    objective: str,
    error: Optional[str] = None,
):
    """Persist the outcome to the experience memory (Level 1) and metrics (Level 2)."""
    record_outcome(provider_id, task_class, success, latency_ms, error)
    try:
        from config import settings
        db = SessionLocal()
        entry = MemoryEntry(
            task_id=None,
            objective=objective[:500],
            outcome=("ok" if success else "failed"),
            evaluation=("positive" if success else "negative"),
            evidence={
                "provider_id": provider_id,
                "task_class": task_class,
                "latency_ms": latency_ms,
                "error": error,
            },
            tools_used=[],
            models_used=[provider_id],
            errors=[error] if error else [],
            system_version=settings.app_version,
        )
        db.add(entry)
        db.commit()
        db.close()
    except Exception:
        pass  # memory persistence must never block routing
