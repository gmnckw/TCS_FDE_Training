"""Hooks: ordinary Python that runs around every tool call, outside the model's control.

A prompt asks the model to behave; a hook makes it.

PreToolUse
  1. audit_pre       every call -> state/audit.jsonl (tool, input, session)
  2. allowlist_guard denies anything not on the allow-list (belt and braces on top of
                     tools=[] / allowed_tools / permission_mode="dontAsk")
  3. save_guard      save_decision only: the claim must have been read through
                     read_claim first, and the decision must pass every rule in
                     policy.decision_problems (order of checks, amounts, monthly cap,
                     hard stops in the reply). Otherwise the call is denied and the
                     reasons go back to the model, which fixes them and tries again.
PostToolUse
  4. audit_post      every result -> state/audit.jsonl (truncated), and remembers
                     which claims were read via read_claim.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from claude_agent_sdk import HookMatcher

from . import config, policy, store
from .tools import ALLOWED_TOOLS, SAVE_TOOL

READ_CLAIM_TOOL = "mcp__claims__read_claim"

# Claims read through the external MCP server in this process (claim ids).
_claims_read: set[str] = set()
# Optional live display hook, set by the agent wrapper (e.g. print guard denials on screen).
on_event: Callable[[str], None] | None = None


def _audit(entry: dict[str, Any]) -> None:
    config.ensure_dirs()
    with config.AUDIT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": store.now_iso(), **entry}, default=str) + "\n")


def _deny(reason: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _claim_id_of(tool_input: Any) -> str | None:
    return (tool_input or {}).get("claim_id") if isinstance(tool_input, dict) else None


async def audit_pre(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
    _audit({"event": "pre", "session": input_data.get("session_id"), "tool_use_id": tool_use_id,
            "tool": input_data.get("tool_name"),
            "input": json.dumps(input_data.get("tool_input"), default=str)[:1500]})
    return {}


async def allowlist_guard(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
    name = input_data.get("tool_name")
    if name in ALLOWED_TOOLS:
        return {}
    _audit({"event": "denied", "tool": name, "reason": "not on allow-list"})
    return _deny(f"{name} is not available to the expense reviewer.")


async def save_guard(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
    args = input_data.get("tool_input") or {}
    claim_id = _claim_id_of(args)
    claim = store.load_claim(claim_id) if claim_id else None
    if claim is None:
        return {}                       # the tool itself returns a helpful "no such claim" error
    problems: list[str] = []
    if claim_id not in _claims_read and store.load_decision(claim_id) is None:
        problems.append(f"Read the claim first with read_claim('{claim_id}'); decisions must be based on the "
                        "claim file, not on a summary.")
    problems += policy.decision_problems(args, claim)
    if not problems:
        return {}
    _audit({"event": "denied", "tool": SAVE_TOOL, "claim_id": claim_id, "problems": problems})
    if on_event:
        on_event("guard blocked save_decision: " + " | ".join(problems))
    return _deny("Decision NOT saved. Fix these and call save_decision again:\n- " + "\n- ".join(problems))


async def audit_post(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
    name = input_data.get("tool_name")
    if name == READ_CLAIM_TOOL:
        cid = _claim_id_of(input_data.get("tool_input"))
        if cid and store.load_claim(cid) is not None:
            _claims_read.add(cid)
    _audit({"event": "post", "session": input_data.get("session_id"), "tool_use_id": tool_use_id,
            "tool": name, "result": json.dumps(input_data.get("tool_response"), default=str)[:1500]})
    return {}


def build_hooks() -> dict[str, list[HookMatcher]]:
    return {
        "PreToolUse": [
            HookMatcher(hooks=[audit_pre, allowlist_guard]),          # no matcher: every tool
            HookMatcher(matcher=SAVE_TOOL, hooks=[save_guard]),
        ],
        "PostToolUse": [HookMatcher(hooks=[audit_post])],
    }
