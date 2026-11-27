# Billing and refunds

**Article ID:** KB-101
**Tags:** billing, refund, duplicate charge, invoice, proration

## Duplicate charges

Duplicate charges are almost always caused by a retried payment authorisation.
Support can refund a duplicate directly, with no approval, when **all** of these hold:

- The two charges are for the same amount, on the same card, within 72 hours.
- The account has exactly one active subscription.
- The amount is under **USD 500**.

Refunds land back on the original card in 5-10 business days.

If any condition fails, route the ticket to **Billing Operations** instead of refunding.

## Proration on cancellation

Monthly plans are **not** prorated on cancellation. The subscription stays active
until the end of the paid period, then lapses. Annual plans are prorated to the
month, minus a 5% administration fee.

Do not promise a prorated refund on a monthly plan. Offer the remaining access
period instead.

## Refund escalation triggers

Escalate to Billing Operations, do not resolve in-channel, when the ticket involves:

- an amount at or above USD 500
- a chargeback or a dispute already opened with the card issuer
- a request older than 90 days
- any tax or VAT adjustment

## Standard invoice fields

Invoice numbers use the form `INV-#####`. Customers can download PDFs from
**Settings -> Billing -> Invoices**. Invoices cannot be re-issued with a
different billing name after they are finalised; issue a credit note instead.
