"""Hooks: code that runs around every tool call, outside the model's control.

A prompt asks the model to behave; a hook makes it. The model cannot talk its
way past a hook, because the hook is ordinary Python that runs before the tool.

1. audit_hook      - appends every tool call to workspace/audit.jsonl
2. hard_stop_guard - blocks save_triage when the draft reply breaks one of the
                     four absolute rules in routing_policy.md. The model gets the
                     reason back and rewrites the reply.
"""
from __future__ import annotations

import json
import re
from typing import Any

from claude_agent_sdk import HookMatcher

from . import config, store

# The four things routing_policy.md ("Hard stops") forbids, as (regex, label).
# Regexes are blunt on purpose: a false positive only costs one rewrite of the
# reply, while a false negative would let a forbidden statement reach a customer.
HARD_STOPS = [
    (r"\b(has been|have been|was|were|is)\s+(permanently\s+)?deleted\b", "confirms personal data was deleted"),
    (r"\b(caused by|due to|because of)\s+(the\s+)?(2026[-.\d]*\s*)?(release|update|deploy|deployment)\b",
     "blames a specific release"),
    (r"\bpro[- ]?rated?\s+refund\b", "promises a prorated refund"),
    (r"\b(yes|confirm(ed)?),?\s+(that\s+)?(email|address|account)\s+is\s+registered\b",
     "confirms an email address is registered"),
]


def find_violations(reply: str) -> list[str]:
    """Labels of every hard stop the reply breaks (empty list = clean)."""
    return [why for pattern, why in HARD_STOPS if re.search(pattern, reply, re.IGNORECASE)]


# Hook callbacks all share this signature:
#   input_data   - what is about to happen (tool_name, tool_input, ...)
#   tool_use_id  - id of this particular call (unused here)
#   context      - SDK-provided context (unused here)
# Returning {} means "no opinion - carry on". Returning a decision overrides that.

async def audit_hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
    """Record every tool call - a permanent trail of what the agent actually did."""
    config.ensure_dirs()
    entry = {"at": store.now_iso(), "tool": input_data.get("tool_name"),
             # Truncated so one huge draft reply cannot bloat the log.
             "input": json.dumps(input_data.get("tool_input"), default=str)[:400]}
    with config.AUDIT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return {}      # empty = no opinion, let the call proceed


async def hard_stop_guard(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
    """Veto save_triage if the draft reply contains a forbidden statement."""
    reply = str((input_data.get("tool_input") or {}).get("draft_reply", ""))
    violations = find_violations(reply)
    if not violations:
        return {}
    # "deny" stops the tool from running at all. The reason text is fed back to
    # the model, which then rewrites the reply and calls save_triage again.
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "Draft reply blocked by policy hard stops: " + "; ".join(violations) +
            ". Rewrite the reply so it does not make these statements, then call save_triage again."),
    }}


def build_hooks() -> dict[str, list[HookMatcher]]:
    """Wire the callbacks to events. Returned dict goes straight into ClaudeAgentOptions(hooks=...)."""
    return {"PreToolUse": [
        # No matcher = fires for EVERY tool call.
        HookMatcher(hooks=[audit_hook]),
        # Matcher = fires only for this one tool (full mcp__server__tool name).
        HookMatcher(matcher="mcp__support__save_triage", hooks=[hard_stop_guard]),
    ]}
