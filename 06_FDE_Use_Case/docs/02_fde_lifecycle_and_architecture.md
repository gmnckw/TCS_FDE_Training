# 10-Phase FDE Lifecycle & Technical Architecture

## Problem Statement
Meridian Health & Claims processes thousands of group health claims weekly through fragmented legacy CSV exports and unstructured policy rulebooks. Manual cross-checking causes a **12–15 minute handling bottleneck per claim**, **3–5% duplicate or policy leakage**, and frequent downstream API rejections due to unstandardized dates (`DD/MM/YYYY`, `DD-Mon-YYYY`) and policy IDs (`pol8821` vs. `POL-8821`).

---

## End-to-End 10-Phase FDE Execution Matrix

| Phase | FDE Activity | Technical Approach | Exit Artifact |
| :--- | :--- | :--- | :--- |
| **1. Requirements Capturing** | Map business SLAs, hard compliance gates, and downstream API contracts | Interview SMEs & IT; freeze `target_schema.json` | Signed Requirements & Gate Spec |
| **2. Data Collection** | Ingest anonymized historical claims, policy docs, and SME labels | Place raw extracts in isolated local workspace | `legacy_claims_export.csv`, `policy_rules.md` |
| **3. Data Analysis & Profiling** | Audit null rates, format drift, duplicates, and rule conflicts | Run Cowork batch inspection across all files | `discovery_audit.md` |
| **4. ELT & Schema Normalization** | Standardize dates to ISO-8601, uppercase policy IDs, cast currency floats | Deterministic Python parser + quarantine routing | Normalized staging table |
| **5. Feature Engineering** | Derive deduplication hashes and extract note signals (`PA-XXXX`, discharge status) | Composite key `(policy_id, name, date, amount)` + regex/LLM extraction | Enriched feature vectors |
| **6. Solution & Infra Design** | Design lightweight, idempotent batch/webhook microservice | Stateless Python worker + JSON schema validator + dead-letter queue | Architecture & Data Flow Diagram |
| **7. Model & Rule Evaluation** | Benchmark pipeline against SME-labeled Golden Dataset | Precision/Recall, False Auto-Approval Rate, Confusion Matrix | `evaluation_report.md` |
| **8. Deployment Automation** | Package reproducible CLI/container pipeline with automated regression tests | CI test runner executing `evaluate_pipeline.py` on every rule change | `triage_pipeline.py` + test suite |
| **9. POC Customer Sign-Off** | Review shadow-mode results against pre-agreed exit criteria | Formal gate review with VP Ops, Compliance, and IT | Signed POC Acceptance Memo |
| **10. Handoff & Product Feedback** | Enable client Ops team and log core product gaps for R&D | Deliver runbooks + submit native fuzzy-ingestion RFC to core engineering | `operator_runbook.md`, `product_feedback_memo.md` |
