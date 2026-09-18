"""Tests for the Phase 10 permission gate (devagent/agent/permissions.py)."""

from __future__ import annotations

import threading
import time

from devagent.agent.permissions import (
    PermissionManager,
    PermissionRule,
    _primary_arg,
    get,
    parse_rule,
    register,
    unregister,
)

# ---------------------------------------------------------------------------
# parse_rule
# ---------------------------------------------------------------------------

def test_parse_rule_simple_allow():
    rule = parse_rule("write_file", "allow")
    assert rule.tool == "write_file"
    assert rule.pattern == "*"
    assert rule.action == "allow"


def test_parse_rule_simple_deny():
    rule = parse_rule("run_shell", "deny")
    assert rule.tool == "run_shell"
    assert rule.pattern == "*"
    assert rule.action == "deny"


def test_parse_rule_with_pattern():
    rule = parse_rule("write_file:src/**", "allow")
    assert rule.tool == "write_file"
    assert rule.pattern == "src/**"
    assert rule.action == "allow"


def test_parse_rule_with_shell_pattern():
    rule = parse_rule("run_shell:git *", "allow")
    assert rule.tool == "run_shell"
    assert rule.pattern == "git *"


def test_parse_rule_strips_whitespace():
    rule = parse_rule("  write_file : src/** ", "allow")
    assert rule.tool == "write_file"
    assert rule.pattern == "src/**"


# ---------------------------------------------------------------------------
# _primary_arg
# ---------------------------------------------------------------------------

def test_primary_arg_write_file():
    assert _primary_arg("write_file", {"path": "src/main.py", "content": "x"}) == "src/main.py"


def test_primary_arg_edit_file():
    assert _primary_arg("edit_file", {"file_path": "tests/test_foo.py"}) == "tests/test_foo.py"


def test_primary_arg_run_shell():
    assert _primary_arg("run_shell", {"command": "git status"}) == "git status"


def test_primary_arg_unknown_tool_path_key():
    assert _primary_arg("read_file", {"path": "README.md"}) == "README.md"


def test_primary_arg_unknown_tool_no_key():
    assert _primary_arg("unknown_tool", {"data": "x"}) == ""


# ---------------------------------------------------------------------------
# PermissionManager.check — explicit rules
# ---------------------------------------------------------------------------

def test_check_allow_rule_matches():
    mgr = PermissionManager(rules=[parse_rule("write_file", "allow")], interactive=False)
    assert mgr.check("write_file", {"path": "any/file.py"}) == "allow"


def test_check_deny_rule_matches():
    mgr = PermissionManager(rules=[parse_rule("run_shell", "deny")], interactive=False)
    assert mgr.check("run_shell", {"command": "ls -la"}) == "deny"


def test_check_pattern_glob_allow():
    # allow src/**, deny everything else for write_file
    mgr = PermissionManager(
        rules=[
            parse_rule("write_file:src/**", "allow"),
            parse_rule("write_file", "deny"),   # catch-all deny after the allow pattern
        ],
        interactive=False,
    )
    assert mgr.check("write_file", {"path": "src/utils/helper.py"}) == "allow"
    assert mgr.check("write_file", {"path": "tests/test_foo.py"}) == "deny"


def test_check_pattern_glob_deny():
    mgr = PermissionManager(
        rules=[parse_rule("run_shell:rm *", "deny")], interactive=False
    )
    assert mgr.check("run_shell", {"command": "rm -rf /"}) == "deny"
    assert mgr.check("run_shell", {"command": "git status"}) != "deny"


def test_check_wildcard_tool_rule():
    mgr = PermissionManager(rules=[PermissionRule(action="deny", tool="*")], interactive=False)
    assert mgr.check("write_file", {"path": "x"}) == "deny"
    assert mgr.check("run_shell", {"command": "ls"}) == "deny"


def test_check_first_rule_wins():
    rules = [
        parse_rule("write_file", "deny"),
        parse_rule("write_file:src/**", "allow"),
    ]
    mgr = PermissionManager(rules=rules, interactive=False)
    # deny comes first — should win even for src/**
    assert mgr.check("write_file", {"path": "src/main.py"}) == "deny"


# ---------------------------------------------------------------------------
# PermissionManager.check — default (no rule match)
# ---------------------------------------------------------------------------

def test_check_no_match_interactive_returns_ask():
    mgr = PermissionManager(rules=[], interactive=True)
    assert mgr.check("write_file", {"path": "anything.py"}) == "ask"


def test_check_no_match_non_interactive_returns_allow():
    mgr = PermissionManager(rules=[], interactive=False)
    assert mgr.check("write_file", {"path": "anything.py"}) == "allow"


def test_check_unrelated_tool_no_match():
    mgr = PermissionManager(rules=[parse_rule("run_shell", "deny")], interactive=False)
    assert mgr.check("write_file", {"path": "x"}) == "allow"


# ---------------------------------------------------------------------------
# Approval flow — same thread (CLI pattern)
# ---------------------------------------------------------------------------

def test_resolve_approve_same_thread():
    mgr = PermissionManager()
    call_id = "tc-001"
    mgr.request_approval(call_id)
    mgr.resolve(call_id, True)
    result = mgr.wait_for_decision(call_id, timeout=0.1)
    assert result is True


def test_resolve_deny_same_thread():
    mgr = PermissionManager()
    call_id = "tc-002"
    mgr.request_approval(call_id)
    mgr.resolve(call_id, False)
    result = mgr.wait_for_decision(call_id, timeout=0.1)
    assert result is False


def test_wait_for_decision_timeout_returns_false():
    mgr = PermissionManager()
    call_id = "tc-timeout"
    mgr.request_approval(call_id)
    # Don't resolve — should time out
    result = mgr.wait_for_decision(call_id, timeout=0.05)
    assert result is False


# ---------------------------------------------------------------------------
# Approval flow — cross-thread (HTTP pattern)
# ---------------------------------------------------------------------------

def test_resolve_from_different_thread():
    mgr = PermissionManager()
    call_id = "tc-thread"
    mgr.request_approval(call_id)

    def _resolver():
        time.sleep(0.05)
        mgr.resolve(call_id, True)

    t = threading.Thread(target=_resolver, daemon=True)
    t.start()
    result = mgr.wait_for_decision(call_id, timeout=1.0)
    t.join()
    assert result is True


def test_multiple_pending_calls_resolved_independently():
    mgr = PermissionManager()
    for cid, approved in [("c1", True), ("c2", False), ("c3", True)]:
        mgr.request_approval(cid)
        mgr.resolve(cid, approved)

    assert mgr.wait_for_decision("c1", timeout=0.1) is True
    assert mgr.wait_for_decision("c2", timeout=0.1) is False
    assert mgr.wait_for_decision("c3", timeout=0.1) is True


# ---------------------------------------------------------------------------
# has_pending
# ---------------------------------------------------------------------------

def test_has_pending_true_before_resolve():
    mgr = PermissionManager()
    mgr.request_approval("p1")
    assert mgr.has_pending("p1") is True


def test_has_pending_false_after_resolve():
    mgr = PermissionManager()
    mgr.request_approval("p2")
    mgr.resolve("p2", True)
    mgr.wait_for_decision("p2", timeout=0.1)
    assert mgr.has_pending("p2") is False


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------

def test_register_and_get():
    mgr = PermissionManager()
    register("session-reg-1", mgr)
    assert get("session-reg-1") is mgr
    unregister("session-reg-1")


def test_get_returns_none_for_unknown_session():
    assert get("nonexistent-session-xyz") is None


def test_unregister_removes_entry():
    mgr = PermissionManager()
    register("session-unreg-1", mgr)
    unregister("session-unreg-1")
    assert get("session-unreg-1") is None


def test_unregister_idempotent():
    unregister("session-never-registered")  # should not raise


def test_registry_isolation():
    m1, m2 = PermissionManager(), PermissionManager()
    register("iso-1", m1)
    register("iso-2", m2)
    assert get("iso-1") is m1
    assert get("iso-2") is m2
    unregister("iso-1")
    unregister("iso-2")


# ---------------------------------------------------------------------------
# rules property
# ---------------------------------------------------------------------------

def test_rules_returns_copy():
    rules = [parse_rule("write_file", "allow")]
    mgr = PermissionManager(rules=rules)
    assert mgr.rules == rules
    mgr.rules.clear()  # mutating the returned list should not affect the manager
    assert len(mgr.rules) == 1
