"""The local file store: claims in, decisions out, session ids remembered.

Plain JSON files on purpose: a claim is a file you can open and read. Nothing in
this module talks to the model, so it is fully testable offline.

    inbox/CLM-4001.json          the claim as submitted (never modified after intake)
    outbox/CLM-4001.json         the latest decision (all seven policy fields + metadata)
    outbox/CLM-4001.reply.md     the draft message to the employee, human-readable
    outbox/CLM-4001.history.jsonl every revision of the decision, append-only
    state/sessions.json          claim id -> SDK session id, for follow-ups after a restart

A claim is "pending" until a decision exists in the outbox.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, policy

# Claim ids become file names, so only this exact shape is accepted anywhere.
# It is what stops an id like "../../secrets" from escaping the workspace.
CLAIM_ID_RE = re.compile(r"^CLM-\d{4,6}$")
FIRST_USER_CLAIM = 4001          # data/claims.json uses CLM-3001..3010

MAX_DESCRIPTION = 4000
MAX_FIELD = 200


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def valid_claim_id(claim_id: Any) -> bool:
    return bool(CLAIM_ID_RE.match(str(claim_id or "")))


def _atomic_write(path: Path, text: str) -> None:
    """Write to a temp file then swap it in, so a reader never sees half a file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _one_line(value: Any, limit: int = MAX_FIELD) -> str:
    return " ".join(str(value if value is not None else "").split())[:limit]


# ------------------------------------------------------------------ intake (R1)
def next_claim_id() -> str:
    config.ensure_dirs()
    numbers = [FIRST_USER_CLAIM - 1]
    for folder in (config.INBOX, config.OUTBOX):
        for p in folder.iterdir():
            m = re.match(r"CLM-(\d+)", p.name)
            if m and int(m.group(1)) >= FIRST_USER_CLAIM:
                numbers.append(int(m.group(1)))
    return f"CLM-{max(numbers) + 1}"


def validate_intake(fields: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalise user input and list what is wrong with it. Structural checks only:
    policy questions (unknown employee, unsupported currency ...) are for the reviewer."""
    errors: list[str] = []
    c: dict[str, Any] = {}
    c["employee"] = _one_line(fields.get("employee"))
    c["expense_date"] = _one_line(fields.get("expense_date"), 10)
    c["category"] = _one_line(fields.get("category"), 40).lower()
    c["vendor"] = _one_line(fields.get("vendor"))
    c["currency"] = _one_line(fields.get("currency"), 3).upper()
    receipt = _one_line(fields.get("receipt"), 10).lower()
    c["receipt"] = {"yes": "attached", "y": "attached", "true": "attached", "attached": "attached",
                    "no": "missing", "n": "missing", "false": "missing", "missing": "missing"}.get(receipt, receipt)
    pa = _one_line(fields.get("pre_approval"), 40)
    c["pre_approval"] = pa if pa and pa.lower() not in ("none", "null", "-", "n/a") else None
    c["description"] = str(fields.get("description") or "").strip()[:MAX_DESCRIPTION]

    if not c["employee"]:
        errors.append("employee name is required")
    try:
        policy.parse_date(c["expense_date"])
    except policy.PolicyDataError:
        errors.append("expense_date must be YYYY-MM-DD")
    if c["category"] not in config.CATEGORIES:
        errors.append(f"category must be one of {', '.join(config.CATEGORIES)}")
    if not c["vendor"]:
        errors.append("vendor is required")
    try:
        amount = policy.money(fields.get("amount"))
        if amount <= 0:
            errors.append("amount must be greater than zero")
        c["amount"] = float(amount)
    except policy.PolicyDataError:
        errors.append("amount must be a number, e.g. 42.50")
    if not re.fullmatch(r"[A-Z]{3}", c["currency"]):
        errors.append("currency must be a 3-letter code, e.g. USD")
    if c["receipt"] not in ("attached", "missing"):
        errors.append("receipt must be 'attached' or 'missing'")
    if not c["description"]:
        errors.append("description is required: say what the expense was and why")
    return c, errors


def save_claim(fields: dict[str, Any], claim_id: str | None = None,
               submitted_at: str | None = None, source: str = "user") -> Path:
    """Requirement 1: the user's content becomes one file in inbox/. Returns its path."""
    config.ensure_dirs()
    claim, errors = validate_intake(fields)
    if errors:
        raise ValueError("; ".join(errors))
    claim_id = claim_id or next_claim_id()
    if not valid_claim_id(claim_id):
        raise ValueError(f"bad claim id: {claim_id!r}")
    path = config.INBOX / f"{claim_id}.json"
    if path.exists():
        raise ValueError(f"{claim_id} already exists")
    record = {"id": claim_id, "employee": claim["employee"],
              "submitted_at": submitted_at or now_iso(),
              "expense_date": claim["expense_date"], "category": claim["category"],
              "vendor": claim["vendor"], "amount": claim["amount"], "currency": claim["currency"],
              "receipt": claim["receipt"], "pre_approval": claim["pre_approval"],
              "description": claim["description"], "source": source}
    _atomic_write(path, json.dumps(record, indent=2, ensure_ascii=False))
    return path


def seed_samples(ids: list[str] | None = None) -> list[str]:
    """Copy data/claims.json into the inbox, keeping their ids and submitted_at. Re-runnable."""
    samples = json.loads(config.SAMPLE_CLAIMS_FILE.read_text(encoding="utf-8"))
    added = []
    for s in samples:
        if ids and s["id"] not in ids:
            continue
        if load_claim(s["id"]) is not None:
            continue
        fields = {**s, "receipt": s.get("receipt")}
        save_claim(fields, claim_id=s["id"], submitted_at=s["submitted_at"], source="sample")
        added.append(s["id"])
    return added


def load_claim(claim_id: str) -> dict[str, Any] | None:
    """The claim as stored, or None for an unknown or malformed id."""
    if not valid_claim_id(claim_id):
        return None
    path = config.INBOX / f"{claim_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_claims(status: str = "all") -> list[dict[str, Any]]:
    """Claims with status 'pending' (no decision yet), 'reviewed' or 'all', oldest first."""
    config.ensure_dirs()
    out = []
    for p in sorted(config.INBOX.glob("CLM-*.json")):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        c["status"] = "reviewed" if decision_path(c["id"]).exists() else "pending"
        if status in ("all", c["status"]):
            out.append(c)
    return sorted(out, key=lambda c: (c.get("submitted_at", ""), c["id"]))


# ------------------------------------------------------------------ decisions
def decision_path(claim_id: str) -> Path:
    return config.OUTBOX / f"{claim_id}.json"


def load_decision(claim_id: str) -> dict[str, Any] | None:
    if not valid_claim_id(claim_id):
        return None
    p = decision_path(claim_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def write_decision(record: dict[str, Any]) -> Path:
    """Persist a decision. Saving again (after a follow-up) overwrites it and bumps
    `revision`; every revision is also appended to the history file.

    Every new revision starts as `pending_review`, and any reply released for an
    earlier revision is withdrawn: a person must approve what is actually saved."""
    config.ensure_dirs()
    cid = record["claim_id"]
    previous = load_decision(cid)
    revision = (previous or {}).get("revision", 0) + 1
    record = {**record, "saved_at": now_iso(), "revision": revision,
              "approval": {"status": "pending_review", "revision": revision}}
    _atomic_write(decision_path(cid), json.dumps(record, indent=2, ensure_ascii=False))
    with (config.OUTBOX / f"{cid}.history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    _atomic_write(config.OUTBOX / f"{cid}.reply.md", render_reply_md(record))
    released_path(cid).unlink(missing_ok=True)
    return decision_path(cid)


def render_reply_md(r: dict[str, Any]) -> str:
    esc = r["escalate_to"] + (f" ({r.get('escalation_reason')})" if r["escalate_to"] != "none" else "")
    approval = r.get("approval") or {"status": "pending_review"}
    who = f" by {approval['by']} at {approval['at']}" if approval.get("by") else ""
    return (f"# Decision for {r['claim_id']} (revision {r['revision']})\n\n"
            f"| Field | Value |\n|---|---|\n"
            f"| decision | `{r['decision']}` |\n"
            f"| approved_amount_usd | {r['approved_amount_usd']:.2f} |\n"
            f"| policy_refs | {', '.join(r['policy_refs'])} |\n"
            f"| flags | {', '.join(r['flags']) or '-'} |\n"
            f"| escalate_to | {esc} |\n"
            f"| reply approval | `{approval['status']}`{who} |\n\n"
            f"**Reviewer notes:** {r.get('reviewer_notes', '')}\n\n"
            f"## Draft reply to the employee (held until a finance reviewer approves it)\n\n"
            f"{r['reply_to_employee'].strip()}\n")


# ------------------------------------------------------------------ human approval of the reply
# The agent has no tool that can reach these functions: only a person, through the
# CLI or the web UI, can approve a reply. Approval is tied to one revision.
APPROVAL_STATES = ("pending_review", "approved", "changes_requested")


def released_path(claim_id: str) -> Path:
    return config.RELEASED / f"{claim_id}.reply.md"


def set_approval(claim_id: str, status: str, by: str, note: str = "") -> dict[str, Any]:
    """Record a person's verdict on the current revision's reply.

    'approved' re-runs the code checks (reply hard stops and decision rules) and, if
    they pass, writes the reply to released/ - the only folder an integration that
    actually emails employees would read. Anything else withdraws a released reply."""
    if status not in APPROVAL_STATES[1:]:
        raise ValueError(f"status must be one of {APPROVAL_STATES[1:]}")
    by = _one_line(by, 80)
    if not by:
        raise ValueError("the approver's name is required")
    if status == "changes_requested" and not note.strip():
        raise ValueError("say what needs to change (note)")
    d = load_decision(claim_id)
    claim = load_claim(claim_id)
    if d is None or claim is None:
        raise ValueError(f"no saved decision for {claim_id!r}")
    if status == "approved":
        problems = policy.decision_problems(d, claim)
        if problems:
            raise ValueError("cannot approve - the saved decision fails the policy checks: " + "; ".join(problems))
    d["approval"] = {"status": status, "revision": d["revision"], "by": by, "at": now_iso(),
                     "note": note.strip()}
    _atomic_write(decision_path(claim_id), json.dumps(d, indent=2, ensure_ascii=False))
    _atomic_write(config.OUTBOX / f"{claim_id}.reply.md", render_reply_md(d))
    with config.APPROVALS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"claim_id": claim_id, **d["approval"]}, ensure_ascii=False) + "\n")
    if status == "approved":
        _atomic_write(released_path(claim_id),
                      f"<!-- {claim_id} revision {d['revision']}, approved by {by} at {d['approval']['at']} -->\n"
                      f"{d['reply_to_employee'].strip()}\n")
    else:
        released_path(claim_id).unlink(missing_ok=True)
    return d


# ------------------------------------------------------------------ sessions (R3)
def _load_sessions() -> dict[str, Any]:
    if config.SESSIONS_FILE.exists():
        return json.loads(config.SESSIONS_FILE.read_text(encoding="utf-8"))
    return {}


def remember_session(claim_id: str, session_id: str) -> None:
    config.ensure_dirs()
    data = _load_sessions()
    data[claim_id] = {"session_id": session_id, "updated_at": now_iso()}
    _atomic_write(config.SESSIONS_FILE, json.dumps(data, indent=2))


def get_session(claim_id: str) -> str | None:
    return (_load_sessions().get(claim_id) or {}).get("session_id")


def append_chat(claim_id: str, prompt: str, answer: str, tools: list[str], cost_usd: float) -> None:
    """Display copy of the conversation (the SDK session is the agent's real memory)."""
    if not valid_claim_id(claim_id):
        return
    config.ensure_dirs()
    with (config.CHAT_DIR / f"{claim_id}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now_iso(), "prompt": prompt, "answer": answer, "tools": tools,
                             "cost_usd": cost_usd}, ensure_ascii=False) + "\n")


def load_chat(claim_id: str) -> list[dict[str, Any]]:
    p = config.CHAT_DIR / f"{claim_id}.jsonl"
    if not valid_claim_id(claim_id) or not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def log_run(entry: dict[str, Any]) -> None:
    config.ensure_dirs()
    with config.RUNS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now_iso(), **entry}) + "\n")
