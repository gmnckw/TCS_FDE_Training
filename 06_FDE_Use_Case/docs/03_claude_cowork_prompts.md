# End-to-End Claude Cowork Prompts (Run in Sequence)

Open **Claude Cowork** pointed at the `meridian_fde_pack/` directory and run these prompts step by step.

---

## Phase 1–3 Prompt: Discovery & Data Profiling
> "Inspect all files inside `datasets/`. Audit `legacy_claims_export.csv` against `policy_rules.md` and `target_schema.json`. Generate `docs/generated_discovery_audit.md` cataloging every date format anomaly, policy ID casing/missing issue, duplicate claim pair, and policy rule edge case, grouped by severity (Critical, High, Medium)."

## Phase 4–6 Prompt: ELT, Feature Engineering & Pipeline Build
> "Based on `docs/generated_discovery_audit.md`, `datasets/policy_rules.md`, and `datasets/target_schema.json`, write a production-clean Python script `scripts/cowork_triage_pipeline.py` that:
> 1. Normalizes all dates to ISO-8601 (`YYYY-MM-DD`) and standardizes policy IDs (`pol8821` -> `POL-8821`).
> 2. Routes missing policy IDs to `INTAKE_ERROR` (`INTAKE_REMEDIATION`).
> 3. Detects composite duplicates on `(policy_id, claimant_name, service_date, amount_inr)` and routes them to `DUPLICATE` (`DEDUP_ARCHIVE`).
> 4. Extracts signals from `adjuster_note` (inpatient/outpatient, discharge summary status, `PA-XXXX` pre-auth ID, out-of-network flags) and applies Silver/Gold/Bronze tier rules.
> 5. Outputs `datasets/cleaned_claims_payload.json` strictly matching `target_schema.json`. Run the script now and verify all 12 rows."

## Phase 7–8 Prompt: Evaluation & Regression Testing
> "Compare `datasets/cleaned_claims_payload.json` against `datasets/golden_ground_truth.csv`. Generate `docs/generated_evaluation_report.md` calculating overall routing accuracy, false auto-approval rate, duplicate recall, and a row-by-row diff table explaining any discrepancies."

## Phase 9–10 Prompt: POC Sign-Off, Runbook & Product Feedback
> "Create three final handoff artifacts in `docs/`:
> 1. `generated_poc_signoff_brief.md`: Executive summary for Meridian's VP of Claims Operations showing KPI achievements against baseline.
> 2. `generated_operator_runbook.md`: Step-by-step SOP for Meridian's Level-1 Ops team to run the pipeline and remediate `INTAKE_ERROR` and `DOCS_FOLLOWUP_QUEUE` items.
> 3. `generated_product_feedback_memo.md`: Technical RFC for our internal core product engineering team detailing native fuzzy policy-ID resolution and multi-format date ingestion needed across enterprise insurance clients."
