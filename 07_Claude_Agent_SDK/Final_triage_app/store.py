"""The local file store: tickets in, decisions out, session ids remembered.

Plain files on purpose - a ticket is a markdown file you can open, edit, or
delete by hand. Nothing here talks to the model, so it is fully testable offline.

Ticket file format (workspace/inbox/TKT-2001.md):

    ---
    id: TKT-2001
    customer: Anita Rao
    channel: web
    received_at: 2026-03-02T09:14:00Z
    subject: Charged twice for March
    ---

    free-text body ...

Lifecycle of a ticket:
    save_ticket()        -> inbox/TKT-x.md              (status "pending")
    agent: save_triage   -> outbox/TKT-x.json + .reply.md
    agent: mark_processed-> processed/TKT-x.md          (status "processed")
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

# Ticket ids become part of file paths, so only this exact shape is ever accepted.
# This is what stops an id like "../../secrets" from escaping the workspace.
TICKET_ID_RE = re.compile(r"^TKT-\d{3,6}$")

# data/tickets.json already uses TKT-1001..TKT-1010, so tickets typed by a user
# start at 2001 to avoid colliding with the samples.
FIRST_USER_TICKET = 2001


def now_iso() -> str:
    """Current UTC time like 2026-03-02T09:14:00Z (second precision)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def valid_ticket_id(ticket_id: str) -> bool:
    """True only for ids shaped exactly like TKT-2001."""
    return bool(TICKET_ID_RE.match(str(ticket_id)))


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file, then rename.

    The agent (via the MCP server) may read a ticket at the same moment the CLI is
    writing it. os.replace() swaps the file in one step, so a reader sees either
    the old complete file or the new complete file - never a half-written one.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------- tickets

def next_ticket_id() -> str:
    """Pick the next free id by scanning every folder for the highest TKT number."""
    config.ensure_dirs()
    numbers = [FIRST_USER_TICKET - 1]          # so an empty workspace yields 2001
    for folder in (config.INBOX, config.PROCESSED, config.OUTBOX):
        for p in folder.iterdir():
            m = re.match(r"TKT-(\d+)", p.name)
            # Ignore sample tickets (1001..) so seeding them never shifts our numbering.
            if m and int(m.group(1)) >= FIRST_USER_TICKET:
                numbers.append(int(m.group(1)))
    return f"TKT-{max(numbers) + 1}"


def _one_line(value: str) -> str:
    """Collapse all whitespace/newlines to single spaces (header values must be one line)."""
    return " ".join(str(value).split())


def save_ticket(customer: str, subject: str, body: str, channel: str = "web",
                ticket_id: str | None = None, **extra: str) -> Path:
    """Requirement 1: user content -> a file on local disk. Returns its path."""
    config.ensure_dirs()
    customer, subject, body = _one_line(customer), _one_line(subject), body.strip()
    if not (customer and subject and body):
        raise ValueError("customer, subject and body are all required")

    ticket_id = ticket_id or next_ticket_id()
    if not valid_ticket_id(ticket_id):
        raise ValueError(f"bad ticket id: {ticket_id!r}")

    # Header = small key/value block; body = whatever the customer typed, untouched.
    header = {"id": ticket_id, "customer": customer, "channel": channel,
              "received_at": now_iso(), "subject": subject,
              **{k: _one_line(v) for k, v in extra.items()}}
    text = "---\n" + "\n".join(f"{k}: {v}" for k, v in header.items()) + "\n---\n\n" + body + "\n"

    path = config.INBOX / f"{ticket_id}.md"
    _atomic_write(path, text)
    return path


def parse_ticket(path: Path) -> dict[str, Any]:
    """Read a ticket file back into a dict: header fields + body + path + status."""
    text = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    body = text
    if text.startswith("---\n"):
        # The header ends at the FIRST later "---" line. Using find() (not split)
        # means a "---" inside the customer's body can never be mistaken for it.
        end = text.find("\n---\n", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip()
            body = text[end + 5:]
    meta["body"] = body.strip()
    meta["path"] = str(path)
    # Status is simply "which folder is it in" - no separate state to keep in sync.
    meta["status"] = "pending" if path.parent == config.INBOX else "processed"
    return meta


def find_ticket(ticket_id: str) -> Path | None:
    """Locate a ticket in inbox or processed. None if the id is invalid or unknown."""
    if not valid_ticket_id(ticket_id):
        return None
    for folder in (config.INBOX, config.PROCESSED):
        p = folder / f"{ticket_id}.md"
        if p.exists():
            return p
    return None


def list_tickets(status: str = "pending") -> list[dict[str, Any]]:
    """All tickets with the given status ('pending', 'processed' or 'all'), oldest first."""
    config.ensure_dirs()
    folders = {"pending": [config.INBOX], "processed": [config.PROCESSED],
               "all": [config.INBOX, config.PROCESSED]}[status]
    out = [parse_ticket(p) for f in folders for p in f.glob("TKT-*.md")]
    return sorted(out, key=lambda t: t.get("received_at", ""))


def mark_processed(ticket_id: str) -> Path:
    """Move a ticket from inbox/ to processed/. Raises FileNotFoundError if not in the inbox."""
    src = config.INBOX / f"{ticket_id}.md"
    if not valid_ticket_id(ticket_id) or not src.exists():
        raise FileNotFoundError(f"{ticket_id} is not in the inbox")
    dst = config.PROCESSED / src.name
    shutil.move(str(src), str(dst))
    return dst


def seed_samples(ids: list[str] | None = None) -> list[str]:
    """Copy tickets from data/tickets.json into the inbox (keeps their original ids).

    Handy for demos. Already-present tickets are skipped, so it is safe to re-run.
    Returns the ids that were actually added.
    """
    samples = json.loads(config.SAMPLE_TICKETS.read_text(encoding="utf-8"))
    added = []
    for t in samples:
        if ids and t["id"] not in ids:
            continue
        if find_ticket(t["id"]):
            continue
        save_ticket(t["customer"], t["subject"], t["body"], channel=t.get("channel", "sample"),
                    ticket_id=t["id"])
        added.append(t["id"])
    return added


# --------------------------------------------------------------------- results

def result_path(ticket_id: str) -> Path:
    """Where the saved decision for a ticket lives (outbox/TKT-x.json)."""
    return config.OUTBOX / f"{ticket_id}.json"


def load_result(ticket_id: str) -> dict[str, Any] | None:
    """The saved triage decision, or None if the agent has not saved one yet."""
    p = result_path(ticket_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def write_result(record: dict[str, Any]) -> Path:
    """Persist a triage decision as JSON plus a human-readable reply file.

    Calling it again for the same ticket overwrites the decision and bumps
    `revision` - that is how follow-up edits ("make it shorter") are tracked.
    """
    config.ensure_dirs()
    tid = record["ticket_id"]
    previous = load_result(tid)
    record = {**record, "saved_at": now_iso(),
              "revision": (previous or {}).get("revision", 0) + 1}
    _atomic_write(result_path(tid), json.dumps(record, indent=2))

    # The .reply.md is the file a human agent would actually open and send.
    reply = (f"# Reply to {tid}\n\n"
             f"- Category: {record['category']}\n- Priority: {record['priority']}\n"
             f"- Queue: {record['queue']}\n- Escalate: {record['escalate']}\n"
             f"- KB articles: {', '.join(record['kb_articles'])}\n\n---\n\n"
             f"{record['draft_reply'].strip()}\n")
    _atomic_write(config.OUTBOX / f"{tid}.reply.md", reply)
    return result_path(tid)


# -------------------------------------------------------------------- sessions
# The SDK gives every conversation a session id. We store ticket -> session id
# so a later process can pass it as `resume=` and continue the same conversation
# with all its context (the ticket, the KB articles read, earlier decisions).

def _load_sessions() -> dict[str, Any]:
    if config.SESSIONS_FILE.exists():
        return json.loads(config.SESSIONS_FILE.read_text(encoding="utf-8"))
    return {}


def remember_session(ticket_id: str, session_id: str) -> None:
    """Record (or update) the session id for a ticket."""
    config.ensure_dirs()
    data = _load_sessions()
    data[ticket_id] = {"session_id": session_id, "updated_at": now_iso()}
    _atomic_write(config.SESSIONS_FILE, json.dumps(data, indent=2))


def get_session(ticket_id: str) -> str | None:
    """The saved session id for a ticket, or None if it has never been triaged."""
    return (_load_sessions().get(ticket_id) or {}).get("session_id")
