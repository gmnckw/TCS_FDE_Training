# Meridian Group Health — Triage & Routing Rules (v2.4)

## Tier Rules
- **POL-8821 (Silver Tier):**
  - Auto-approve (`READY_FOR_PAYOUT` -> `AUTO_PAYOUT_BATCH`) outpatient claims under ₹25,000.
  - Inpatient claims require a Discharge Summary (`AWAITING_DOCS` -> `DOCS_FOLLOWUP_QUEUE` until attached). If attached, route to `AUTO_PAYOUT_BATCH`.
- **POL-9044 (Gold Tier):**
  - Auto-approve claims up to ₹50,000 if a pre-authorization ID (`PA-XXXX`) is present. If missing pre-auth, route to `AWAITING_DOCS` -> `DOCS_FOLLOWUP_QUEUE`.
  - **Hard Escalation:** Any single claim `> ₹1,00,000` must route to `SENIOR_REVIEW` -> `SENIOR_ADJUSTER_QUEUE`.
- **POL-7712 (Bronze Tier):**
  - Strictly in-network providers only (`READY_FOR_PAYOUT` -> `AUTO_PAYOUT_BATCH`).
  - Out-of-network or provider mismatch claims route to `SIU_HOLD` -> `SIU_REVIEW`.

## Global Gates (Evaluated First)
1. **Missing Policy ID:** Any claim missing a valid `POL-XXXX` identifier routes to `INTAKE_ERROR` -> `INTAKE_REMEDIATION`.
2. **Duplicate Detection:** Composite match on `(normalized_policy_id, claimant_name, iso_service_date, amount_inr)` routes subsequent records to `DUPLICATE` -> `DEDUP_ARCHIVE`.
