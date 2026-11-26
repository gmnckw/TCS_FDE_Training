import csv
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PRED_JSON = BASE_DIR / "datasets" / "cleaned_claims_payload.json"
GOLDEN_CSV = BASE_DIR / "datasets" / "golden_ground_truth.csv"

def main():
    if not PRED_JSON.exists():
        raise FileNotFoundError("Run reference_triage_pipeline.py first to generate cleaned_claims_payload.json")

    with open(PRED_JSON, "r", encoding="utf-8") as f:
        preds = {item["claim_id"]: item for item in json.load(f)}

    total = 0
    exact_matches = 0
    false_auto_approvals = 0
    actual_dups = 0
    caught_dups = 0

    print("=== MERIDIAN FDE PIPELINE EVALUATION REPORT ===")
    with open(GOLDEN_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            total += 1
            cid = row["claim_id"]
            exp_status = row["expected_status"]
            exp_queue = row["expected_queue"]
            pred = preds[cid]

            if exp_status == "DUPLICATE":
                actual_dups += 1
                if pred["normalized_status"] == "DUPLICATE":
                    caught_dups += 1

            if pred["normalized_status"] == "READY_FOR_PAYOUT" and exp_status != "READY_FOR_PAYOUT":
                false_auto_approvals += 1

            if pred["normalized_status"] == exp_status and pred["routing_queue"] == exp_queue:
                exact_matches += 1
            else:
                print(f"[MISMATCH] {cid}: expected ({exp_status}, {exp_queue}) vs got ({pred['normalized_status']}, {pred['routing_queue']})")

    accuracy = (exact_matches / total) * 100
    dup_recall = (caught_dups / actual_dups) * 100 if actual_dups else 100.0

    print(f"Total Evaluated Claims : {total}")
    print(f"Routing Accuracy       : {accuracy:.1f}% ({exact_matches}/{total})")
    print(f"False Auto-Approvals   : {false_auto_approvals} (Target: 0)")
    print(f"Duplicate Recall       : {dup_recall:.1f}% ({caught_dups}/{actual_dups})")

if __name__ == "__main__":
    main()
