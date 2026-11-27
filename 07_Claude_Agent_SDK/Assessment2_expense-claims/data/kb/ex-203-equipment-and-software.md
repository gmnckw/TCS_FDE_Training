# Equipment and software

**Article ID:** EX-203
**Tags:** equipment, hardware, software, pre-approval, procurement, threshold

## Equipment purchases

Measure each purchase by its **total for that vendor on that day** (see EX-205 on split purchases).

| Purchase total (USD) | Rule |
| --- | --- |
| under $150 | Reimbursable with a receipt. |
| $150 to $1,000 | Needs a valid manager pre-approval of type `equipment` (EX-206). Without one, the claim is `needs_info`. |
| over $1,000 | Not reimbursable through expenses. It must go through procurement. `reject` and point the employee to procurement. |

## Software and subscriptions

Software licences and subscriptions are **never** reimbursed through expenses, at any price. IT
buys them. `reject` and point the employee to IT.
