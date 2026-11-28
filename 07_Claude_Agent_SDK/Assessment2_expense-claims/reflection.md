# Reflection

## Which results am I least sure of, and why?

**CLM-3010 (Lucas, Berlin offsite, approve $300.00).** The per diem is "$60 per full day away
overnight". The claim says "5 days, 15 to 19 February", but that is only 4 nights. If the 19th
was a return day with no overnight stay, the answer is 4 × $60 = $240.00. I accepted the 5 days
as claimed. The agent made the same call on its own and flagged the doubt in its reviewer notes.
The exclusion of the dinner (flag `double_claim`) is the part I am sure of.

**CLM-3002 (Mei, team dinner, approve $300.00).** Whether "dinner to celebrate the platform
release" counts as a *business purpose* is a judgment call. If a grader reads it as social, the
answer would be `needs_info`. I followed EX-201, which says an internal team meal is a business
meal.

**`policy_refs` and `flags` on every claim.** The policy says "the article IDs actually used" but
does not say whether articles used only to rule out a check count. I chose the articles that
decided the outcome or the amount. For flags, I recorded flags from earlier steps but not from
later checks: CLM-3003 carries both `over_limit` (step 6) and `monthly_cap_exceeded` (step 7).
These are the fields where I expect to lose partial credit if my reading differs from the grader's.

## One thing I enforce in code that I first tried to enforce in the prompt

**Which articles may be cited.** The first prompt only said "cite the articles you used". On the
first live run (CLM-3001, a simple meal), the agent cited EX-200, EX-201, EX-204 and EX-205:
everything it had read, including the decision framework itself. I made the prompt more specific,
and I also removed EX-200 from the `policy_refs` enum in the `save_decision` schema. The model now
cannot send it, however it reads the prompt. The re-run cited only EX-201.

The bigger version of the same lesson is the save guard. The order of checks, approving more than
was claimed, the monthly cap and the reply hard stops are all re-checked in `policy.decision_problems()`
before anything is written. The cost is false positives. My first payment-wording regex blocked
"Team meals are reimbursed up to $75 per person" on CLM-3002, which describes the policy and
promises nothing. The agent rewrote the sentence and saved, so the run cost one extra call. I
anchored the pattern to the claim ("your claim was reimbursed") and added a regression test. A
guard needs its own tests, like any other code.

## What I would change before letting it tell employees about their claims directly

1. **Keep a person in the loop for anything but routine approvals.** Today every reply is a draft. I
   would only auto-send replies for approvals with no flags, and queue the rest for a reviewer.
2. **Replace the regex reply guard with a two-layer check.** Keep the regexes as a fast first pass,
   and add a second, separate model call that scores the reply against the reply rules. Then test
   both on a set of adversarial replies. Regexes miss paraphrases ("the money is on its way") and
   other languages.
3. **Build a larger evaluation set.** Ten claims is not enough. I would add a few hundred, including
   claims that break two rules at once, and the injection patterns the heuristic in
   `policy.injection_signals` does not catch. I would run it on every prompt or model change.
4. **Verify the evidence, not the claim form.** The assistant trusts `receipt: attached` and the
   attendee list. A real deployment should read the receipt itself: vendor, date, amount, itemised
   alcohol.
5. **Identity and data access.** Today the employee is identified by a typed name. A real system
   needs an authenticated employee id, so nobody can file under someone else's name and see their
   cap or pre-approvals in the reply.
