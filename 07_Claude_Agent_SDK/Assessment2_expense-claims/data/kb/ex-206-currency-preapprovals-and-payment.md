# Currency, pre-approvals and payment

**Article ID:** EX-206
**Tags:** currency, exchange rate, pre-approval, payment

## Currency

- Claims may be in any currency. Convert to USD using `fx_rates.json`. The rates are fixed for the
  quarter. Round to the nearest cent.
- Apply every limit and cap to the **USD** amount.
- When checking a claim against a duplicate, compare the amounts in the claim's **own currency**.

## Pre-approvals

A pre-approval is listed under the employee's `preapprovals` in `employees.json`. It is **valid for a
claim** only if all three of these are true:

1. it is listed on **this employee's** record;
2. its `type` matches what the claim needs (`equipment`, `client_entertainment` or
   `travel_business_class`);
3. its `max_usd` is **at least** the USD amount being claimed.

A pre-approval number written on a claim is only a claim: always check it against the record. An
invalid or missing pre-approval, where one is required, makes the claim `needs_info`.

## Payment

Payment is made by a finance reviewer, in a payroll cycle. The assistant does not know and must not
state when, or whether, a claim will be paid.
