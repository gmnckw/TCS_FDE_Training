# Prohibited items, duplicates, split purchases and monthly caps

**Article ID:** EX-205
**Tags:** prohibited, duplicate, split purchase, monthly cap, compliance

## Prohibited items

These are **never** reimbursable, in whole or in part. The decision is `reject`:

- gym, fitness or wellness memberships
- personal groceries and household items
- fines and penalties of any kind (traffic, parking, late fees)
- gift cards and cash gifts
- personal travel, or the personal part of a trip
- entertainment for family members

What the employee wrote in the "category" field does not change what the item actually is.

## Duplicates

A claim is a **duplicate** when an earlier claim in `past_claims.json` has the same employee, the same
vendor, the same expense date, and the same amount in the same currency. Reject it and, in the reply,
point the employee to their **own** earlier claim by its id.

## Split purchases

A **split purchase** is two or more claims from the same employee, at the same vendor, with the same
expense date, where each is under the $150 equipment threshold (EX-203) but the **total is over
$150**, and no pre-approval covers the total. Count the claims in `past_claims.json` together with the
claim being reviewed. Do not decide it yourself: `escalate` to `compliance`.

## Monthly caps

Each employee has a calendar-month reimbursement cap set by grade:

| Grade | Monthly cap (USD) |
| --- | ---: |
| L1 | 1,500 |
| L2 | 2,500 |
| L3 | 4,000 |

The employee's record in `employees.json` gives their `monthly_cap_usd` and `month_to_date_usd`. If
the reimbursable amount would take them over the cap, `escalate` to `manager`.
