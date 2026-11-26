# FDE Hypotheses, Evaluation Parameters & Validation Protocol

## 1. Core FDE Hypotheses
- **H1 (Automation Lift):** Deterministic rule normalization + note signal extraction will auto-route **≥ 30%–65%** of valid routine claims without manual adjuster intervention while keeping complex cases safely queued.
- **H2 (Leakage Prevention):** Composite deduplication keys `(policy_id, claimant_name, service_date, amount_inr)` will achieve **100% recall** on cross-format duplicate submissions (`CLM-1002`, `CLM-1012`).
- **H3 (Compliance Safety — Zero-Tolerance Gate):** Hard threshold and missing-ID gates will achieve **0% false auto-approvals** on high-value (`> ₹1,00,000`), out-of-network (`SIU_HOLD`), or unverified claims.
- **H4 (Cycle-Time Compression):** Automated pre-triage will reduce batch processing time from ~12 minutes/claim to **< 2 seconds per batch**.

## 2. Benchmark Comparison Matrix

| Metric | Manual Baseline | POC Target | Validation Gate |
| :--- | :--- | :--- | :--- |
| **Routing Accuracy** | ~88% | **≥ 98%** (100% on Golden Set) | Must pass before sign-off |
| **False Auto-Approval Rate** | ~3–5% | **0.0%** | Hard blocker if > 0% |
| **Duplicate Recall** | ~40% | **100%** | Must catch `CLM-1002` & `CLM-1012` |
| **Schema Conformance** | Ad-hoc | **100%** | Validated against `target_schema.json` |

## 3. Engineer Validation Workflow
1. **Golden Set Verification:** Run `python3 scripts/reference_triage_pipeline.py` followed by `python3 scripts/evaluate_pipeline.py`.
2. **Boundary Stress Testing:** Verify `CLM-1011` (`₹1,00,001.00`) escalates to `SENIOR_REVIEW` rather than auto-approving.
3. **Zero-Leakage Inspection:** Audit every claim marked `READY_FOR_PAYOUT` first to guarantee zero compliance violations.
