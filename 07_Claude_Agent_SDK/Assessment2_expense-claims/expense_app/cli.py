"""Command-line front end.

    python -m expense_app submit              enter a claim (prompts for each field) -> inbox/
    python -m expense_app seed                copy the ten sample claims into inbox/
    python -m expense_app list                claims and their status
    python -m expense_app review CLM-3001     run the agent on one claim (tool calls shown live)
    python -m expense_app review-all          review every pending claim, then a summary table with cost
    python -m expense_app ask CLM-3001 "..."  one follow-up question (works after a restart)
    python -m expense_app chat CLM-3001       interactive follow-ups until you type 'exit'
    python -m expense_app show CLM-3001       print the saved decision and draft reply
    python -m expense_app trace CLM-3001      print the audited tool calls for a claim
    python -m expense_app check               re-verify every saved decision against the policy code
    python -m expense_app score               score results/ against tests/expected_samples.json, per field
    python -m expense_app approve CLM-3001 --by "Ana"            release the reply (human sign-off)
    python -m expense_app request-changes CLM-3001 --by "Ana" --note "..."   hold it back
    python -m expense_app export              copy decisions to results/ with a summary table

Web UI: streamlit run app.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from typing import Any

from . import config, policy, store

# Windows consoles default to a legacy code page; make sure any text prints.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

FIELDS = [
    ("employee", "Employee full name"),
    ("expense_date", "Expense date (YYYY-MM-DD)"),
    ("category", f"Category ({'/'.join(config.CATEGORIES)})"),
    ("vendor", "Vendor"),
    ("amount", "Amount (e.g. 42.50)"),
    ("currency", "Currency (3 letters, e.g. USD)"),
    ("receipt", "Receipt attached? (yes/no)"),
    ("pre_approval", "Pre-approval number (blank if none)"),
    ("description", "Description (what and why)"),
]


# ------------------------------------------------------------------ display
def print_decision(d: dict[str, Any] | None) -> None:
    if not d:
        print("  (no decision saved)")
        return
    print(f"\n  Claim {d['claim_id']}  -  revision {d['revision']}  -  saved {d['saved_at']}")
    print(f"  decision            : {d['decision']}")
    print(f"  approved_amount_usd : {d['approved_amount_usd']:.2f}")
    print(f"  policy_refs         : {', '.join(d['policy_refs'])}")
    print(f"  flags               : {', '.join(d['flags']) or '-'}")
    esc = d["escalate_to"] + (f"  ({d['escalation_reason']})" if d["escalate_to"] != "none" else "")
    print(f"  escalate_to         : {esc}")
    print(f"  reviewer notes      : {d.get('reviewer_notes', '')}")
    print(f"  reply approval      : {approval_label(d)}")
    print("\n  ---- draft reply to the employee (held until a person approves it) ----")
    for line in d["reply_to_employee"].splitlines():
        print(f"  | {line}")
    print()


def approval_label(d: dict[str, Any]) -> str:
    a = d.get("approval") or {"status": "pending_review"}
    if a.get("by"):
        return f"{a['status']} by {a['by']} at {a['at']} (revision {a['revision']})" + \
            (f" - {a['note']}" if a.get("note") else "")
    return a["status"]


def cmd_approval(claim_id: str, status: str, by: str, note: str) -> int:
    try:
        d = store.set_approval(claim_id, status, by, note)
    except ValueError as exc:
        print(f"Not recorded: {exc}")
        return 1
    print(f"{claim_id} revision {d['revision']}: {approval_label(d)}")
    if status == "approved":
        print(f"Reply released to {store.released_path(claim_id)}")
    else:
        print("Reply held back; ask the agent to revise it, e.g. "
              f"python -m expense_app ask {claim_id} \"{note}\"")
    return 0


def print_run(summary: dict[str, Any]) -> None:
    print(f"\n  [{summary['subtype']}] turns={summary['turns']}  tool calls={len(summary['tools'])}  "
          f"cost=${summary['cost_usd']:.4f}  model={','.join(summary['models']) or config.MODEL}")


# ------------------------------------------------------------------ agent runs
async def _run(claim_id: str, prompts: list[str], resume: str | None, show_answer: bool) -> float:
    from .agent import ReviewSession      # imported lazily: offline commands need no SDK session
    async with ReviewSession(claim_id, resume=resume) as s:
        for prompt in prompts:
            if resume or show_answer:
                print(f"\n>>> {prompt}")
            summary = await s.ask(prompt)
            if show_answer and summary["text"]:
                print("\n<<< " + summary["text"].replace("\n", "\n    "))
            print_run(summary)
        return s.total_cost


def cmd_review(claim_id: str, force: bool = False) -> int:
    from .agent import review_prompt
    claim = store.load_claim(claim_id)
    if claim is None:
        print(f"No claim {claim_id!r} in the inbox. Try: python -m expense_app list")
        return 1
    if store.load_decision(claim_id) and not force:
        print(f"{claim_id} is already reviewed. Use `ask {claim_id} \"...\"` for follow-ups, "
              f"or `review {claim_id} --force` to review it again from scratch.")
        print_decision(store.load_decision(claim_id))
        return 0
    print(f"Reviewing {claim_id} ({claim['employee']}, {claim['amount']} {claim['currency']}, {claim['vendor']})")
    print("  agent tool calls:")
    try:
        asyncio.run(_run(claim_id, [review_prompt(claim_id, fresh=force)], resume=None, show_answer=False))
    except Exception as exc:          # surface SDK / budget errors without a traceback wall
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        return 1
    d = store.load_decision(claim_id)
    print_decision(d)
    return 0 if d else 2


def cmd_ask(claim_id: str, questions: list[str]) -> int:
    session = store.get_session(claim_id)
    if not store.load_claim(claim_id):
        print(f"No claim {claim_id!r} in the inbox.")
        return 1
    if not session:
        print(f"{claim_id} has not been reviewed yet, so there is no conversation to continue. "
              f"Run: python -m expense_app review {claim_id}")
        return 1
    before = (store.load_decision(claim_id) or {}).get("revision")
    print(f"Resuming the conversation for {claim_id} (session {session[:8]}...)")
    try:
        asyncio.run(_run(claim_id, questions, resume=session, show_answer=True))
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        return 1
    after = store.load_decision(claim_id)
    if after and after.get("revision") != before:
        print(f"  Decision updated: revision {before} -> {after['revision']}")
        print_decision(after)
    return 0


def cmd_chat(claim_id: str) -> int:
    print(f"Follow-up chat about {claim_id}. Type 'exit' to stop, 'show' for the saved decision.")
    while True:
        try:
            q = input(f"\n{claim_id}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if q.lower() in ("exit", "quit"):
            return 0
        if q.lower() == "show":
            print_decision(store.load_decision(claim_id))
        elif q:
            cmd_ask(claim_id, [q])


def cmd_review_all(limit: int | None) -> int:
    pending = store.list_claims("pending")[: limit or None]
    if not pending:
        print("No pending claims.")
        return 0
    rows = []
    for c in pending:
        before = _runs_cost()
        cmd_review(c["id"])
        d = store.load_decision(c["id"]) or {}
        rows.append((c["id"], c["employee"], d.get("decision", "ERROR"), d.get("approved_amount_usd", 0.0),
                     d.get("escalate_to", "-"), ", ".join(d.get("flags", [])), _runs_cost() - before))
    print(f"\n{'claim':<10} {'employee':<16} {'decision':<11} {'amount':>9}  {'escalate':<18} {'cost':>7}  flags")
    for cid, emp, dec, amt, esc, flags, cost in rows:
        print(f"{cid:<10} {emp:<16} {dec:<11} {amt:>9.2f}  {esc:<18} ${cost:>6.4f}  {flags}")
    print(f"total cost ${sum(r[-1] for r in rows):.4f} for {len(rows)} claims")
    return 0


def _runs_cost() -> float:
    if not config.RUNS_FILE.exists():
        return 0.0
    return sum(json.loads(line).get("cost_usd", 0.0) for line in config.RUNS_FILE.read_text("utf-8").splitlines()
               if line.strip())


# ------------------------------------------------------------------ offline commands
def cmd_submit(args: argparse.Namespace) -> int:
    fields = {k: getattr(args, k) for k, _ in FIELDS}
    interactive = all(v is None for v in fields.values())
    while True:
        if interactive:
            print("Enter the claim (Ctrl+C to cancel).")
            for key, label in FIELDS:
                default = fields.get(key)
                shown = f" [{default}]" if default not in (None, "") else ""
                fields[key] = input(f"  {label}{shown}: ").strip() or (default or "")
        try:
            path = store.save_claim(fields)
        except ValueError as exc:
            print(f"Not saved: {exc}")
            if not interactive:
                return 1
            continue
        claim = json.loads(path.read_text(encoding="utf-8"))
        print(f"Saved {claim['id']} -> {path.relative_to(config.WORKSPACE) if path.is_relative_to(config.WORKSPACE) else path}")
        if args.review:
            return cmd_review(claim["id"])
        print(f"Review it with: python -m expense_app review {claim['id']}")
        return 0


def cmd_list() -> int:
    claims = store.list_claims("all")
    if not claims:
        print("Inbox is empty. Add claims with `submit` or `seed`.")
    for c in claims:
        d = store.load_decision(c["id"]) or {}
        result = (f"{d['decision']} {d['approved_amount_usd']:.2f} "
                  f"[{(d.get('approval') or {}).get('status', 'pending_review')}]") if d else ""
        print(f"{c['id']:<10} {c['status']:<9} {c['employee']:<16} {c['expense_date']}  "
              f"{c['amount']:>9.2f} {c['currency']}  {c['vendor'][:24]:<24} {result}")
    return 0


def cmd_trace(claim_id: str) -> int:
    """Tool calls the agent made for a claim, from the audit log (PreToolUse/PostToolUse hooks)."""
    if not config.AUDIT_FILE.exists():
        print("No audit log yet.")
        return 1
    sessions = set()
    if config.RUNS_FILE.exists():
        for line in config.RUNS_FILE.read_text("utf-8").splitlines():
            r = json.loads(line)
            if r.get("claim_id") == claim_id and r.get("session_id"):
                sessions.add(r["session_id"])
    sid = store.get_session(claim_id)
    if sid:
        sessions.add(sid)
    for line in config.AUDIT_FILE.read_text("utf-8").splitlines():
        e = json.loads(line)
        if e.get("session") in sessions or (e.get("event") == "denied" and e.get("claim_id") == claim_id):
            what = e.get("input") or e.get("result") or "; ".join(e.get("problems", []))
            print(f"{e['at']}  {e['event']:<6} {str(e.get('tool')).replace('mcp__', ''):<34} {what[:160]}")
    return 0


def cmd_check() -> int:
    """Re-run the code-enforced policy checks on every saved decision (a self-scoring script)."""
    bad = 0
    for c in store.list_claims("reviewed"):
        d = store.load_decision(c["id"])
        problems = policy.decision_problems(d, c)
        status = "OK " if not problems else "FAIL"
        bad += bool(problems)
        print(f"{status} {c['id']}  {d['decision']:<10} {d['approved_amount_usd']:>8.2f}  {d['escalate_to']}")
        for p in problems:
            print(f"     - {p}")
    print(f"\n{bad} decision(s) with problems.")
    return 1 if bad else 0


def cmd_export(ids: list[str] | None) -> int:
    config.RESULTS_DIR.mkdir(exist_ok=True)
    rows = []
    for c in store.list_claims("reviewed"):
        if ids and c["id"] not in ids:
            continue
        cid = c["id"]
        for suffix in (".json", ".reply.md"):
            shutil.copy2(config.OUTBOX / f"{cid}{suffix}", config.RESULTS_DIR / f"{cid}{suffix}")
        d = store.load_decision(cid)
        rows.append(f"| {cid} | {c['employee']} | {d['decision']} | {d['approved_amount_usd']:.2f} | "
                    f"{', '.join(d['policy_refs'])} | {', '.join(d['flags']) or '-'} | {d['escalate_to']} |")
    table = ("# Results\n\nProduced by `python -m expense_app review-all` and exported with "
             "`python -m expense_app export`. Each claim has a `.json` decision (all seven policy fields) "
             "and a `.reply.md` with the draft reply.\n\n"
             "| claim | employee | decision | approved_amount_usd | policy_refs | flags | escalate_to |\n"
             "|---|---|---|---:|---|---|---|\n" + "\n".join(rows) + "\n")
    (config.RESULTS_DIR / "summary.md").write_text(table, encoding="utf-8")
    print(f"Exported {len(rows)} decisions to {config.RESULTS_DIR}")
    return 0


# ------------------------------------------------------------------ entry point
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m expense_app", description="Expense claim review assistant")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit", help="enter a claim; prompts for any field not given as an option")
    for key, label in FIELDS:
        s.add_argument(f"--{key.replace('_', '-')}", dest=key, help=label)
    s.add_argument("--review", action="store_true", help="review it straight away")
    sub.add_parser("seed", help="copy data/claims.json into the inbox")
    sub.add_parser("list", help="list claims and status")
    r = sub.add_parser("review", help="review one claim with the agent")
    r.add_argument("claim_id")
    r.add_argument("--force", action="store_true", help="re-review an already reviewed claim from scratch")
    ra = sub.add_parser("review-all", help="review all pending claims and print a summary with cost")
    ra.add_argument("--limit", type=int)
    a = sub.add_parser("ask", help="ask a follow-up question about a reviewed claim")
    a.add_argument("claim_id")
    a.add_argument("question", nargs="+")
    c = sub.add_parser("chat", help="interactive follow-ups about a reviewed claim")
    c.add_argument("claim_id")
    sh = sub.add_parser("show", help="show the saved decision")
    sh.add_argument("claim_id")
    t = sub.add_parser("trace", help="show the audited tool calls for a claim")
    t.add_argument("claim_id")
    sub.add_parser("check", help="re-verify saved decisions against the policy code")
    sc = sub.add_parser("score", help="score decisions against tests/expected_samples.json")
    sc.add_argument("--source", choices=["results", "outbox"], default="results")
    ap_ = sub.add_parser("approve", help="a person approves the reply for the current revision (releases it)")
    ap_.add_argument("claim_id")
    ap_.add_argument("--by", required=True, help="approver's name")
    ap_.add_argument("--note", default="")
    rc = sub.add_parser("request-changes", help="a person holds the reply back and says what to change")
    rc.add_argument("claim_id")
    rc.add_argument("--by", required=True, help="reviewer's name")
    rc.add_argument("--note", required=True, help="what needs to change")
    e = sub.add_parser("export", help="copy decisions into results/")
    e.add_argument("ids", nargs="*")
    args = ap.parse_args(argv)

    config.ensure_dirs()
    if args.cmd == "submit":
        return cmd_submit(args)
    if args.cmd == "seed":
        added = store.seed_samples()
        print(f"Added {len(added)} sample claims: {', '.join(added) or '(all already present)'}")
        return 0
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "review":
        return cmd_review(args.claim_id.upper(), args.force)
    if args.cmd == "review-all":
        return cmd_review_all(args.limit)
    if args.cmd == "ask":
        return cmd_ask(args.claim_id.upper(), [" ".join(args.question)])
    if args.cmd == "chat":
        return cmd_chat(args.claim_id.upper())
    if args.cmd == "show":
        d = store.load_decision(args.claim_id.upper())
        print_decision(d)
        return 0 if d else 1
    if args.cmd == "trace":
        return cmd_trace(args.claim_id.upper())
    if args.cmd == "check":
        return cmd_check()
    if args.cmd == "score":
        from . import scoring
        return scoring.run(args.source)
    if args.cmd == "approve":
        return cmd_approval(args.claim_id.upper(), "approved", args.by, args.note)
    if args.cmd == "request-changes":
        return cmd_approval(args.claim_id.upper(), "changes_requested", args.by, args.note)
    if args.cmd == "export":
        return cmd_export([i.upper() for i in args.ids] or None)
    return 2


if __name__ == "__main__":
    sys.exit(main())
