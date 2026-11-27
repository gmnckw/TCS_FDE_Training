# Incidents, outages, and severity

**Article ID:** KB-106
**Tags:** outage, incident, downtime, severity, sev1, status page, data integrity

## Before answering an "is it down?" ticket

Check `status.example-app.com` first. If an incident is open, reply with the
incident ID and the posted ETA, and do not speculate about the cause.

If no incident is open, treat it as a single-customer issue and collect: region,
API key prefix, one request ID, and the exact timestamp.

## Severity ladder

| Severity | Definition                                                      | First response |
| -------- | --------------------------------------------------------------- | -------------- |
| Sev-1    | Total outage, data loss, or **incorrect data shown to end users** | 15 minutes     |
| Sev-2    | Major feature broken for many users, no workaround               | 1 hour         |
| Sev-3    | Feature degraded, workaround exists                              | 4 hours        |
| Sev-4    | Cosmetic, question, or feature request                           | 1 business day |

**Any suspected data-integrity problem is Sev-1**, even if the system is
otherwise up, and even if only one customer reports it. Wrong numbers shown to a
customer's own customers are the most damaging class of incident we have.

## Sev-1 handling

1. Page the on-call engineer through the incident channel immediately. Do not
   wait for a second confirmation.
2. Acknowledge to the customer within 15 minutes, without assigning blame or
   confirming a root cause.
3. Offer a live call for Enterprise accounts.
4. Never state that a release caused the problem until engineering confirms it.

## Churn-risk language

Phrases such as "considering switching providers", "our CTO is asking", or
"we have an audit" mark the account as at-risk. Flag the ticket for the account
manager in addition to the technical escalation.
