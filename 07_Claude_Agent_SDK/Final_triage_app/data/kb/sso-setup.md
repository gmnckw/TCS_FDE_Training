# SSO and SAML setup

**Article ID:** KB-104
**Tags:** sso, saml, okta, azure ad, identity provider, blank screen

## Supported providers

Okta, Azure AD / Entra ID, Google Workspace, and any SAML 2.0 IdP.
SSO is an **Enterprise-only** feature.

## The "blank screen after redirect" failure

This is the single most reported SSO symptom. It has one usual cause and two
rarer ones.

**Usual cause - stale session cookie.** A user who was signed in with a password
before SSO was enforced keeps a legacy session cookie. The SAML assertion is
accepted, then the two sessions collide and the app renders nothing. It affects
only the subset of users who had signed in previously, which is why it looks
random. Clearing cookies fixes it until the next collision.

**Permanent fix:** the workspace admin runs **Settings -> Security -> Revoke all
sessions** once, after SSO enforcement is switched on. Every user signs in again
cleanly. This is a 30-second action and resolves the ticket.

**Rarer cause 1 - clock skew.** More than 3 minutes of drift between the IdP and
our servers invalidates the assertion. Symptom is usually an explicit error, not
a blank screen.

**Rarer cause 2 - attribute mapping.** A missing `email` attribute in the SAML
response produces a blank screen on some browsers. Ask for a SAML trace.

## Data support should collect

- IdP entity ID
- Whether the affected users had password logins before SSO
- One SAML trace (browser extension) from an affected user

## Escalation

Escalate to **Identity Engineering** only after "revoke all sessions" has been
tried and the symptom persists.
