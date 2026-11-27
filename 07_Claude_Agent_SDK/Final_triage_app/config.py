"""Paths and environment, in one place.

Every other module imports its file locations and settings from here, so
moving the workspace or changing the model never means hunting through code.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# --------------------------------------------------------------- locations
APP_DIR = Path(__file__).resolve().parent      # .../triage_app  (this package)
ROOT = APP_DIR                          # .../claude-agent-sdk-course (course root)

# --------------------------------------------------------------- environment
# The Agent SDK does NOT read .env files by itself; it only sees real process
# environment variables. load_dotenv() copies the file's values into os.environ.
# We try the course root first, then notebooks/ (where the key currently lives).
# load_dotenv never overwrites a variable that is already set, so a real
# environment variable always wins over a file.
for _env in (ROOT / ".env", ROOT / "notebooks" / ".env"):
    if _env.exists():
        load_dotenv(_env)

# --------------------------------------------------------------- shared data
# The knowledge base, accounts and routing policy are shared with the course
# notebooks, so the app and the notebooks always agree on the "business rules".
DATA = ROOT / "data"
KB_DIR = DATA / "kb"                           # knowledge-base articles (*.md)
POLICY_FILE = DATA / "routing_policy.md"       # queues, priorities, hard stops
ACCOUNTS_FILE = DATA / "accounts.json"         # mock customer database
SAMPLE_TICKETS = DATA / "tickets.json"         # sample tickets for the `seed` command

# --------------------------------------------------------------- runtime files
# Everything the app creates while running lives under ONE folder (git-ignored).
# Override with the TRIAGE_WORKSPACE env var, e.g. to keep tests isolated.
WORKSPACE = Path(os.environ.get("TRIAGE_WORKSPACE") or APP_DIR / "workspace")
INBOX = WORKSPACE / "inbox"            # tickets the user submitted (the agent reads these)
PROCESSED = WORKSPACE / "processed"    # tickets the agent has finished with
OUTBOX = WORKSPACE / "outbox"          # triage decisions (.json) and draft replies (.reply.md)
SESSIONS_FILE = WORKSPACE / "sessions.json"        # ticket id -> SDK session id (for resume)
ESCALATIONS_FILE = WORKSPACE / "escalations.jsonl" # one JSON line per escalation filed
AUDIT_FILE = WORKSPACE / "audit.jsonl"             # one JSON line per tool call the agent made

# --------------------------------------------------------------- model
# Which Claude model the agent uses. Set COURSE_MODEL in .env to pin one
# (e.g. COURSE_MODEL=claude-sonnet-5-5). When it is empty we pass None and the
# SDK falls back to its own default model, which changes over time.
MODEL = os.environ.get("COURSE_MODEL") or None

# --------------------------------------------------------------- LangSmith
# Optional tracing. Enable with LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env
# (see agent.enable_langsmith). Traces land in this LangSmith project.
LANGSMITH_PROJECT = os.environ.get("LANGSMITH_PROJECT") or "triage-app"

# The only queues a ticket may be routed to (mirrors data/routing_policy.md).
QUEUES = ["tier1", "billing-ops", "api-platform", "identity-eng", "privacy", "incident-response"]


def ensure_dirs() -> None:
    """Create the workspace folders if they do not exist yet. Safe to call repeatedly."""
    for d in (INBOX, PROCESSED, OUTBOX):
        d.mkdir(parents=True, exist_ok=True)
