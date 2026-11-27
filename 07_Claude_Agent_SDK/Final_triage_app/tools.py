"""IN-PROCESS MCP server: the support tools, written as plain async functions.

Contrast with ticket_store_mcp.py: no subprocess here - the SDK serves these
from inside this Python process, so they can share state and need no protocol
plumbing. Use this style for logic that belongs to your app; use a separate
stdio server for things you want reusable by other clients.

The agent sees these as mcp__support__<name>, because agent.py registers this
server under the key "support".

How a tool is defined:
    @tool(name, description, input_schema)
    async def fn(args: dict) -> {"content": [{"type": "text", "text": ...}]}
The DESCRIPTION is what Claude reads to decide when to call the tool, so it is
written as an instruction, not as documentation for humans.
"""
from __future__ import annotations

import json
import re
from typing import Any

from claude_agent_sdk import ToolAnnotations, create_sdk_mcp_server, tool

from . import config, store


def as_result(body: str, is_error: bool = False) -> dict[str, Any]:
    """Wrap text in the shape the SDK expects from every tool: {"content": [blocks]}."""
    result: dict[str, Any] = {"content": [{"type": "text", "text": body}]}
    if is_error:
        # Flags the call as FAILED, so Claude reads the text as an error to
        # recover from rather than as odd-looking data.
        result["is_error"] = True
    return result


# ------------------------------------------------------------------ search_kb
@tool(
    "search_kb",
    "Search the support knowledge base and return matching articles in full. Pass 2-5 "
    "keywords describing the customer's problem, e.g. 'duplicate charge refund'. Always "
    "call this before drafting a reply - never answer a support question from memory.",
    {"query": str},        # shorthand schema: one required string argument
    # readOnlyHint tells Claude this tool has no side effects, so it can safely
    # be called alongside other read-only tools.
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def search_kb(args: dict[str, Any]) -> dict[str, Any]:
    # Split the query into lowercase words; drop 1-2 letter words like "to", "a".
    terms = [t for t in re.split(r"[^a-z0-9]+", str(args.get("query", "")).lower()) if len(t) > 2]
    if not terms:
        return as_result("Empty query. Pass keywords, e.g. 'refund duplicate charge'.", True)

    # Deliberately simple keyword scoring: count how often each term appears in
    # each article. The routing policy is searched too, so it can be cited (KB-100).
    hits = []
    for path in sorted(config.KB_DIR.glob("*.md")) + [config.POLICY_FILE]:
        content = path.read_text(encoding="utf-8")
        score = sum(content.lower().count(t) for t in terms)
        if score:
            hits.append((score, path.name, content))
    if not hits:
        # An explicit "nothing found" is better than an empty string: it tells the
        # agent to escalate instead of inventing an answer.
        return as_result(f"No knowledge base article matches {terms}. Do not guess - say the "
                         "KB does not cover it and escalate.")
    hits.sort(reverse=True)                       # best match first
    # Return the top 3 articles IN FULL so the reply can be grounded in real text.
    return as_result("\n\n".join(f"--- {name} (relevance {score}) ---\n{content}"
                                 for score, name, content in hits[:3]))


# ------------------------------------------------------------- lookup_account
@tool(
    "lookup_account",
    "Look up the internal account record for a customer by full name: plan, monthly revenue, "
    "tenure, SSO enforcement, contracted API rate limit, and an operational note. Call this "
    "whenever the reply depends on the customer's plan or entitlements.",
    {"customer_name": str},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def lookup_account(args: dict[str, Any]) -> dict[str, Any]:
    accounts = json.loads(config.ACCOUNTS_FILE.read_text(encoding="utf-8"))
    name = str(args.get("customer_name", "")).strip()
    # Exact match first, then a case-insensitive fallback ("anita rao" works).
    record = accounts.get(name) or next(
        (v for k, v in accounts.items() if k.lower() == name.lower()), None)
    if record is None:
        # is_error=True + guidance: the agent carries on without an account
        # instead of assuming a plan it never saw.
        return as_result(f"No account found for '{name}'. Triage from the ticket and KB alone, "
                         "and do not assume a plan.", True)
    return as_result(json.dumps(record, indent=2))


# ------------------------------------------------------------ file_escalation
@tool(
    "file_escalation",
    "File an escalation to a downstream team. Only call when the routing policy says the "
    "ticket must leave tier 1. State the reason in one sentence, quoting the policy rule.",
    {
        # Full JSON-schema form, used when we need constraints. The `enum`s mean
        # the model physically cannot send a queue or priority we do not recognise.
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string", "description": "e.g. TKT-2001"},
            "queue": {"type": "string", "enum": config.QUEUES[1:]},   # tier1 is not an escalation
            "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
            "reason": {"type": "string", "description": "One sentence, cite the policy rule"},
        },
        "required": ["ticket_id", "queue", "priority", "reason"],
    },
)
async def file_escalation(args: dict[str, Any]) -> dict[str, Any]:
    if not store.valid_ticket_id(args["ticket_id"]):
        return as_result(f"{args['ticket_id']!r} is not a valid ticket id.", True)
    config.ensure_dirs()
    record = {"filed_at": store.now_iso(), **args}
    # JSON Lines: one record per line, append-only. Simple to write and to grep,
    # and a crash can never corrupt earlier entries.
    with config.ESCALATIONS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return as_result(f"Escalation filed to {args['queue']} at {args['priority']} for {args['ticket_id']}.")


# ---------------------------------------------------------------- save_triage
@tool(
    "save_triage",
    "Save the triage decision and draft reply for one ticket. Call after the KB has been "
    "consulted. All seven policy fields are required. If the customer asks for a revision, "
    "call it again with the updated values - it overwrites the previous decision.",
    {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "category": {"type": "string",
                         "enum": ["billing", "login", "api", "sso", "data", "incident", "other"]},
            "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
            "queue": {"type": "string", "enum": config.QUEUES},
            "kb_articles": {"type": "array", "items": {"type": "string"},
                            "description": "Article IDs actually used, e.g. ['KB-103']"},
            "draft_reply": {"type": "string", "description": "Customer-facing text"},
            "escalate": {"type": "boolean"},
            "escalation_reason": {"type": "string", "description": "Required when escalate is true"},
        },
        # The seven fields routing_policy.md demands for every ticket.
        # (escalation_reason is conditionally required - checked in code below.)
        "required": ["ticket_id", "category", "priority", "queue",
                     "kb_articles", "draft_reply", "escalate"],
    },
)
async def save_triage(args: dict[str, Any]) -> dict[str, Any]:
    # Deterministic checks live in code, not in the prompt. A schema can say a
    # field is required, but not "required WHEN escalate is true" - code can.
    # Each error message tells the agent exactly how to fix its next call.
    if not store.valid_ticket_id(args["ticket_id"]) or store.find_ticket(args["ticket_id"]) is None:
        return as_result(f"No ticket {args['ticket_id']!r} exists. Use the id from read_ticket.", True)
    if args["escalate"] and not args.get("escalation_reason"):
        return as_result("escalate is true but escalation_reason is missing. "
                         "Call save_triage again with a one-line reason.", True)
    if not args["kb_articles"]:
        # Forces grounding: a decision must cite where its facts came from.
        return as_result("kb_articles is empty. Cite the article IDs you used; if the KB does not "
                         "cover the question, cite KB-100 (the routing policy) and escalate.", True)

    path = store.write_result(args)
    return as_result(f"Saved triage for {args['ticket_id']} -> {path.name}")


def build_support_server():
    """A fresh server object per agent session (avoids sharing one instance across clients)."""
    return create_sdk_mcp_server(
        name="support", version="1.0.0",
        tools=[search_kb, lookup_account, file_escalation, save_triage],
    )


# Full tool names as the agent sees them: mcp__<server key in mcp_servers>__<tool name>
# (two underscores between each part). These lists feed `allowed_tools` in agent.py.
SUPPORT_TOOLS = [f"mcp__support__{t}" for t in
                 ("search_kb", "lookup_account", "file_escalation", "save_triage")]
TICKET_TOOLS = [f"mcp__tickets__{t}" for t in
                ("list_pending_tickets", "read_ticket", "mark_processed")]
