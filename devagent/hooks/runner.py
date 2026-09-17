"""HookRunner — executes hooks defined in .devagent/hooks.toml.

Exit codes from command hooks:
  0  — allow (proceed normally)
  2  — block (return error to the agent; stderr is the reason)
  Other — allow (treated as success)

Input rewrite: if exit code 0 and stdout is valid JSON with an "updatedInput" key,
the tool arguments are replaced with updatedInput before execution.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devagent.hooks.config import HookDef, load_hooks


@dataclass
class HookResult:
    allowed: bool
    rewritten_args: dict | None = None   # non-None on pre_tool_use if args were rewritten
    feedback: str = ""


class HookRunner:
    """Loads hooks from hooks.toml and fires them on tool events."""

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
        self._hooks: list[HookDef] = load_hooks(project_root)

    def reload(self) -> None:
        """Reload hooks from disk (useful after editing hooks.toml)."""
        self._hooks = load_hooks(self._project_root)

    @property
    def hooks(self) -> list[HookDef]:
        return list(self._hooks)

    def pre_tool_use(self, tool_name: str, args: dict[str, Any]) -> HookResult:
        return self._fire("pre_tool_use", tool_name, args)

    def post_tool_use(self, tool_name: str, args: dict[str, Any], result: str = "") -> None:
        self._fire("post_tool_use", tool_name, args, result=result)

    def session_start(self, session_id: str = "") -> None:
        self._fire_lifecycle("session_start", {"session_id": session_id})

    def session_end(self, session_id: str = "") -> None:
        self._fire_lifecycle("session_end", {"session_id": session_id})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire_lifecycle(self, event: str, extra: dict) -> None:
        env = {**os.environ, **{k.upper(): str(v) for k, v in extra.items()}}
        for hook in self._hooks:
            if hook.event == event and hook.type == "command" and hook.command:
                try:
                    subprocess.run(
                        hook.command, shell=True, env=env,
                        capture_output=True, text=True, timeout=30,
                    )
                except Exception:
                    pass

    def _fire(self, event: str, tool_name: str, args: dict, result: str = "") -> HookResult:
        matching = [h for h in self._hooks if h.matches(event, tool_name)]
        if not matching:
            return HookResult(allowed=True)

        env = {
            **os.environ,
            "DEVAGENT_TOOL_NAME": tool_name,
            "DEVAGENT_TOOL_INPUT": json.dumps(args),
            "DEVAGENT_TOOL_RESULT": result,
            "DEVAGENT_EVENT": event,
        }

        current_args = dict(args)
        for hook in matching:
            hr = self._dispatch(hook, current_args, env)
            if not hr.allowed:
                return hr
            if hr.rewritten_args is not None:
                current_args = hr.rewritten_args
                env["DEVAGENT_TOOL_INPUT"] = json.dumps(current_args)

        rewritten = current_args if (event == "pre_tool_use" and current_args != args) else None
        return HookResult(allowed=True, rewritten_args=rewritten)

    def _dispatch(self, hook: HookDef, args: dict, env: dict) -> HookResult:
        if hook.type == "command" and hook.command:
            return self._run_command(hook.command, args, env)
        if hook.type == "http" and hook.url:
            return self._call_http(hook.url, args)
        return HookResult(allowed=True)

    def _run_command(self, cmd: str, args: dict, env: dict) -> HookResult:
        try:
            proc = subprocess.run(
                cmd, shell=True, env=env,
                capture_output=True, text=True, timeout=30,
            )
        except Exception as exc:
            return HookResult(allowed=True, feedback=f"hook error: {exc}")

        if proc.returncode == 2:
            reason = proc.stderr.strip() or "blocked by hook"
            return HookResult(allowed=False, feedback=reason)

        if proc.stdout.strip():
            try:
                out = json.loads(proc.stdout.strip())
                if isinstance(out, dict) and "updatedInput" in out:
                    return HookResult(allowed=True, rewritten_args=out["updatedInput"])
            except (json.JSONDecodeError, ValueError):
                pass

        return HookResult(allowed=True)

    def _call_http(self, url: str, args: dict) -> HookResult:
        try:
            import httpx
            resp = httpx.post(url, json={"args": args}, timeout=10)
            data = resp.json()
            if not data.get("ok", True):
                return HookResult(allowed=False, feedback=data.get("reason", "blocked by http hook"))
            if "updatedInput" in data:
                return HookResult(allowed=True, rewritten_args=data["updatedInput"])
        except Exception as exc:
            return HookResult(allowed=True, feedback=f"hook http error: {exc}")
        return HookResult(allowed=True)
