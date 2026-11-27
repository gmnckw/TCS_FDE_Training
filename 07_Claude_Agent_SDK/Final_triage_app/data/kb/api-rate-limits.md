# API rate limits

**Article ID:** KB-103
**Tags:** api, 429, rate limit, throttling, batch, quota

## Published limits

| Plan       | Requests / minute | Burst | Batch endpoint |
| ---------- | ----------------- | ----- | -------------- |
| Free       | 60                | 100   | not available  |
| Pro        | 300               | 450   | 60 / min       |
| Enterprise | contract-defined  | +50%  | contract-defined |

Enterprise limits live in the contract, not in the default table. Always look up
the account's contracted limit before telling an Enterprise customer what their
limit is.

## Reading a 429

Every 429 response carries these headers:

- `X-RateLimit-Limit` - the ceiling currently applied to the key
- `X-RateLimit-Remaining` - requests left in the window
- `Retry-After` - seconds to wait

If `X-RateLimit-Limit` is **lower than the contracted value**, the account has
been throttled by an operational safeguard rather than by its own quota. That is
a platform-side issue: escalate to the API Platform team with the API key prefix
and a sample response header dump.

## Common causes

- Client-side retry storms - a failed request retried without backoff multiplies
  load and keeps the key pinned at the limit.
- A new deploy that removed request batching.
- Sharing one API key across several services.

## Escalation

Escalate to **API Platform** when: the limit applied is below contract, the 429s
started without a client-side change, or the customer has a compliance or audit
deadline within 5 business days.
