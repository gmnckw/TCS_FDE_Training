# Results

Produced by `python -m expense_app review-all` and exported with `python -m expense_app export`. Each claim has a `.json` decision (all seven policy fields) and a `.reply.md` with the draft reply.

| claim | employee | decision | approved_amount_usd | policy_refs | flags | escalate_to |
|---|---|---|---:|---|---|---|
| CLM-3001 | Daniel Okafor | approve | 198.00 | EX-201 | - | none |
| CLM-3002 | Mei Tan | approve | 300.00 | EX-201 | alcohol_excluded, over_limit | none |
| CLM-3003 | Asha Verma | escalate | 0.00 | EX-202, EX-205, EX-206 | monthly_cap_exceeded, over_limit | manager |
| CLM-3004 | Lucas Meyer | needs_info | 0.00 | EX-203, EX-206 | invalid_preapproval | none |
| CLM-3005 | Sara Lindqvist | escalate | 0.00 | EX-205 | split_purchase | compliance |
| CLM-3006 | Omar Haddad | needs_info | 0.00 | EX-204 | missing_receipt | none |
| CLM-3007 | Ravi Iyer | reject | 0.00 | EX-205 | duplicate | none |
| CLM-3008 | Chloe Dubois | reject | 0.00 | EX-205 | injection_attempt, prohibited_item | none |
| CLM-3009 | Daniel Okafor | escalate | 0.00 | EX-204 | late_submission | finance-controller |
| CLM-3010 | Lucas Meyer | approve | 300.00 | EX-201, EX-202 | double_claim | none |
