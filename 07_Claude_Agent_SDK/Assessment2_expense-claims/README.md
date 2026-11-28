# Expense Claim Reviewer

A claim review assistant built on the **Claude Agent SDK**. An employee or finance clerk
enters a claim. The claim is saved as a file, and an agent reviews it against the expense
policy (EX-200 to EX-206). The finance reviewer gets back a **recommended decision with all
seven policy fields and a draft reply**. The assistant only recommends: it never pays and
never contacts the employee.

## Quick start

```powershell
cd Assessment2_expense-claims
python -m venv .venv
.venv\Scripts\activate                      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                      # then put your ANTHROPIC_API_KEY in .env

python -m unittest discover -s tests        # 37 offline tests, no API key needed
python -m expense_app seed                  # copy the 10 sample claims into inbox/
python -m expense_app review CLM-3001       # review one claim; tool calls are shown live

streamlit run app.py                        # or use the web UI (http://localhost:8501)
```

The **web UI** (`app.py`) does the same as the CLI. In the *New claim* tab you enter a claim and can
review it straight away. The *Claims* tab lists claims with their status and lets you run a review:
each tool call appears live while the agent works. It shows the seven decision fields and the draft
reply, has a follow-up chat that survives restarts, and holds the **Approve and release** and
**Request changes** buttons. The *Batch & score* tab reviews every pending claim with a progress bar
and cost table, and runs the scoring script.

**Dark mode.** The 🌙 toggle in the bottom-left corner switches between light and dark. It stays
visible when the sidebar is collapsed. The choice is kept in the URL (`?theme=dark`), so it survives
a refresh. It applies only to your own browser session, because Streamlit's built-in theme is a
server-wide setting. `.streamlit/config.toml` fixes the base theme to light so the toggle is the
only switch, and the dark palette lives in `ui_theme.py`.

| Command | What it does |
|---|---|
| `python -m expense_app submit` | Enter a claim; prompts for each field, validates, saves `inbox/CLM-xxxx.json`. All fields can also be passed as options (`--employee "Mei Tan" --amount 600 ...`). `--review` reviews it immediately. |
| `python -m expense_app seed` | Copy `data/claims.json` into the inbox (keeps ids and `submitted_at`). Re-runnable. |
| `python -m expense_app list` | All claims, pending or reviewed, with the saved decision. |
| `python -m expense_app review CLM-3001` | Run the agent on one claim. Prints every tool call, then the decision and draft reply. `--force` re-reviews from scratch. |
| `python -m expense_app review-all` | Review every pending claim, then print a summary table with cost (batch mode). |
| `python -m expense_app ask CLM-3001 "why was the amount reduced?"` | One follow-up in the claim's own conversation. Works after a full restart. |
| `python -m expense_app chat CLM-3001` | Interactive follow-ups until `exit`. |
| `python -m expense_app show CLM-3001` | Print the saved decision and draft reply. |
| `python -m expense_app trace CLM-3001` | The audited tool calls for a claim, with inputs and results. |
| `python -m expense_app check` | Re-run the code-enforced policy checks on every saved decision. |
| `python -m expense_app score [--source outbox]` | Score `results/` (or the live outbox) against `tests/expected_samples.json`, field by field, and re-check each reply against the hard stops. |
| `python -m expense_app approve CLM-3001 --by "Ana Ruiz"` | A person approves the reply for the **current revision**. It is re-checked in code and written to `released/`. |
| `python -m expense_app request-changes CLM-3001 --by "Ana Ruiz" --note "..."` | A person holds the reply back and says what to change; then `ask` the agent to revise it. |
| `python -m expense_app export` | Copy decisions to `results/` with a `summary.md` table. |

**Model and cost.** The default is `claude-opus-5-5` (set `EXPENSE_MODEL` to change it). The SDK's
CLI also makes small background calls on `claude-haiku-5-5`, which are included in the costs below.
On the ten sample claims a review took 10 to 13 tool calls and cost **$0.07 to $0.14, about $0.10
on average** ($1.00 for all ten). A follow-up question costs about $0.13 to $0.20, because the
resumed conversation is sent again. Per-claim costs are in `evidence/batch_review_transcript.txt`
and `state/runs.jsonl`. Each run is capped at 30 turns and $1.00 (`EXPENSE_MAX_TURNS`,
`EXPENSE_MAX_BUDGET_USD`).

## Architecture

```
  user (CLI)                                         Claude Agent SDK (ClaudeSDKClient)
  ──────────                                         ───────────────────────────────────
  submit ──► store.save_claim ──► inbox/CLM-x.json        system prompt: role + method
                                        ▲                 tools=[]  (no Bash/Read/Write/Web)
  review ──► ReviewSession ─── "review CLM-x" ──►         allowed_tools = 13 MCP tools only
                │                       │                 permission_mode="dontAsk"
                │        ┌──────────────┴─────────────┐   max_turns=30, max_budget_usd=1.00
                │        │ EXTERNAL stdio MCP server  │   strict_mcp_config, setting_sources=[]
                │        │ "claims" (own process)     │
                │        │  list_pending_claims       │   hooks ──────────────────────────────
                │        │  read_claim  (fenced,      │   PreToolUse  audit_pre      -> state/audit.jsonl
                │        │   untrusted text)          │   PreToolUse  allowlist_guard (deny others)
                │        │  get_saved_decision        │   PreToolUse  save_guard on save_decision:
                │        └────────────────────────────┘     policy.decision_problems() -> deny + reasons
                │        ┌────────────────────────────┐   PostToolUse audit_post     -> state/audit.jsonl
                │        │ IN-PROCESS SDK MCP server  │
                │        │ "expense"                  │
                │        │  search_policy             │      policy.py (pure Python, no model)
                │        │  get_policy_article        │      Decimal money, FX, day counts,
                │        │  lookup_employee           │──►   duplicates, splits, pre-approvals,
                │        │  find_related_claims       │      caps, monthly cap, reply hard stops
                │        │  check_filing_deadline     │
                │        │  convert_to_usd            │
                │        │  check_preapproval         │
                │        │  calculate_reimbursable    │
                │        │  check_monthly_cap         │
                │        │  save_decision ────────────┼──► outbox/CLM-x.json (+ .reply.md, .history.jsonl)
                │        └────────────────────────────┘
                └── ResultMessage.session_id ──► state/sessions.json   (ask/chat: resume=session_id)
```

| File | Role |
|---|---|
| `expense_app/config.py` | Paths, model, limits, policy vocabulary (decisions, flags, targets). |
| `expense_app/store.py` | R1 intake and validation, one JSON file per claim, decisions with revisions, session ids. |
| `expense_app/policy.py` | Every rule code can check: FX (Decimal, half-up to the cent), filing gap, duplicates, split purchases, pre-approval validity, step-6 caps, monthly cap, injection heuristics, reply hard stops, and `decision_problems()` (the save guard). |
| `expense_app/claims_mcp.py` | External MCP server over stdio (FastMCP). The agent reads every claim through it. |
| `expense_app/tools.py` | In-process MCP server (`create_sdk_mcp_server`) with 10 tools. |
| `expense_app/hooks.py` | Audit log, allow-list guard, save guard. |
| `expense_app/agent.py` | System prompt, `ClaudeAgentOptions`, `ReviewSession` (connect, wait for MCP, stream tool calls, persist session id). |
| `expense_app/cli.py` | The command-line front end. |
| `app.py` | The Streamlit web UI (stretch goal). |
| `expense_app/scoring.py` | The scoring script (stretch goal). |
| `tests/test_policy.py` | 37 offline tests: arithmetic, facts, guard, reply rules, intake, tool error handling, approval gate, scoring. |
| `tests/expected_samples.json` | The expected outcome for each sample claim, worked out by hand from the policy before the agent ran. |

### How a review runs (R2)

`review CLM-3001` sends the agent one line: *"A new expense claim CLM-3001 is waiting in the inbox.
Review it following your method."* The claim text is **not** passed in. The model then chooses its
own calls. A typical sequence is `get_policy_article(EX-200)`, `read_claim`, `lookup_employee`, the
relevant articles, `find_related_claims`, `check_filing_deadline`, `calculate_reimbursable`,
`check_monthly_cap` and `save_decision`, but it stops early when a check settles the claim and
skips tools that do not apply. Every call is printed live and written to `state/audit.jsonl` by the
hooks. `trace CLM-x` prints them back.

### Sessions (R3)

Each claim has its own conversation. After every run the SDK's `session_id` is stored in
`state/sessions.json`, and `ask`/`chat` reopen it with `ClaudeAgentOptions(resume=session_id)`. The
SDK files sessions by working directory, so `cwd` is pinned to the project folder; that is what makes
resume work after the process has exited. If a follow-up changes anything, the agent calls
`save_decision` again: the decision gets a new `revision` (the history is in `outbox/CLM-x.history.jsonl`).
The guard still applies to revisions.

## Design decisions

1. **The model judges, code computes.** Currency conversion, day counts, duplicate and split
   matching, pre-approval validity, per-person, per-night and per-day caps, and the monthly cap are
   tools backed by `Decimal` arithmetic. The model chooses the rule and its inputs, such as attendees,
   nights, days and what to exclude. It never adds up money itself.
2. **Tools read the claim from disk, not from the model.** `find_related_claims`, `calculate_reimbursable`,
   `check_preapproval` and the others take only a `claim_id`. The model cannot pass a different amount,
   date or pre-approval number than the employee submitted.
3. **A save guard re-checks the decision in code (PreToolUse hook + inside the tool).**
   `policy.decision_problems()` re-derives everything deterministic and refuses a decision that:
   breaks the order of checks (a duplicate must be a reject, late filing must escalate to
   finance-controller, a split must escalate to compliance, a monthly-cap breach must escalate to
   manager); approves more than claimed; uses a flag the data contradicts; misses
   `injection_attempt` when the claim contains instructions; or has a reply that breaks a hard
   stop or reply rule. The reply checks cover payment wording, another employee's name, their
   pre-approval or claim ids, accusatory words, internal flag names, first-name greeting and
   "Finance Operations" sign-off. The denial reasons go back to the model, which fixes them and
   saves again. Judgment calls stay with the model: what an item really is, whether attendees
   and purpose are given, the number of nights.
4. **Two MCP servers with different jobs.** The inbox is an external stdio server, a separate
   process any MCP client could use, and the agent must read every claim through it. The review
   logic is in-process, because it shares code with the guard and needs no subprocess.
5. **Least privilege.** `tools=[]` removes every built-in tool, so there is no shell and no file
   access. `allowed_tools` lists the 13 MCP tools, `permission_mode="dontAsk"` denies everything
   else without prompting, and an allow-list hook repeats the check. `strict_mcp_config` and
   `setting_sources=[]` ignore machine-level MCP servers and settings.
6. **Hostile text stays data.** `read_claim` returns the claim as JSON, so quotes and newlines are
   escaped and cannot pose as a new message. It labels employee-written fields `_as_entered` /
   `_untrusted` and lists instruction-like phrases it detected. The guard then insists on the
   `injection_attempt` flag. Even if the model were persuaded, the save guard would still refuse
   an over-claim approval, a skipped check or a forbidden reply.
7. **Nothing about other employees can leak by construction.** `lookup_employee` returns only the
   named employee. `find_related_claims` returns only that employee's past claims.
   `check_preapproval` says "not on this employee's record" and never says whose a number is. The
   reply guard blocks other employees' names and ids anyway.
8. **Plain files.** Claims, decisions, replies, history, sessions and the audit log are JSON/JSONL/Markdown
   you can open. Claim ids are validated against `^CLM-\d{4,6}$` before they become file names, which
   stops path traversal.

## Policy interpretations

Where the policy leaves room, this is how the assistant reads it:

- **Flags** record the settling check's flag, flags from earlier steps that applied (e.g.
  `alcohol_excluded`, `over_limit`, `double_claim`), and always `injection_attempt` when present.
  Later checks are not run, so their flags are not added. For example, a duplicate is not also
  flagged `missing_receipt`.
- **policy_refs** lists the articles whose rules decided the outcome or the amount: EX-206 when a
  currency was converted or a pre-approval checked, EX-205 when the monthly cap decided it. EX-200,
  and articles consulted only to rule a check out, are not listed.
- **Split purchase** follows EX-205 literally: the same employee, vendor and day; each claim under
  $150 in USD; total over $150; no `equipment` pre-approval on the record covering the total. It is
  not limited to the `equipment` category, because the category field does not change what an
  item is.
- **Pre-approval.** The record is the source of truth. A cited number not on the employee's record
  is invalid. If the employee's own record has a matching pre-approval of the right type and limit,
  it counts even if they cited the wrong number or none.
- **Hotel cap** is `min(actual total, limit × nights)`, which equals the per-night rule when the
  nightly rate is the same each night.
- **Per diem days**: the number of full days stated on the claim (e.g. "5 days, 15 to 19 February" → 5).
- **Unknown employee** → `needs_info`: resubmit under the name on their employee record. The cap and
  pre-approvals cannot be checked, so the guard never allows an approval.
- **Currency not in `fx_rates.json`** → `escalate` to `finance-controller`, since there is no rate the
  assistant may use. The guard never allows an approval.
- **Approve** always means a positive amount. When nothing is reimbursable the decision is `reject`.
- **Reply wording.** The assistant says it has *recommended* an amount. Phrases like "has been
  approved", "will be reimbursed" or any payment timing are blocked as implying payment or a final
  approval.

## Stretch goals

| Goal | Status | Where |
|---|---|---|
| Web UI with live progress | Done | `app.py` (Streamlit). Each tool call appears in a status box as the agent makes it, and guard denials show as warnings. |
| Batch mode with summary table and cost | Done | `review-all` (CLI) and the *Batch & score* tab. |
| Own scoring script | Done | `score` / `expense_app/scoring.py`. Scores decision, amount to the cent, escalation, flags (Jaccard) and cited articles against `tests/expected_samples.json`, and re-checks every reply. **Note:** those expected outcomes are *our own* reading of the policy, so 100% means the agent agrees with our reading, not that a grader would. |
| Hold the reply until a person approves it | Done | Every saved revision starts as `pending_review`. Only a person (the `approve` command or the UI button, with their name) can release it to `released/`, and only after the code re-checks the decision and the reply. A new revision, for example after a follow-up, withdraws the released reply and needs approval again. The agent has no tool that reaches the approval functions. Every verdict is logged in `state/approvals.jsonl`. |
| Two cooperating agents (subagents) | Not done | A single agent plus code-enforced checks was enough for the decisions, and a second agent rewriting the reply would have to pass the save guard again. |

## Results and evidence

- `results/`: the decision (`.json`, all seven fields plus reviewer notes) and draft reply (`.reply.md`)
  for all ten sample claims, and `summary.md`. These are the first reviews, exported before the session
  demo. In that demo a follow-up changed CLM-3002 to $225.00 (revision 2), using a fact supplied by the
  finance reviewer that is not in the sample data.
- `evidence/batch_review_transcript.txt`: the batch run with live tool calls and cost per claim.
- `evidence/session_transcript.txt`: CLM-4004 (a claim not in the sample set) reviewed, a follow-up, a
  full restart, and a second follow-up. Then CLM-3002: a follow-up after a restart changes the
  decision, which saves revision 2.
- `evidence/tool_trace_CLM-3002.txt`: the hook audit trail for one claim: every call, its input and its
  result, including one save the guard denied and the corrected retry.
- `evidence/edge_cases_transcript.txt`: an empty claim, bad and unknown ids, an unknown employee, an
  unsupported currency (JPY), and a hostile claim that tries to change the amount and extract another
  employee's data.
- `evidence/approval_and_scoring_transcript.txt`: the approval gate (missing name or note refused,
  approve and release, request changes) and the scoring script's output.
