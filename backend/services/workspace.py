"""
Filesystem service for the authorized project workspace.
All paths are constrained to configured authorized roots.
"""
import os
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from services.command_validator import is_sensitive_path

MAX_READ_BYTES = settings.agent_max_file_size_mb * 1024 * 1024
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".idea", ".vscode"}


def _authorized_roots() -> List[str]:
    roots = []
    for root in settings.agent_allowed_directories:
        path = os.path.abspath(root)
        os.makedirs(path, exist_ok=True)
        roots.append(path)
    return roots


def resolve_path(path: str) -> Tuple[bool, str]:
    """Resolve and authorize a path. Returns (ok, absolute_path_or_error)."""
    if is_sensitive_path(path):
        return False, f"Sensitive file blocked: {path}"
    target = os.path.abspath(path)
    for root in _authorized_roots():
        try:
            if os.path.commonpath([target, root]) == root:
                return True, target
        except ValueError:
            continue
    return False, f"Path outside authorized roots: {target}"


def list_directory(path: Optional[str] = None) -> Dict[str, Any]:
    if path is None:
        return {
            "roots": [
                {"path": root, "exists": os.path.isdir(root)}
                for root in _authorized_roots()
            ]
        }
    ok, target = resolve_path(path)
    if not ok:
        raise PermissionError(target)
    if not os.path.isdir(target):
        raise FileNotFoundError(f"Not a directory: {target}")

    entries = []
    with os.scandir(target) as it:
        for entry in it:
            if entry.name in IGNORE_DIRS:
                continue
            try:
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "path": entry.path,
                    "is_dir": entry.is_dir(),
                    "size": stat.st_size if entry.is_file() else None,
                    "modified": stat.st_mtime,
                })
            except OSError:
                continue
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return {"path": target, "entries": entries}


def read_file(path: str) -> Dict[str, Any]:
    ok, target = resolve_path(path)
    if not ok:
        raise PermissionError(target)
    if not os.path.isfile(target):
        raise FileNotFoundError(f"Not a file: {target}")
    size = os.path.getsize(target)
    if size > MAX_READ_BYTES:
        raise ValueError(f"File too large ({size} bytes > {MAX_READ_BYTES})")
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return {"path": target, "size": size, "content": content}


def write_file(path: str, content: str, create_dirs: bool = True) -> Dict[str, Any]:
    ok, target = resolve_path(path)
    if not ok:
        raise PermissionError(target)
    data = content.encode("utf-8")
    if len(data) > MAX_READ_BYTES:
        raise ValueError("Content too large")
    if create_dirs:
        os.makedirs(os.path.dirname(target), exist_ok=True)
    existed = os.path.isfile(target)
    old_content = None
    if existed:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            old_content = f.read()
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return {
        "path": target,
        "created": not existed,
        "size": len(data),
        "previous_content": old_content if existed else None,
    }


def delete_file(path: str) -> Dict[str, Any]:
    ok, target = resolve_path(path)
    if not ok:
        raise PermissionError(target)
    if not os.path.isfile(target):
        raise FileNotFoundError(f"Not a file: {target}")
    os.remove(target)
    return {"path": target, "deleted": True}


def search(query: str, root: Optional[str] = None, max_results: int = 100) -> List[Dict[str, Any]]:
    roots = [root] if root else _authorized_roots()
    results: List[Dict[str, Any]] = []
    q = query.lower()
    for base in roots:
        ok, base_path = resolve_path(base) if root else (True, base)
        if not ok:
            continue
        for dirpath, dirnames, filenames in os.walk(base_path):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            for name in filenames:
                if is_sensitive_path(name):
                    continue
                full = os.path.join(dirpath, name)
                if q in name.lower():
                    results.append({"path": full, "name": name, "match": "name"})
                else:
                    try:
                        if os.path.getsize(full) > 256 * 1024:
                            continue
                        with open(full, "r", encoding="utf-8", errors="ignore") as f:
                            for i, line in enumerate(f, 1):
                                if q in line.lower():
                                    results.append({"path": full, "name": name, "match": "content", "line": i, "preview": line.strip()[:200]})
                                    break
                    except OSError:
                        continue
                if len(results) >= max_results:
                    return results
    return results
