"""
Git integration — status, diff, commit inside authorized roots.
Every operation runs `git` with a fixed argv (no shell) and the working
directory is validated against the authorized roots. User-provided paths are
passed after `--` to prevent option injection; messages are single arguments.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.command_validator import resolve_and_check_cwd
from services.process_runner import run_command

router = APIRouter()

MAX_DIFF_KB = 512


class GitFile(BaseModel):
    path: str
    index: str
    worktree: str
    label: str


class GitStatusResponse(BaseModel):
    is_repo: bool
    branch: Optional[str] = None
    files: List[GitFile] = []
    ahead: int = 0
    behind: int = 0
    error: Optional[str] = None


class GitDiffResponse(BaseModel):
    is_repo: bool
    diff: str
    truncated: bool = False
    error: Optional[str] = None


class GitCommitRequest(BaseModel):
    path: Optional[str] = None
    message: str = Field(min_length=1, max_length=4000)
    files: List[str] = Field(default_factory=list)


_STATUS_LABELS = {
    "M": "modificado", "A": "añadido", "D": "eliminado", "R": "renombrado",
    "C": "copiado", "U": "conflicto", "?": "sin seguimiento", "!": "ignorado",
}


async def _git(args: List[str], cwd: str, timeout: int = 30) -> dict:
    return await run_command(["git", *args], cwd=cwd, timeout=timeout)


def _check_repo(cwd: str, status: dict) -> Optional[GitStatusResponse]:
    if status["exit_code"] == 0 and status["stdout"].strip() == "true":
        return None
    return GitStatusResponse(is_repo=False, error="No es un repositorio git")


@router.get("/status", response_model=GitStatusResponse)
async def git_status(path: Optional[str] = None):
    """Branch, tracked/untracked changes and ahead/behind for an authorized dir."""
    ok, cwd = resolve_and_check_cwd(path)
    if not ok:
        raise HTTPException(status_code=403, detail=cwd)

    probe = await _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if probe["exit_code"] != 0 or probe["stdout"].strip() != "true":
        return GitStatusResponse(is_repo=False, error="No es un repositorio git")

    branch = None
    ahead = behind = 0
    br = await _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if br["exit_code"] == 0:
        branch = br["stdout"].strip()
    up = await _git(["rev-list", "--left-right", "--count", "@{upstream}...HEAD"], cwd)
    if up["exit_code"] == 0 and up["stdout"].strip():
        parts = up["stdout"].split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])

    st = await _git(["status", "--porcelain=v1", "-b"], cwd)
    if st["exit_code"] != 0:
        return GitStatusResponse(is_repo=True, branch=branch, error=st["stderr"] or "git status falló")

    files: List[GitFile] = []
    for line in st["stdout"].splitlines():
        if line.startswith("##"):
            continue
        if len(line) < 4:
            continue
        index, worktree, path_ = line[0], line[1], line[3:].strip()
        code = worktree if worktree != " " else index
        label = _STATUS_LABELS.get(code, code)
        files.append(GitFile(path=path_, index=index, worktree=worktree, label=label))

    return GitStatusResponse(is_repo=True, branch=branch, files=files, ahead=ahead, behind=behind)


@router.get("/diff", response_model=GitDiffResponse)
async def git_diff(path: Optional[str] = None, file: Optional[str] = None, staged: bool = False):
    """Unified diff of working tree (or a single file) against HEAD."""
    ok, cwd = resolve_and_check_cwd(path)
    if not ok:
        raise HTTPException(status_code=403, detail=cwd)

    probe = await _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if probe["exit_code"] != 0 or probe["stdout"].strip() != "true":
        return GitDiffResponse(is_repo=False, diff="", error="No es un repositorio git")

    args = ["diff", "--no-color"]
    if staged:
        args.append("--staged")
    if file:
        if file.startswith("-") or ".." in file:
            raise HTTPException(status_code=400, detail="Ruta de archivo inválida")
        args += ["--", file]
    result = await _git(args, cwd, timeout=30)
    if result["exit_code"] != 0:
        return GitDiffResponse(is_repo=True, diff="", error=result["stderr"] or "git diff falló")

    diff = result["stdout"]
    truncated = len(diff) > MAX_DIFF_KB * 1024
    if truncated:
        diff = diff[: MAX_DIFF_KB * 1024] + "\n… (dif truncado)"
    return GitDiffResponse(is_repo=True, diff=diff, truncated=truncated)


class GitCommitResponse(BaseModel):
    ok: bool
    output: str
    error: Optional[str] = None


@router.post("/commit", response_model=GitCommitResponse)
async def git_commit(payload: GitCommitRequest):
    """Stage selected files (or all) and commit with the given message."""
    ok, cwd = resolve_and_check_cwd(payload.path)
    if not ok:
        raise HTTPException(status_code=403, detail=cwd)

    probe = await _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if probe["exit_code"] != 0 or probe["stdout"].strip() != "true":
        raise HTTPException(status_code=400, detail="No es un repositorio git")

    # Reject option-like paths; pass everything after `--`
    for f in payload.files:
        if f.startswith("-") or ".." in f:
            raise HTTPException(status_code=400, detail=f"Ruta inválida: {f}")

    if payload.files:
        add = await _git(["add", "--", *payload.files], cwd)
        if add["exit_code"] != 0:
            raise HTTPException(status_code=400, detail=add["stderr"] or "git add falló")
    else:
        add = await _git(["add", "-A"], cwd)
        if add["exit_code"] != 0:
            raise HTTPException(status_code=400, detail=add["stderr"] or "git add falló")

    commit = await _git(["commit", "-m", payload.message], cwd)
    if commit["exit_code"] != 0:
        output = (commit["stderr"] or commit["stdout"] or "").strip()
        return GitCommitResponse(ok=False, output=output, error="git commit falló (¿sin cambios o identidad sin configurar?)")

    head = await _git(["log", "-1", "--oneline"], cwd)
    return GitCommitResponse(ok=True, output=(head["stdout"] or commit["stdout"]).strip())


class GitInitResponse(BaseModel):
    ok: bool
    output: str
    error: Optional[str] = None


@router.post("/init", response_model=GitInitResponse)
async def git_init(path: Optional[str] = None):
    """Initialize a repository inside an authorized root (explicit user action)."""
    ok, cwd = resolve_and_check_cwd(path)
    if not ok:
        raise HTTPException(status_code=403, detail=cwd)
    probe = await _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if probe["exit_code"] == 0 and probe["stdout"].strip() == "true":
        return GitInitResponse(ok=False, output="", error="Ya es un repositorio git")
    result = await _git(["init"], cwd)
    if result["exit_code"] != 0:
        return GitInitResponse(ok=False, output=result["stdout"], error=result["stderr"] or "git init falló")
    return GitInitResponse(ok=True, output=result["stdout"].strip() or "Repositorio inicializado")
