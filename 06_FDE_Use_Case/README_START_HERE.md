# Meridian Health & Claims — FDE End-to-End Exercise Pack

Welcome to the **Forward Deployed Engineer (FDE) Customer Engagement & Claude Cowork Exercise Kit**.

## Folder Structure
- `datasets/`
  - `legacy_claims_export.csv`: 12 messy customer claims containing date drift, lowercase IDs, duplicates, boundary amounts, and missing fields.
  - `golden_ground_truth.csv`: SME-labeled ground truth for automated evaluation.
  - `policy_rules.md`: Unstructured policy rulebook extracted from client documentation.
  - `target_schema.json`: Downstream claims API payload contract.
- `docs/`
  - `01_customer_interaction_playbook.md`: How the FDE interacts with client executives, IT, and SMEs across every stage.
  - `02_fde_lifecycle_and_architecture.md`: Complete 10-phase FDE technical blueprint (Requirements -> POC Sign-Off).
  - `03_claude_cowork_prompts.md`: Copy-paste prompts to run the entire exercise end-to-end inside Claude Cowork.
  - `04_hypotheses_and_evaluation.md`: Statistical hypotheses, KPI benchmarks, and validation protocol.
- `scripts/`
  - `reference_triage_pipeline.py`: Working reference implementation of the ELT and rules engine.
  - `evaluate_pipeline.py`: Automated evaluation script comparing pipeline output against `golden_ground_truth.csv`.

## Quick Start with Claude Cowork
1. Unzip this folder onto your local machine (`meridian_fde_pack/`).
2. Open **Claude Cowork** and grant folder access to `meridian_fde_pack/`.
3. Follow `docs/01_customer_interaction_playbook.md` for stakeholder discovery, then run the prompts in `docs/03_claude_cowork_prompts.md` phase by phase.
