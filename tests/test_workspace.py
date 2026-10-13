"""
Tests for workspace file access authorization.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from services import workspace


def test_resolve_inside_root():
    ok, path = workspace.resolve_path("./projects/hello.txt")
    assert ok, path


def test_resolve_outside_root_blocked():
    ok, msg = workspace.resolve_path("C:\\Windows\\System32\\config\\SAM")
    assert not ok


def test_resolve_traversal_blocked():
    ok, msg = workspace.resolve_path("./projects/../../../Windows/System32")
    assert not ok


def test_resolve_sensitive_blocked():
    ok, msg = workspace.resolve_path("./projects/.env")
    assert not ok
    assert "sensitive" in msg.lower()


def test_write_and_read_roundtrip():
    target = os.path.abspath("./projects/_test_roundtrip.txt")
    result = workspace.write_file(target, "contenido de prueba")
    assert result["size"] > 0
    read = workspace.read_file(target)
    assert read["content"] == "contenido de prueba"
    workspace.delete_file(target)


def test_list_roots():
    roots = workspace.list_directory()
    assert "roots" in roots
    assert len(roots["roots"]) >= 1
