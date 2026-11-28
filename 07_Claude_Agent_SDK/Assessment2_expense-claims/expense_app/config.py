"""Paths, environment and limits, in one place.

Every other module imports its file locations and settings from here, so moving
the workspace or changing the model never means hunting through code.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# --------------------------------------------------------------- locations
APP_DIR = Path(__file__).resolve().parent          # .../expense_app (the package)
ROOT = APP_DIR.parent                              # project root (README lives here)

# The Agent SDK only sees real process environment variables; it does not read
# .env files itself. load_dotenv() never overrides a variable that is already set.
load_dotenv(ROOT / ".env")

# --------------------------------------------------------------- reference data (read-only)
DATA = ROOT / "data"
KB_DIR = DATA / "kb"                                # EX-201 .. EX-206
POLICY_FILE = DATA / "expense_policy.md"            # EX-200, the decision framework
EMPLOYEES_FILE = DATA / "employees.json"
PAST_CLAIMS_FILE = DATA / "past_claims.json"
FX_FILE = DATA / "fx_rates.json"
SAMPLE_CLAIMS_FILE = DATA / "claims.json"

# --------------------------------------------------------------- runtime files
# Override with EXPENSE_WORKSPACE (tests use a temporary folder).
WORKSPACE = Path(os.environ.get("EXPENSE_WORKSPACE") or ROOT)
INBOX = WORKSPACE / "inbox"            # one JSON file per submitted claim
OUTBOX = WORKSPACE / "outbox"          # one decision JSON + one reply .md per reviewed claim
RELEASED = WORKSPACE / "released"      # replies a person has approved (the only ones fit to send)
STATE = WORKSPACE / "state"            # sessions, audit log, run log
SESSIONS_FILE = STATE / "sessions.json"     # claim id -> SDK session id (for resume)
AUDIT_FILE = STATE / "audit.jsonl"          # one line per tool call (PreToolUse + PostToolUse)
RUNS_FILE = STATE / "runs.jsonl"            # one line per agent run: turns, cost, outcome
APPROVALS_FILE = STATE / "approvals.jsonl"  # one line per human approval / change request
CHAT_DIR = STATE / "chat"                   # per-claim conversation log shown in the web UI
EXPECTED_FILE = ROOT / "tests" / "expected_samples.json"  # my own expected answers (scoring)
RESULTS_DIR = ROOT / "results"              # deliverable: exported decisions

# --------------------------------------------------------------- model and limits
MODEL = os.environ.get("EXPENSE_MODEL") or "claude-opus-5-5"
MAX_TURNS = int(os.environ.get("EXPENSE_MAX_TURNS") or 30)          # per agent run
MAX_BUDGET_USD = float(os.environ.get("EXPENSE_MAX_BUDGET_USD") or 1.00)  # per agent run

# --------------------------------------------------------------- policy vocabulary
DECISIONS = ["approve", "reject", "needs_info", "escalate"]
ESCALATION_TARGETS = ["manager", "finance-controller", "compliance", "none"]
FLAGS = ["alcohol_excluded", "over_limit", "duplicate", "late_submission", "split_purchase",
         "missing_receipt", "invalid_preapproval", "prohibited_item", "double_claim",
         "monthly_cap_exceeded", "injection_attempt"]
ARTICLE_IDS = ["EX-200", "EX-201", "EX-202", "EX-203", "EX-204", "EX-205", "EX-206"]
CATEGORIES = ["meals", "travel", "equipment", "software", "entertainment", "other"]
PREAPPROVAL_TYPES = ["equipment", "client_entertainment", "travel_business_class"]


def ensure_dirs() -> None:
    """Create the runtime folders if missing. Safe to call repeatedly."""
    for d in (INBOX, OUTBOX, RELEASED, STATE, CHAT_DIR):
        d.mkdir(parents=True, exist_ok=True)
