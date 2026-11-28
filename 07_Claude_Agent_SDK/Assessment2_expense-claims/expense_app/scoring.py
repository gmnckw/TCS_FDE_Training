"""Scoring script: compare saved decisions with expected outcomes, field by field.

    python -m expense_app score                     # scores results/ against tests/expected_samples.json
    python -m expense_app score --source outbox     # scores the live outbox instead

Each claim gets five field scores, mirroring the assessment's "partial credit per field":

    decision      1 if equal
    amount        1 if equal to the cent
    escalate_to   1 if equal
    flags         Jaccard similarity of the two flag sets (1.0 when both are empty)
    policy_refs   share of the expected articles that were cited (extra ones are listed, not penalised)

The reply is also re-checked against the hard stops (policy.reply_problems), reported as
a separate pass/fail column: a hard-stop breach is a defect whatever the decision.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config, policy, store

FIELDS = ("decision", "amount", "escalate_to", "flags", "policy_refs")


def load_expected(path: Path = config.EXPECTED_FILE) -> dict[str, dict[str, Any]]:
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def _same_cents(a: Any, b: Any) -> bool:
    try:
        return policy.money(a) == policy.money(b)
    except policy.PolicyDataError:
        return False


def score_one(got: dict[str, Any], want: dict[str, Any], claim: dict[str, Any] | None) -> dict[str, Any]:
    gf, wf = set(got.get("flags") or []), set(want.get("flags") or [])
    gr, wr = set(got.get("policy_refs") or []), set(want.get("policy_refs") or [])
    s = {
        "decision": float(got.get("decision") == want["decision"]),
        "amount": float(_same_cents(got.get("approved_amount_usd"), want["approved_amount_usd"])),
        "escalate_to": float(got.get("escalate_to") == want["escalate_to"]),
        "flags": 1.0 if not (gf | wf) else len(gf & wf) / len(gf | wf),
        "policy_refs": 1.0 if not wr else len(gr & wr) / len(wr),
    }
    problems = policy.reply_problems(got.get("reply_to_employee", ""), claim) if claim else ["claim file missing"]
    diffs = []
    if s["decision"] < 1:
        diffs.append(f"decision {got.get('decision')} != {want['decision']}")
    if s["amount"] < 1:
        diffs.append(f"amount {got.get('approved_amount_usd')} != {want['approved_amount_usd']}")
    if s["escalate_to"] < 1:
        diffs.append(f"escalate_to {got.get('escalate_to')} != {want['escalate_to']}")
    if gf - wf:
        diffs.append(f"extra flags {sorted(gf - wf)}")
    if wf - gf:
        diffs.append(f"missing flags {sorted(wf - gf)}")
    if wr - gr:
        diffs.append(f"missing refs {sorted(wr - gr)}")
    return {"fields": s, "total": sum(s.values()) / len(s), "reply_ok": not problems,
            "reply_problems": problems, "diffs": diffs, "extra_refs": sorted(gr - wr)}


def load_decision_from(source: str, claim_id: str) -> dict[str, Any] | None:
    if source == "outbox":
        return store.load_decision(claim_id)
    p = config.RESULTS_DIR / f"{claim_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def sample_claim(claim_id: str) -> dict[str, Any] | None:
    """The claim from the inbox, or straight from data/claims.json if it was never seeded."""
    c = store.load_claim(claim_id)
    if c:
        return c
    return next((s for s in json.loads(config.SAMPLE_CLAIMS_FILE.read_text(encoding="utf-8"))
                 if s["id"] == claim_id), None)


def run(source: str = "results") -> int:
    expected = load_expected()
    rows, totals, field_sums = [], [], {f: 0.0 for f in FIELDS}
    print(f"Scoring {source}/ against {config.EXPECTED_FILE.relative_to(config.ROOT)}\n")
    print(f"{'claim':<10} {'decision':>8} {'amount':>7} {'escal.':>7} {'flags':>6} {'refs':>6} "
          f"{'reply':>6} {'score':>6}")
    for cid, want in expected.items():
        got = load_decision_from(source, cid)
        if got is None:
            print(f"{cid:<10} {'(no decision saved)':>44}  0.00")
            totals.append(0.0)
            continue
        r = score_one(got, want, sample_claim(cid))
        f = r["fields"]
        for k in FIELDS:
            field_sums[k] += f[k]
        totals.append(r["total"])
        print(f"{cid:<10} {f['decision']:>8.0f} {f['amount']:>7.0f} {f['escalate_to']:>7.0f} {f['flags']:>6.2f} "
              f"{f['policy_refs']:>6.2f} {'ok' if r['reply_ok'] else 'FAIL':>6} {r['total']:>6.2f}")
        rows.append((cid, r))
    n = len(expected)
    print("-" * 62)
    print(f"{'mean':<10} {field_sums['decision'] / n:>8.2f} {field_sums['amount'] / n:>7.2f} "
          f"{field_sums['escalate_to'] / n:>7.2f} {field_sums['flags'] / n:>6.2f} {field_sums['policy_refs'] / n:>6.2f} "
          f"{'':>6} {sum(totals) / n:>6.2f}")
    notes = [(cid, r) for cid, r in rows if r["diffs"] or r["extra_refs"] or not r["reply_ok"]]
    if notes:
        print("\nDifferences:")
        for cid, r in notes:
            for d in r["diffs"]:
                print(f"  {cid}: {d}")
            if r["extra_refs"]:
                print(f"  {cid}: also cited {r['extra_refs']} (not penalised)")
            for p in r["reply_problems"]:
                print(f"  {cid}: REPLY {p}")
    hard_fail = sum(1 for _, r in rows if not r["reply_ok"])
    print(f"\nOverall {sum(totals) / n:.1%} across {n} claims; {hard_fail} reply hard-stop failure(s).")
    return 0 if hard_fail == 0 else 1
