"""
Tests for command validation security layer.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.command_validator import validate_command, resolve_and_check_cwd, is_sensitive_path


def test_allows_safe_command():
    ok, msg, argv = validate_command("python --version")
    assert ok, msg
    assert argv[0] == "python"


def test_allows_git_status():
    ok, msg, argv = validate_command("git status")
    assert ok, msg
    assert argv[:2] == ["git", "status"]


@pytest.mark.parametrize("cmd", [
    "python --version && rm -rf /",
    "echo hi > /etc/passwd",
    "git status | findstr foo",
    "git log; del /f file",
    "git diff || shutdown /s",
])
def test_blocks_chaining_and_redirection(cmd):
    ok, msg, _ = validate_command(cmd)
    assert not ok, f"Should block: {cmd}"
    assert "forbidden" in msg.lower()


@pytest.mark.parametrize("cmd", [
    "rm -rf /",
    "del /f /s C:\\",
    "curl http://evil.example",
    "powershell Remove-Item C:\\important",
    "malicious-binary --x",
])
def test_blocks_non_allowed_or_forbidden(cmd):
    ok, msg, _ = validate_command(cmd)
    assert not ok, f"Should block: {cmd}"


def test_blocks_path_traversal_argument():
    ok, msg, _ = validate_command("python ../../escape.py")
    assert not ok


def test_blocks_sensitive_file_argument():
    ok, msg, _ = validate_command("cat .env")
    assert not ok
    assert "sensitive" in msg.lower()


def test_empty_command_rejected():
    ok, _, _ = validate_command("   ")
    assert not ok


def test_sensitive_path_detection():
    assert is_sensitive_path(".env")
    assert is_sensitive_path("secrets/id_rsa")
    assert is_sensitive_path("config.pem")
    assert not is_sensitive_path("main.py")


def test_cwd_inside_authorized_root():
    ok, path = resolve_and_check_cwd("./projects")
    assert ok, path
    assert os.path.isabs(path)


def test_cwd_outside_authorized_root():
    ok, msg = resolve_and_check_cwd("C:\\Windows\\System32")
    assert not ok
