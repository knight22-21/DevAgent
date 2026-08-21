"""Shell execution tool with a blocklist for dangerous commands.

Runs commands in a subprocess with a timeout (default 30s).
The blocklist rejects patterns that could cause irreversible damage or
leak credentials even when accidentally triggered.
"""

from __future__ import annotations

import re
import subprocess

from devagent.tools.registry import ToolRegistry

# Commands / patterns that are never allowed
_BLOCKLIST: list[re.Pattern] = [
    re.compile(r"\brm\s+-rf\s+/"),            # rm -rf /
    re.compile(r"\bdd\b.*\bof=/dev/"),         # dd to device
    re.compile(r"\b(shutdown|reboot|halt)\b"), # system control
    re.compile(r"\bmkfs\b"),                   # format disk
    re.compile(r"\bchmod\s+[0-7]*7[0-7]{2}\s+/"),  # world-writable root files
    re.compile(r">\s*/etc/"),                  # overwrite system files
    re.compile(r"\bcurl\b.*\|\s*(ba)?sh"),     # curl | bash
    re.compile(r"\bwget\b.*\|\s*(ba)?sh"),     # wget | bash
    re.compile(r"\bcat\s+.*\.env\b"),          # read .env files
    re.compile(r"\bprintenv\b"),               # dump environment
]


def _is_blocked(command: str) -> str | None:
    """Return the matching pattern string if the command is blocked, else None."""
    for pattern in _BLOCKLIST:
        if pattern.search(command):
            return pattern.pattern
    return None


def register_shell_tool(registry: ToolRegistry, project_root: str = ".") -> None:

    def run_shell(args: dict) -> str:
        command = args.get("command", "").strip()
        timeout = min(int(args.get("timeout", 30)), 120)

        if not command:
            return "[error] No command provided"

        blocked = _is_blocked(command)
        if blocked:
            return f"[blocked] Command matches blocklist pattern: {blocked!r}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=project_root,
            )
            out = result.stdout.strip()
            err = result.stderr.strip()
            parts = []
            if out:
                parts.append(out)
            if err:
                parts.append(f"[stderr]\n{err}")
            if result.returncode != 0:
                parts.append(f"[exit code: {result.returncode}]")
            return "\n".join(parts) if parts else "(no output)"
        except subprocess.TimeoutExpired:
            return f"[error] Command timed out after {timeout}s"
        except Exception as exc:
            return f"[error] {exc}"

    registry.register(
        "run_shell",
        (
            "Execute a shell command in the project directory. "
            "Use for running tests, linters, build commands, package managers, etc. "
            "Dangerous commands (rm -rf /, curl|bash, etc.) are blocked."
        ),
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (max 120)", "default": 30},
            },
            "required": ["command"],
        },
        run_shell,
    )
