import csv
import json
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = BASE_DIR / "datasets" / "legacy_claims_export.csv"
OUTPUT_JSON = BASE_DIR / "datasets" / "cleaned_claims_payload.json"

def normalize_date(raw_dt: str) -> str:
    raw_dt = raw_dt.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw_dt, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw_dt

def normalize_policy_id(raw_pol: str):
    if not raw_pol or not raw_pol.strip():
        return None
    cleaned = raw_pol.strip().upper().replace(" ", "")
    match = re.match(r"^POL-?(\d{4})$", cleaned)
    if match:
        return f"POL-{match.group(1)}"
    return None

def triage_claim(row: dict, seen_keys: set) -> dict:
    claim_id = row["claim_id"].strip()
    claimant = row["claimant_name"].strip()
    service_date = normalize_date(row["service_dt"])
    amount = float(row["billed_amt"])
    policy_id = normalize_policy_id(row["policy_ref"])
    note = row["adjuster_note"].lower()

    # Gate 1: Missing or invalid policy ID
    if not policy_id:
        return {
            "claim_id": claim_id,
            "policy_id": None,
            "claimant_name": claimant,
            "service_date": service_date,
            "amount_inr": amount,
            "normalized_status": "INTAKE_ERROR",
            "routing_queue": "INTAKE_REMEDIATION",
            "triage_reason": "Missing or invalid policy_ref identifier"
        }

    # Gate 2: Duplicate detection
    dedup_key = (policy_id, claimant.lower(), service_date, round(amount, 2))
    if dedup_key in seen_keys:
        return {
            "claim_id": claim_id,
            "policy_id": policy_id,
            "claimant_name": claimant,
            "service_date": service_date,
            "amount_inr": amount,
            "normalized_status": "DUPLICATE",
            "routing_queue": "DEDUP_ARCHIVE",
            "triage_reason": "Composite match on policy, claimant, date, and amount"
        }
    seen_keys.add(dedup_key)

    # Gate 3: Policy tier rules
    if policy_id == "POL-8821":  # Silver
        is_inpatient = "inpatient" in note
        has_discharge = "discharge summary attached" in note
        if is_inpatient and not has_discharge:
            status, queue, reason = "AWAITING_DOCS", "DOCS_FOLLOWUP_QUEUE", "Silver inpatient claim missing discharge summary"
        elif not is_inpatient and amount >= 25000:
            status, queue, reason = "SENIOR_REVIEW", "SENIOR_ADJUSTER_QUEUE", "Silver outpatient claim >= INR 25,000"
        else:
            status, queue, reason = "READY_FOR_PAYOUT", "AUTO_PAYOUT_BATCH", "Silver policy criteria satisfied"

    elif policy_id == "POL-9044":  # Gold
        has_preauth = bool(re.search(r"pa-\d+", note))
        if amount > 100000:
            status, queue, reason = "SENIOR_REVIEW", "SENIOR_ADJUSTER_QUEUE", "Gold claim exceeds INR 1,00,000 threshold"
        elif not has_preauth:
            status, queue, reason = "AWAITING_DOCS", "DOCS_FOLLOWUP_QUEUE", "Gold claim missing pre-authorization ID"
        elif amount <= 50000:
            status, queue, reason = "READY_FOR_PAYOUT", "AUTO_PAYOUT_BATCH", "Gold claim <= INR 50,000 with pre-auth"
        else:
            status, queue, reason = "SENIOR_REVIEW", "SENIOR_ADJUSTER_QUEUE", "Gold claim between 50k and 100k review"

    elif policy_id == "POL-7712":  # Bronze
        if "out-of-network" in note or "out of network" in note or "mismatch" in note:
            status, queue, reason = "SIU_HOLD", "SIU_REVIEW", "Bronze policy out-of-network provider violation"
        else:
            status, queue, reason = "READY_FOR_PAYOUT", "AUTO_PAYOUT_BATCH", "Bronze in-network claim verified"
    else:
        status, queue, reason = "INTAKE_ERROR", "INTAKE_REMEDIATION", f"Unrecognized policy tier: {policy_id}"

    return {
        "claim_id": claim_id,
        "policy_id": policy_id,
        "claimant_name": claimant,
        "service_date": service_date,
        "amount_inr": amount,
        "normalized_status": status,
        "routing_queue": queue,
        "triage_reason": reason
    }

def main():
    seen_keys = set()
    results = []
    with open(INPUT_CSV, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(triage_claim(row, seen_keys))

    with open(OUTPUT_JSON, mode="w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Processed {len(results)} claims -> {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
