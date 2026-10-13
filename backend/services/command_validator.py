"""
Command validation layer for the local terminal agent.

Security model:
- Only explicitly allowlisted programs may run.
- Shell metacharacters (&&, ||, ;, |, >, <, ` , $(), backticks) are rejected
  so AI-generated text cannot smuggle chained commands.
- Working directory must resolve inside an authorized project root.
- Sensitive filenames (.env, keys, secrets) can never be targeted by file ops.
"""
import os
import re
import shlex
from typing import List, Optional, Tuple

from config import settings

# Programs considered safe read/build/test tools.
# NOTE: powershell/cmd are NOT allowed — they are escape hatches that could
# bypass every other rule (Remove-Item, Invoke-Expression, chaining, etc.).
ALLOWED_COMMANDS = {
    "git", "python", "python3", "py", "pip", "pip3", "node", "npm", "npx",
    "pnpm", "yarn", "dir", "ls", "echo", "cat", "where", "which", "java",
    "mvn", "gradle", "docker", "code", "pytest", "tsc", "cargo", "go",
}

# Explicitly forbidden even if allowlisted elsewhere.
FORBIDDEN_COMMANDS = {
    "rm", "rmdir", "del", "format", "shutdown", "restart", "reg", "regedit",
    "schtasks", "netsh", "cipher", "mkfs", "diskpart", "taskkill", "Stop-Process",
    "Remove-Item", "Remove-ItemProperty", "Set-ExecutionPolicy", "Invoke-WebRequest",
    "Invoke-Expression", "iex", "curl", "wget", "ssh", "scp", "ftp",
}

_DANGEROUS_PATTERNS = [
    r"&&", r"\|\|", r"[;&|]", r"`", r"\$\(", r">", r"<", r"\n", r"\r",
    r"\.\.[/\\]",  # path traversal
]

_SENSITIVE_NAMES = (".env", "id_rsa", "id_ed25519", ".pem", ".key", "secret", "credentials")


def _has_dangerous_chars(command: str) -> bool:
    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


def is_sensitive_path(path: str) -> bool:
    lowered = path.lower()
    return any(name in lowered for name in _SENSITIVE_NAMES)


def validate_command(command: str) -> Tuple[bool, str, List[str]]:
    """
    Validate a shell command string.

    Returns:
        (ok, message, argv) — argv is the tokenized command when ok.
    """
    if not command or not command.strip():
        return False, "Empty command", []

    if _has_dangerous_chars(command):
        return False, "Command contains forbidden characters (chaining/redirection/traversal)", []

    try:
        argv = shlex.split(command, posix=False)
    except ValueError as e:
        return False, f"Cannot parse command: {e}", []

    if not argv:
        return False, "Empty command after parsing", []

    program = os.path.basename(argv[0]).lower().replace('"', "").replace("'", "")

    if program in FORBIDDEN_COMMANDS:
        return False, f"Command '{program}' is blocked by policy", []

    if program not in ALLOWED_COMMANDS:
        return False, f"Command '{program}' is not in the allowlist", []

    # Block file arguments that point at sensitive files
    for arg in argv[1:]:
        if is_sensitive_path(arg):
            return False, f"Argument references a sensitive file: {arg}", []

    return True, "OK", argv


def resolve_and_check_cwd(cwd: Optional[str]) -> Tuple[bool, str]:
    """
    Ensure the working directory exists and lies inside an authorized root.
    """
    allowed_roots = []
    for root in settings.agent_allowed_directories:
        path = os.path.abspath(root)
        os.makedirs(path, exist_ok=True)
        allowed_roots.append(path)

    target = os.path.abspath(cwd) if cwd else os.path.abspath(allowed_roots[0])

    for root in allowed_roots:
        try:
            if os.path.commonpath([target, root]) == root:
                return True, target
        except ValueError:
            continue
    return False, f"Directory outside authorized roots: {target}"
