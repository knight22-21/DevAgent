"""Permission manager — tool call allow/deny gate (Phase 10).

Rules are evaluated in order; first match wins:
  --allow write_file           → allow all write_file calls
  --allow write_file:src/**    → allow write_file to paths matching src/**
  --deny  run_shell            → deny all run_shell calls
  --deny  "run_shell:rm *"     → deny run_shell whose command matches 'rm *'

Default when no rule matches:
  - interactive=True  → emit ApprovalNeededEvent; agent loop blocks until
    the user responds via CLI prompt or HTTP POST /api/v1/sessions/{id}/approve
  - interactive=False → allow (same behaviour as pre-Phase 10)
"""

from __future__ import annotations

import fnmatch
import threading
from dataclasses import dataclass
from typing import Literal

Action = Literal["allow", "deny", "ask"]


@dataclass
class PermissionRule:
    action: Action
    tool: str     # tool name, or "*" for any tool
    pattern: str = "*"   # glob matched against the primary arg (path / command)


def parse_rule(spec: str, action: Action) -> PermissionRule:
    """Parse 'write_file' or 'write_file:src/**' into a PermissionRule."""
    if ":" in spec:
        tool, pattern = spec.split(":", 1)
    else:
        tool, pattern = spec, "*"
    return PermissionRule(action=action, tool=tool.strip(), pattern=pattern.strip())


def _primary_arg(tool_name: str, args: dict) -> str:
    """Extract the matchable argument from a tool call."""
    if tool_name in ("write_file", "edit_file"):
        return args.get("path", args.get("file_path", ""))
    if tool_name == "run_shell":
        return args.get("command", "")
    for key in ("path", "command", "query", "url"):
        if key in args:
            return str(args[key])
    return ""


class PermissionManager:
    """Thread-safe allow/deny gate with pause-for-approval support.

    The agent loop calls check() before each tool execution. If it returns
    "ask", the loop yields ApprovalNeededEvent, calls request_approval(), and
    then wait_for_decision(). The CLI or HTTP handler calls resolve() from
    another context (same thread after yield, or a different thread for HTTP),
    which unblocks wait_for_decision().
    """

    def __init__(
        self,
        rules: list[PermissionRule] | None = None,
        *,
        interactive: bool = True,
    ) -> None:
        self._rules: list[PermissionRule] = rules or []
        self._interactive = interactive
        self._pending: dict[str, threading.Event] = {}
        self._decisions: dict[str, bool] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def check(self, tool_name: str, args: dict) -> Action:
        """Return 'allow', 'deny', or 'ask' for the given tool call."""
        primary = _primary_arg(tool_name, args)
        for rule in self._rules:
            if rule.tool not in ("*", tool_name):
                continue
            if fnmatch.fnmatch(primary, rule.pattern):
                return rule.action
        return "ask" if self._interactive else "allow"

    # ------------------------------------------------------------------
    # Approval flow
    # ------------------------------------------------------------------

    def request_approval(self, call_id: str) -> None:
        """Register a pending approval slot before yielding the event."""
        with self._lock:
            self._pending[call_id] = threading.Event()

    def wait_for_decision(self, call_id: str, timeout: float = 300.0) -> bool:
        """Block until resolved by resolve(). Returns True if approved."""
        with self._lock:
            ev = self._pending.get(call_id)
        if ev is None:
            return False
        ev.wait(timeout=timeout)
        with self._lock:
            self._pending.pop(call_id, None)
            return self._decisions.pop(call_id, False)

    def resolve(self, call_id: str, approved: bool) -> None:
        """Called by CLI prompt or HTTP /approve to unblock wait_for_decision."""
        with self._lock:
            self._decisions[call_id] = approved
            ev = self._pending.get(call_id)
        if ev:
            ev.set()

    def has_pending(self, call_id: str) -> bool:
        with self._lock:
            return call_id in self._pending

    @property
    def rules(self) -> list[PermissionRule]:
        return list(self._rules)


# ---------------------------------------------------------------------------
# Session registry — lets the HTTP /approve endpoint reach the right manager
# ---------------------------------------------------------------------------

_registry: dict[str, PermissionManager] = {}
_registry_lock = threading.Lock()


def register(session_id: str, mgr: PermissionManager) -> None:
    with _registry_lock:
        _registry[session_id] = mgr


def get(session_id: str) -> PermissionManager | None:
    with _registry_lock:
        return _registry.get(session_id)


def unregister(session_id: str) -> None:
    with _registry_lock:
        _registry.pop(session_id, None)
