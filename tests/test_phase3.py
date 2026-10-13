"""
Tests for keystore (encrypted API key storage) and routing (adaptive learning).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.keystore import mask_key, _fernet
from services.routing import RoutingMetrics


# ── Keystore ──────────────────────────────────────────────────────────────────

def test_mask_key_short():
    assert mask_key("abc") == "****"


def test_mask_key_normal():
    masked = mask_key("sk-1234567890abcdef")
    assert masked.startswith("sk-1")
    assert masked.endswith("cdef")
    assert "1234567890abcdef" not in masked  # full key never shown


def test_fernet_roundtrip():
    f = _fernet()
    token = f.encrypt(b"my-secret-key").decode()
    assert f.decrypt(token.encode()).decode() == "my-secret-key"


def test_fernet_is_deterministic_key():
    # Two Fernet instances derive the same key from the same secret
    f1, f2 = _fernet(), _fernet()
    t = f1.encrypt(b"hello").decode()
    assert f2.decrypt(t.encode()).decode() == "hello"


def test_store_and_get_and_delete():
    from services import keystore
    # Ensure tables exist (tests run without app startup; engine is async)
    from database.base import Base
    from database.session import engine
    import database.models  # register models
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncEngine
    if isinstance(engine, AsyncEngine):
        async def _create():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        asyncio.get_event_loop().run_until_complete(_create())
    else:
        Base.metadata.create_all(bind=engine)
    keystore.store_api_key("testprov", "sk-test-1234567890")
    try:
        assert keystore.get_api_key("testprov") == "sk-test-1234567890"
        stored = keystore.list_stored_keys()
        entry = next(k for k in stored if k["provider_id"] == "testprov")
        assert "sk-test-1234567890" not in entry["masked"]  # masked only
    finally:
        keystore.delete_api_key("testprov")
    assert keystore.get_api_key("testprov") is None


# ── Adaptive routing ──────────────────────────────────────────────────────────

def test_routing_neutral_prior_for_untried():
    rm = RoutingMetrics()
    s = rm.score("newprov", "general")
    assert s["attempts"] == 0
    assert s["score"] == 0.5  # neutral prior
    assert s["confidence"] == 0.0


def test_routing_records_success_and_failure():
    rm = RoutingMetrics()
    rm.record("a", "code", True, 500)
    rm.record("a", "code", True, 700)
    rm.record("a", "code", False, 0, "err")
    s = rm.score("a", "code")
    assert s["attempts"] == 3
    assert s["success_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert s["avg_latency_ms"] == pytest.approx(600.0)


def test_routing_recommends_better_provider():
    rm = RoutingMetrics()
    # provider "good": 10/10 success; provider "bad": 2/10 success
    for _ in range(10):
        rm.record("good", "general", True, 400)
    for i in range(10):
        rm.record("bad", "general", i < 2, 9000)
    rec = rm.recommend("general", ["good", "bad"])
    assert rec["recommended"] == "good"
    assert rec["expected_improvement"] > 0  # better than uniform baseline
    assert rec["ranking"][0]["provider_id"] == "good"


def test_routing_empty_candidates():
    rm = RoutingMetrics()
    rec = rm.recommend("general", [])
    assert rec["recommended"] is None


def test_routing_confidence_ramps():
    rm = RoutingMetrics()
    for _ in range(3):
        rm.record("p", "chat", True, 100)
    assert rm.score("p", "chat")["confidence"] == pytest.approx(0.3)
    for _ in range(7):
        rm.record("p", "chat", True, 100)
    assert rm.score("p", "chat")["confidence"] == 1.0


# ── Orchestrator C plan parsing ───────────────────────────────────────────────

def test_parse_plan_extracts_valid_dag():
    from services.orchestrator_c import _parse_plan, SubtaskKind
    content = '''```json
{"subtasks": [
  {"id": "s1", "kind": "analyze", "title": "Analizar", "prompt": "p1", "depends_on": []},
  {"id": "s2", "kind": "implement", "title": "Implementar", "prompt": "p2", "depends_on": ["s1"]},
  {"id": "s3", "kind": "test", "title": "Probar", "prompt": "p3", "depends_on": ["s1", "s2"]}
]}
```'''
    subtasks = _parse_plan(content, ["google"])
    assert len(subtasks) == 3
    assert subtasks[0].kind == SubtaskKind.ANALYZE
    assert subtasks[1].depends_on == ["s1"]
    assert subtasks[2].depends_on == ["s1", "s2"]


def test_parse_plan_breaks_forward_cycles():
    from services.orchestrator_c import _parse_plan
    # s1 depends on s2 (forward ref) — should be dropped
    content = '''{"subtasks": [
      {"id": "s1", "kind": "analyze", "title": "A", "prompt": "p", "depends_on": ["s2"]},
      {"id": "s2", "kind": "test", "title": "B", "prompt": "p", "depends_on": ["s1"]}
    ]}'''
    subtasks = _parse_plan(content, ["google"])
    # s1 cannot depend on s2 (later); s2 can depend on s1
    assert subtasks[0].depends_on == []
    assert subtasks[1].depends_on == ["s1"]


def test_parse_plan_invalid_json_returns_empty():
    from services.orchestrator_c import _parse_plan
    assert _parse_plan("no json here", ["google"]) == []


def test_parse_plan_unknown_kind_falls_back():
    from services.orchestrator_c import _parse_plan, SubtaskKind
    content = '''{"subtasks": [{"id": "s1", "kind": "dance", "title": "X", "prompt": "p", "depends_on": []}]}'''
    subtasks = _parse_plan(content, ["google"])
    assert subtasks[0].kind == SubtaskKind.ANALYZE


# ── Streaming SSE formatting ──────────────────────────────────────────────────

def test_sse_event_format():
    from services.streaming import _sse
    out = _sse("chunk", {"delta": "hola"})
    assert out.startswith("data: ")
    assert out.endswith("\n\n")
    import json
    payload = json.loads(out[6:].strip())
    assert payload["type"] == "chunk"
    assert payload["delta"] == "hola"


# ── Quota tracking (Copilot-style counter) ────────────────────────────────────

def test_quota_parses_google_429_body():
    from services.quota import reset_for_tests, record_error, snapshot
    reset_for_tests()
    body = (
        "You exceeded your current quota, please check your plan and billing details. "
        "* Quota exceeded for metric: generativelanguage.googleapis.com/"
        "generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash\n"
        "Please retry in 2h10m36.122573403s."
    )
    record_error("gemini-3.8-flash", 429, body)
    rows = {m["model"]: m for m in snapshot()}
    row = rows["gemini-3.8-flash"]
    assert row["known_limit"] == 20
    assert row["available"] is False
    assert row["seconds_until_reset"] is not None and 7000 < row["seconds_until_reset"] <= 7860


def test_quota_counts_served_messages():
    from services.quota import reset_for_tests, record_served, snapshot
    reset_for_tests()
    for _ in range(3):
        record_served("gemini-3-flash-preview")
    rows = {m["model"]: m for m in snapshot()}
    assert rows["gemini-3-flash-preview"]["messages_used"] == 3
    assert rows["gemini-3-flash-preview"]["available"] is True


def test_quota_can_chat_when_alternative_available():
    from services.quota import reset_for_tests, record_error, record_served, snapshot
    reset_for_tests()
    record_error("gemini-3.8-flash", 429, "limit: 20, model: gemini-3.8-flash. Please retry in 1h0m0s.")
    record_served("gemini-3.1-flash-lite")
    rows = snapshot()
    active = [m["model"] for m in rows if m["available"]]
    assert "gemini-3.8-flash" not in active
    assert "gemini-3.1-flash-lite" in active
