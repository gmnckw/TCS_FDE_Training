"""IN-PROCESS MCP server ("expense"): the review tools, served from this Python process.

Design rule: the model judges, code computes. Anything with one right answer
(currency conversion, day counts, duplicate and split matching, pre-approval
validity, per-person and per-night limits, the monthly cap) is a tool here, so
the model never does the arithmetic itself.

The tools that take a claim_id read the claim from the inbox themselves. The model
cannot hand them a different amount or date than the one the employee submitted.

Every tool returns a helpful error (is_error=True) instead of raising, so the
agent can recover. The agent sees them as mcp__expense__<name>.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from claude_agent_sdk import ToolAnnotations, create_sdk_mcp_server, tool

from . import config, policy, store

READ_ONLY = ToolAnnotations(readOnlyHint=True)


def ok(payload: Any) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
    return {"content": [{"type": "text", "text": text}]}


def err(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Error: {message}"}], "is_error": True}


def _claim_or_error(claim_id: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not store.valid_claim_id(claim_id):
        return None, err(f"{claim_id!r} is not a valid claim id (expected like CLM-3001).")
    claim = store.load_claim(claim_id)
    if claim is None:
        return None, err(f"no claim {claim_id} in the inbox. Use list_pending_claims to see what exists.")
    return claim, None


# ------------------------------------------------------------------ policy articles
def _articles() -> dict[str, tuple[str, str]]:
    """article id -> (file name, text), including EX-200 itself."""
    out = {}
    for path in [config.POLICY_FILE] + sorted(config.KB_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.search(r"\*\*Article ID:\*\*\s*(EX-\d+)", text)
        if m:
            out[m.group(1)] = (path.name, text)
    return out


@tool("search_policy",
      "Search the expense policy articles (EX-200 to EX-206) by keyword and return the best "
      "matching articles in full. Pass 2-6 keywords about the expense, e.g. 'hotel per night "
      "London' or 'alcohol meal attendees'. Call this before deciding: cite only articles you read.",
      {"query": str}, annotations=READ_ONLY)
async def search_policy(args: dict[str, Any]) -> dict[str, Any]:
    terms = [t for t in re.split(r"[^a-z0-9]+", str(args.get("query", "")).lower()) if len(t) > 2]
    if not terms:
        return err("empty query. Pass keywords such as 'equipment pre-approval threshold'.")
    hits = []
    for aid, (name, text) in _articles().items():
        low = text.lower()
        score = sum(low.count(t) for t in terms)
        if score:
            hits.append((score, aid, name, text))
    if not hits:
        return ok(f"No article matches {terms}. Available: {', '.join(_articles())}. "
                  "Use get_policy_article with an id.")
    hits.sort(key=lambda h: (-h[0], h[1]))
    return ok("\n\n".join(f"=== {aid} ({name}, relevance {score}) ===\n{text}"
                          for score, aid, name, text in hits[:2]))


@tool("get_policy_article",
      "Return one policy article in full by id: EX-200 (decision framework), EX-201 meals, EX-202 "
      "travel, EX-203 equipment and software, EX-204 documentation and timing, EX-205 prohibited "
      "items, duplicates, splits and caps, EX-206 currency and pre-approvals.",
      {"article_id": str}, annotations=READ_ONLY)
async def get_policy_article(args: dict[str, Any]) -> dict[str, Any]:
    aid = str(args.get("article_id", "")).strip().upper()
    arts = _articles()
    if aid not in arts:
        return err(f"no article {aid!r}. Valid ids: {', '.join(arts)}.")
    return ok(arts[aid][1])


# ------------------------------------------------------------------ employee record
@tool("lookup_employee",
      "Look up ONE employee's own record by full name: employee id, grade, manager, monthly cap, "
      "month-to-date approved spend and their pre-approvals. Use the name from the claim. Never "
      "returns other employees' data.",
      {"employee_name": str}, annotations=READ_ONLY)
async def lookup_employee(args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("employee_name", "")).strip()
    if not name:
        return err("employee_name is empty.")
    found = policy.find_employee(name)
    if not found:
        return err(f"no employee named {name!r} in the directory. Do not guess a record: the claim cannot "
                   "be checked against a cap or pre-approvals. Decide on that basis (it must not be approved).")
    key, rec = found
    return ok({"name": key, **rec})


# ------------------------------------------------------------------ duplicates and splits
@tool("find_related_claims",
      "Check a claim against the employee's earlier claims in past_claims.json (EX-205): exact "
      "duplicates (same employee, vendor, expense date, amount and currency), other claims at the "
      "same vendor on the same day, the split-purchase test, and the vendor-day total in USD used "
      "for the EX-203 equipment thresholds. Reads the claim itself from the inbox.",
      {"claim_id": str}, annotations=READ_ONLY)
async def find_related_claims(args: dict[str, Any]) -> dict[str, Any]:
    claim, e = _claim_or_error(args.get("claim_id"))
    if e:
        return e
    try:
        # Duplicates are compared in the claim's own currency (EX-206), so this never needs a rate.
        dups = policy.find_duplicates(claim)
        same_day = policy.same_vendor_same_day(claim)
    except policy.PolicyDataError as exc:
        return err(str(exc))
    out: dict[str, Any] = {"duplicates": dups, "is_duplicate": bool(dups), "same_vendor_same_day_claims": same_day}
    try:
        own_usd = policy.to_usd(claim["amount"], claim["currency"])
        others_usd = sum((policy.to_usd(p["amount"], p["currency"]) for p in same_day
                          if p["id"] not in {d["id"] for d in dups}), Decimal("0"))
        vendor_day_total = own_usd + others_usd
        out.update(split_purchase=policy.split_purchase_analysis(claim),
                   vendor_day_total_usd=float(vendor_day_total),
                   equipment_tier_for_vendor_day_total=policy.equipment_tier(vendor_day_total))
    except policy.PolicyDataError as exc:
        # The duplicate result above still stands; only the USD-based checks are unavailable.
        out.update(split_purchase=None, vendor_day_total_usd=None, equipment_tier_for_vendor_day_total=None,
                   usd_checks_unavailable=str(exc))
    out["note"] = "Only this employee's own claims are listed. Equipment tiers apply only if the item is equipment."
    return ok(out)


@tool("check_filing_deadline",
      "Compute the number of days between the claim's expense_date and submitted_at, and whether it "
      "is late under EX-204 (more than 60 days). Reads the dates from the claim file.",
      {"claim_id": str}, annotations=READ_ONLY)
async def check_filing_deadline(args: dict[str, Any]) -> dict[str, Any]:
    claim, e = _claim_or_error(args.get("claim_id"))
    if e:
        return e
    try:
        gap = policy.filing_gap_days(claim["expense_date"], claim["submitted_at"])
    except policy.PolicyDataError as exc:
        return err(str(exc))
    return ok({"expense_date": claim["expense_date"], "submitted_at": claim["submitted_at"],
               "days_between": gap, "limit_days": policy.LATE_AFTER_DAYS,
               "late": gap > policy.LATE_AFTER_DAYS})


# ------------------------------------------------------------------ money
@tool("convert_to_usd",
      "Convert an amount to USD with the fixed quarterly rates in fx_rates.json, rounded to the cent "
      "(EX-206). Use this for any part-amount (e.g. an itemised line in EUR); never convert in your head.",
      {"type": "object", "properties": {"amount": {"type": "number"}, "currency": {"type": "string"}},
       "required": ["amount", "currency"]}, annotations=READ_ONLY)
async def convert_to_usd(args: dict[str, Any]) -> dict[str, Any]:
    try:
        usd = policy.to_usd(args.get("amount"), args.get("currency", ""))
    except (policy.PolicyDataError, ArithmeticError) as exc:
        return err(str(exc))
    rate = policy.fx_rates()[str(args["currency"]).strip().upper()]
    return ok({"amount": args["amount"], "currency": str(args["currency"]).upper(),
               "rate": float(rate), "usd": float(usd)})


@tool("check_preapproval",
      "Validate a pre-approval for a claim against the EMPLOYEE'S OWN record (EX-206): it must be "
      "listed on their record, have the required type, and have max_usd >= the USD amount. Use the "
      "type the expense actually needs: 'equipment' (EX-203, $150-$1,000), 'client_entertainment' "
      "(EX-201, over $200) or 'travel_business_class' (EX-202). amount_usd defaults to the whole "
      "claim in USD. The number written on the claim is checked, not trusted.",
      {"type": "object", "properties": {
          "claim_id": {"type": "string"},
          "required_type": {"type": "string", "enum": config.PREAPPROVAL_TYPES},
          "amount_usd": {"type": "number", "description": "USD amount the pre-approval must cover"}},
       "required": ["claim_id", "required_type"]}, annotations=READ_ONLY)
async def check_preapproval(args: dict[str, Any]) -> dict[str, Any]:
    claim, e = _claim_or_error(args.get("claim_id"))
    if e:
        return e
    try:
        amount = policy.money(args["amount_usd"]) if args.get("amount_usd") is not None else \
            policy.to_usd(claim["amount"], claim["currency"])
        return ok(policy.check_preapproval(claim, str(args.get("required_type")), amount))
    except policy.PolicyDataError as exc:
        return err(str(exc))


@tool("calculate_reimbursable",
      "EX-200 step 6 for a claim: convert to USD, subtract non-reimbursable items, then apply the "
      "category cap. rule is one of: 'meal' (needs attendees, employee included; $75/person), "
      "'hotel' (needs nights and city; $220/night or $320 in London, New York, San Francisco, "
      "Singapore, Zurich), 'per_diem' (needs days; $60/full day away overnight), 'parking' (needs "
      "days; $25/day), 'client_entertainment' or 'travel_business_class' (capped at the valid "
      "pre-approval), 'actual_cost' (no cap). excluded_amount is in the CLAIM's currency: itemised "
      "alcohol, a meal already covered by the per diem, or any other non-reimbursable part.",
      {"type": "object", "properties": {
          "claim_id": {"type": "string"},
          "rule": {"type": "string", "enum": ["meal", "hotel", "per_diem", "parking", "client_entertainment",
                                             "travel_business_class", "actual_cost"]},
          "excluded_amount": {"type": "number", "description": "In the claim's currency. Default 0."},
          "attendees": {"type": "integer", "description": "meal: number of people including the employee"},
          "nights": {"type": "integer", "description": "hotel: number of nights"},
          "city": {"type": "string", "description": "hotel: city of the hotel"},
          "days": {"type": "integer", "description": "per_diem or parking: number of days"}},
       "required": ["claim_id", "rule"]}, annotations=READ_ONLY)
async def calculate_reimbursable(args: dict[str, Any]) -> dict[str, Any]:
    claim, e = _claim_or_error(args.get("claim_id"))
    if e:
        return e
    try:
        return ok(policy.calculate_reimbursable(
            claim, str(args.get("rule")), excluded_amount=args.get("excluded_amount") or 0,
            attendees=args.get("attendees"), nights=args.get("nights"), city=args.get("city"),
            days=args.get("days")))
    except (policy.PolicyDataError, ArithmeticError, TypeError) as exc:
        return err(str(exc))


@tool("check_monthly_cap",
      "EX-205 check 7: would month_to_date_usd plus this amount exceed the employee's monthly cap? "
      "Pass the reimbursable amount from calculate_reimbursable (step 6), not the claimed amount.",
      {"type": "object", "properties": {"claim_id": {"type": "string"}, "amount_usd": {"type": "number"}},
       "required": ["claim_id", "amount_usd"]}, annotations=READ_ONLY)
async def check_monthly_cap(args: dict[str, Any]) -> dict[str, Any]:
    claim, e = _claim_or_error(args.get("claim_id"))
    if e:
        return e
    try:
        return ok(policy.monthly_cap_check(claim["employee"], policy.money(args.get("amount_usd"))))
    except policy.PolicyDataError as exc:
        return err(str(exc))


# ------------------------------------------------------------------ save
SAVE_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_id": {"type": "string"},
        "decision": {"type": "string", "enum": config.DECISIONS},
        "approved_amount_usd": {"type": "number", "description": "approve: recommended USD amount; otherwise 0"},
        "policy_refs": {"type": "array", "items": {"type": "string", "enum": config.ARTICLE_IDS[1:]},
                        "description": "Ids of the articles whose rules decided the outcome or amount"},
        "flags": {"type": "array", "items": {"type": "string", "enum": config.FLAGS}},
        "reply_to_employee": {"type": "string",
                              "description": "Draft message to the employee, following the EX-200 reply rules"},
        "escalate_to": {"type": "string", "enum": config.ESCALATION_TARGETS},
        "escalation_reason": {"type": "string", "description": "One line; required when escalate_to is not none"},
        "reimbursable_before_cap_usd": {"type": "number",
                                        "description": "Step-6 amount; required when escalating for the monthly cap"},
        "reviewer_notes": {"type": "string",
                           "description": "For the finance reviewer: which check settled the claim, and the sums"},
    },
    "required": ["claim_id", "decision", "approved_amount_usd", "policy_refs", "flags",
                 "reply_to_employee", "escalate_to", "reviewer_notes"],
}


@tool("save_decision",
      "Save the recommended decision for a claim to the outbox (all seven EX-200 fields plus reviewer "
      "notes). Call once the checks are done. Saving again overwrites it with a new revision; do that "
      "when a follow-up changes the decision or the reply. A guard re-checks the decision against "
      "the policy data and the reply hard stops; if it refuses, fix what it lists and call again.",
      SAVE_SCHEMA)
async def save_decision(args: dict[str, Any]) -> dict[str, Any]:
    claim, e = _claim_or_error(args.get("claim_id"))
    if e:
        return e
    # Defence in depth: the PreToolUse hook runs the same checks first.
    problems = policy.decision_problems(args, claim)
    if problems:
        return err("decision not saved:\n- " + "\n- ".join(problems))
    record = {
        "claim_id": claim["id"],
        "decision": args["decision"],
        "approved_amount_usd": float(policy.money(args["approved_amount_usd"])),
        "policy_refs": sorted(set(args["policy_refs"])),
        "flags": sorted(set(args["flags"])),
        "reply_to_employee": args["reply_to_employee"].strip(),
        "escalate_to": args["escalate_to"],
        "escalation_reason": (args.get("escalation_reason") or "").strip() if args["escalate_to"] != "none" else "",
        "reimbursable_before_cap_usd": args.get("reimbursable_before_cap_usd"),
        "reviewer_notes": args.get("reviewer_notes", "").strip(),
        "employee": claim["employee"],
        "model": config.MODEL,
    }
    path = store.write_decision(record)
    saved = store.load_decision(claim["id"])
    return ok(f"Saved {claim['id']} revision {saved['revision']} -> outbox/{path.name}")


ALL_TOOLS = [search_policy, get_policy_article, lookup_employee, find_related_claims,
             check_filing_deadline, convert_to_usd, check_preapproval, calculate_reimbursable,
             check_monthly_cap, save_decision]


def build_expense_server():
    """A fresh server instance per agent session."""
    return create_sdk_mcp_server(name="expense", version="1.0.0", tools=ALL_TOOLS)


# Full tool names as the agent sees them: mcp__<server key>__<tool name>.
EXPENSE_TOOLS = [f"mcp__expense__{t.name}" for t in ALL_TOOLS]
CLAIMS_TOOLS = [f"mcp__claims__{n}" for n in ("list_pending_claims", "read_claim", "get_saved_decision")]
ALLOWED_TOOLS = EXPENSE_TOOLS + CLAIMS_TOOLS
SAVE_TOOL = "mcp__expense__save_decision"
