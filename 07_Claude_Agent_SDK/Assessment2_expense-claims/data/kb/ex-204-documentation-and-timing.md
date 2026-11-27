# Documentation and timing

**Article ID:** EX-204
**Tags:** receipts, documentation, deadline, late claims

## Receipts

- A receipt is required for any single item worth **$25 or more** (in USD). It must show the vendor,
  the date and the amount.
- If a required receipt is missing, the claim is `needs_info`.
- Per-diem days (EX-202) never need receipts.
- Items worth less than $25 do not need a receipt.

## Deadline

- A claim must be submitted within **60 days** of the expense date: the gap between `expense_date`
  and `submitted_at` is at most 60 days.
- A claim submitted later than that is a **late claim**. The assistant must neither approve nor reject
  a late claim: `escalate` to `finance-controller`, who decides whether to make an exception.
