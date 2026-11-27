# Login and password reset

**Article ID:** KB-102
**Tags:** login, password, reset, email delivery, magic link

## Reset email not arriving

Work through these in order before escalating:

1. **Confirm the address is registered.** Reset mail is only sent to known
   accounts. An unregistered address gets no email and no error, by design.
2. **Check the mail domain.** Reset mail is sent from `no-reply@example-app.com`.
   Corporate filters frequently quarantine it. Ask the customer to check the
   quarantine, not just the spam folder.
3. **Check the rate limit.** After 3 reset requests in 15 minutes, further
   requests are silently dropped for 30 minutes. This is the single most common
   cause of "I tried 4 times and nothing came".
4. **Check for SSO.** Accounts on an SSO-enforced workspace cannot use password
   reset at all. They must sign in through their identity provider.

## Manual reset

Support can issue a one-time sign-in link valid for 15 minutes from the admin
console. This is safe for Free and Pro accounts. For Enterprise accounts, a
manual link requires approval from the workspace admin on record.

## Never do this

Never read a password back to a customer, never accept a password over chat, and
never confirm whether an email address is registered to an unauthenticated
caller. Those requests are account-enumeration attempts.
