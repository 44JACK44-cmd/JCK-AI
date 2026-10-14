"""
Tests for Phase 5: web tools (SSRF, parsing), BM25 memory, agent JSON loop, scheduler model.
No live network calls — parsing/validation only. E2E live checks are done manually against the server.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ── Web tools: SSRF + parsing ────────────────────────────────────────────────

from services.web_tools import (
    ToolError,
    _decode_ddg_redirect,
    _is_public_host,
    _strip_html_to_text,
    _validate_url,
)


def test_ssrf_blocks_localhost():
    with pytest.raises(ToolError):
        _validate_url("http://localhost:8000/health")


def test_ssrf_blocks_loopback_ip():
    with pytest.raises(ToolError):
        _validate_url("http://127.0.0.1:8000/health")


def test_ssrf_blocks_link_local_metadata():
    with pytest.raises(ToolError):
        _validate_url("http://169.254.169.254/latest/meta-data/")


def test_ssrf_blocks_file_scheme():
    with pytest.raises(ToolError):
        _validate_url("file:///C:/Windows/System32/config/SAM")


def test_ssrf_blocks_private_range():
    with pytest.raises(ToolError):
        _validate_url("http://192.168.1.1/admin")


def test_ssrf_allows_public_hostname_syntax():
    # Only validates scheme + hostname presence + private-IP check.
    # example.com resolves publicly; if DNS fails in sandbox the helper returns False → ToolError.
    try:
        url = _validate_url("https://example.com/page")
        assert url.startswith("https://")
    except ToolError:
        pytest.skip("DNS unavailable in test environment")


def test_strip_html_basic():
    html = "<html><head><script>var x=1;</script></head><body><h1>Title</h1><p>Hello &amp; world</p></body></html>"
    text = _strip_html_to_text(html)
    assert "Title" in text
    assert "Hello & world" in text
    assert "var x" not in text
    assert "<" not in text


def test_ddg_redirect_decode():
    href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Ffastapi.tiangolo.com%2F&rut=abc"
    assert _decode_ddg_redirect(href) == "https://fastapi.tiangolo.com/"


# ── BM25 semantic memory ────────────────────────────────────────────────────

from services.semantics import BM25Index, tokenize


def test_tokenize_basic():
    tokens = tokenize("Configurar Gemini API key para chat")
    assert "gemini" in tokens
    assert "api" in tokens
    assert "para" not in tokens  # stopword


def test_bm25_ranks_relevant_doc_first():
    index = BM25Index()
    index.build([
        {"id": 1, "text": "Compilar APK Android con gradlew assembleDebug"},
        {"id": 2, "text": "Configurar Gemini API key en AI Studio"},
        {"id": 3, "text": "Limpiar disco C liberar espacio temporales"},
    ])
    hits = index.search("gemini api key", top_k=2)
    assert hits, "should return at least one hit"
    assert hits[0]["id"] == 2
    assert hits[0]["score"] > 0


def test_bm25_no_match_returns_empty():
    index = BM25Index()
    index.build([{"id": 1, "text": "solo habla de cocina y recetas"}])
    assert index.search("quantum blockchain", top_k=5) == []


def test_bm25_empty_index():
    index = BM25Index()
    assert index.search("anything") == []


# ── Agent loop: JSON action extraction ──────────────────────────────────────

from services.agent_loop import _extract_json


def test_extract_json_plain():
    obj = _extract_json('{"thought":"ok","action":"list_dir","params":{"path":"."}}')
    assert obj["action"] == "list_dir"
    assert obj["params"]["path"] == "."


def test_extract_json_code_fence():
    raw = '```json\n{"thought":"x","action":"final","params":{"answer":"done"}}\n```'
    obj = _extract_json(raw)
    assert obj["action"] == "final"
    assert obj["params"]["answer"] == "done"


def test_extract_json_with_surrounding_text():
    raw = 'Voy a crear el archivo. {"thought":"t","action":"write_file","params":{"path":"a.txt","content":"hola"}} Espero.'
    obj = _extract_json(raw)
    assert obj["action"] == "write_file"


def test_extract_json_invalid_returns_none():
    assert _extract_json("no json here") is None
    assert _extract_json("") is None
    assert _extract_json("{broken") is None


# ── Scheduler model sanity ──────────────────────────────────────────────────

def test_scheduler_tick_no_tasks_is_safe():
    import asyncio
    from services.scheduler import tick
    runs = asyncio.get_event_loop().run_until_complete(tick())
    assert isinstance(runs, list)
