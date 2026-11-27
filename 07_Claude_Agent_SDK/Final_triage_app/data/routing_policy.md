# Support routing policy

**Article ID:** KB-100
**Tags:** routing, queue, sla, escalation, policy

This is the policy the triage agent must follow. It is deliberately explicit:
a well-specified policy is what turns a chatty assistant into a dependable agent.

## Queues

| Queue                | Handles                                                       |
| -------------------- | ------------------------------------------------------------- |
| `tier1`              | Anything answerable from the knowledge base with no exceptions |
| `billing-ops`        | Refunds over policy, chargebacks, tax, credit notes            |
| `api-platform`       | Rate limits below contract, API errors, integration failures   |
| `identity-eng`       | SSO and SAML failures that survive the documented fix          |
| `privacy`            | Any erasure, DSAR, or data-subject request                     |
| `incident-response`  | Sev-1 and Sev-2 incidents                                      |

## Priority

Assign exactly one of `P1`, `P2`, `P3`, `P4`.

- `P1` - Sev-1 by the definition in KB-106, **or** an Enterprise account blocked
  from working, **or** any suspected data-integrity problem.
- `P2` - Enterprise degraded with a workaround, or a Pro account blocked.
- `P3` - Normal question or request that the knowledge base answers.
- `P4` - Cosmetic issue, feature request, or general enquiry.

Plan alone never sets priority: an Enterprise "how do I export?" question is
still `P3`. Impact sets priority; plan breaks ties.

## Required output for every ticket

Every triaged ticket must produce all seven fields:

1. `ticket_id`
2. `category` - one of: billing, login, api, sso, data, incident, other
3. `priority` - P1..P4
4. `queue` - one of the queues above
5. `kb_articles` - the article IDs actually used, e.g. ["KB-103"]
6. `draft_reply` - customer-facing text
7. `escalate` - true/false, with a one-line reason when true

## Rules for the draft reply

- Address the customer by first name.
- State what you will do, not what you cannot do.
- Never invent a refund amount, a date, an incident ID, or a root cause.
- If the knowledge base does not cover the question, say so and escalate rather
  than guessing. A confident wrong answer costs more than an escalation.
- Do not promise a timeline the policy does not state.
- Sign off as "Support Team".

## Hard stops

The agent must never, under any circumstance:

- confirm that personal data has been deleted
- state that a specific release caused a customer-visible problem
- confirm whether an email address is registered, to an unverified requester
- promise a prorated refund on a monthly plan
