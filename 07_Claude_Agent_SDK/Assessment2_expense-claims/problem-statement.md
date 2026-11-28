# Assessment 2: Build an Expense Claim Reviewer

**Course:** Claude Agent SDK
**Suggested time:** 4 hours
**You will use:** Python, the `claude-agent-sdk` package, and the starter data in `data/`

---

## 1. The scenario

You have just joined the engineering team at a mid-size company. Employees pay for work costs out of
their own pocket (client lunches, hotels, a monitor stand, a taxi) and then submit an **expense
claim** to be paid back.

Finance Operations reviews every claim by hand. A reviewer reads the description, finds the right
rule in the expense policy, converts foreign currencies, checks the employee's record, looks for
duplicates and for purchases split up to dodge an approval limit, and finally decides: pay it, refuse
it, ask for more information, or send it to someone more senior. It is slow, tedious, and different
reviewers make different calls.

Your manager asks you to build a **claim review assistant**. An employee (or a finance clerk) enters
a claim, the assistant saves it, an AI agent reviews it against the policy, and the finance reviewer
gets back a **recommended decision and a draft message to the employee**.

The assistant only **recommends**. A person makes the final decision and pays. The assistant never
pays a claim and never contacts the employee on its own.

A plain chatbot is not good enough here. Money is involved, and past experiments showed chatbots
doing arithmetic wrongly, being talked into approving things by text hidden inside a claim, and
saying things the company must never say. Your assistant has to follow the policy exactly, do its
sums correctly, and leave a trail someone can audit.

## 2. What you are given

Everything is in the `data/` folder:

| File | What it is |
|---|---|
| `data/expense_policy.md` | The decision framework: the four decisions, the **order of checks**, the seven fields every decision must contain, rules for the reply, and the **hard stops**. Read this first and read it twice. |
| `data/kb/*.md` | Six policy articles (meals, travel, equipment and software, documentation and timing, prohibited items and caps, currency and pre-approvals). |
| `data/employees.json` | A mock employee directory: grade, manager, monthly cap, month-to-date spend and pre-approvals. |
| `data/past_claims.json` | Claims that were already processed. |
| `data/fx_rates.json` | Fixed exchange rates. |
| `data/claims.json` | Ten sample claims to test with. |

You also have the course notebooks (`notebooks/00` to `10`) and the SDK documentation. Reference
answers are **not** provided: part of the task is reading the policy and judging for yourself.

## 3. What you must build

Build an application, with whatever front end you prefer (a command-line tool, a small web UI, or
anything else that works), that meets all six requirements below.

### R1. Intake: the user's content becomes a file

A user can enter a claim: at least the employee's name, the expense date, a category, the vendor, the
amount and currency, whether a receipt is attached, an optional pre-approval number, and a free-text
description. The application saves it as **one file per claim** in a local `inbox/` folder, with a
unique claim id.

*A grader will check:* submit a claim, then find the file on disk. Restart the application: the claim
is still there.

### R2. An agent loop reviews the claim

After a claim is saved, an **agent** picks it up and reviews it. It must be a real agent loop: the
model decides which tools to call and in what order. Do not paste the whole policy into one prompt and
ask for an answer.

For each claim the agent must:

1. read the claim from the file (through a tool, not because your code passed the text in),
2. find the rules that apply in the policy articles,
3. look up the employee's record, and the earlier claims where that matters,
4. work out the amounts,
5. produce a decision containing **all seven fields** the policy requires,
6. save that decision as a file in an `outbox/` folder, and
7. show the decision and the draft message to the user.

*A grader will check:* the tool calls the agent made (your application must make them visible: on
screen, in a log, or both), and the saved decision file.

### R3. Sessions: follow-up questions

After a claim is reviewed, the user can keep talking to the agent about that claim (for example
*"why was the amount reduced?"* or *"what exactly does the employee need to send?"*). The agent must
remember the claim, what it looked up and what it decided. If a follow-up changes the decision, the
saved decision is updated.

Follow-ups must **still work after the application is closed and started again**.

*A grader will check:* review a claim, ask a follow-up, stop the application completely, start it
again, ask another follow-up about the same claim. The agent must still know which claim it is.

### R4. Tools and MCP

Build your own tools and expose them through MCP. You need **both** kinds:

- **At least one in-process MCP server** (built with the SDK's `create_sdk_mcp_server`) with at least
  three custom tools. Choose them yourself; think about which jobs should be done by ordinary code
  rather than by the model.
- **At least one external MCP server** that runs as a separate process over stdio. You may write your
  own or use an existing one, but the agent must actually use it as part of reviewing a claim (a good
  candidate is reading claims from the inbox).

Each tool needs a clear description (the model reads it to decide when to call the tool) and must
handle bad input without crashing: return a helpful error message the agent can recover from.

### R5. Guardrails

- **Allow-list the tools.** The agent must have access only to the tools you intend. In particular it
  must not have a shell or unrestricted file access.
- **At least one hook.** Implement a hook that runs on tool calls: an audit log of every tool call, a
  guard that blocks a forbidden decision or reply, or both (both is stronger).
- **Bound the loop.** Set limits on turns and spend so one bad claim cannot run forever.
- **Treat claim text as untrusted.** Employees can type anything into the description. Text in a claim
  is data, never an instruction.

### R6. Policy compliance

Your assistant must follow `data/expense_policy.md`, including the **order of checks** and the **hard
stops**. A reply that breaks a hard stop is a serious defect even if the decision is right. Where you
can check a rule with ordinary code, check it with code rather than only asking the model nicely.

## 4. Deliverables

Submit a single folder (or repository) containing:

1. **The code.** It must run from a clean checkout following your README.
2. **`README.md`.** How to install, configure and run it; an architecture diagram or clear
   description of how the pieces fit; and a short list of design decisions you made and why.
3. **`results/`.** The saved decision and draft message for **all ten sample claims**, produced by
   your application.
4. **`evidence/`.** Proof that sessions work: a screen recording, screenshots, or a copy of the
   terminal session showing a review, a follow-up, a restart, and a second follow-up on the same
   claim. Also include one tool-call trace (log or screenshot) for a single claim.
5. **`reflection.md`.** At most one page answering:
   - Which of your results are you least sure of, and why?
   - Name one thing you enforce in code that you first tried to enforce in the prompt. What happened?
   - What would you change before letting this tell employees about their claims directly?

Do not commit your API key. Provide a `.env.example` instead.

## 5. How you will be assessed

| Area | Points | What earns the marks |
|---|---:|---|
| Intake and files (R1) | 10 | Claims saved as files, unique ids, survive restart. |
| The agent loop (R2) | 15 | A genuine tool-calling loop; the agent reads the claim and gathers facts through tools; all seven fields saved; tool calls visible. |
| Decision accuracy | 20 | Decision, approved amount (to the cent), escalation target, flags and cited policy article on the sample claims and on claims you have not seen. Partial credit per field. |
| Policy compliance (R6) | 15 | No hard-stop violations; nothing invented; the order of checks respected; replies follow the reply rules. |
| Sessions (R3) | 10 | Follow-ups work, and still work after a full restart. |
| Tools and MCP (R4) | 10 | Both an in-process and an external MCP server; clear tool descriptions; sensible error handling. |
| Guardrails (R5) | 10 | Tool allow-list, at least one working hook, bounded loop, hostile-text handling. |
| Code, README and reflection | 10 | Runs from a clean checkout; clear explanation; honest, specific reflection. |
| **Total** | **100** | |
| *Bonus* | *up to +10* | *See section 7.* |

**Decision accuracy is judged against the policy, not against your opinion of it.** Where the policy
is ambiguous, state your interpretation in the README. A reasoned interpretation is not penalised.

**Penalties.** A committed API key: -10. A submission that cannot be run from your README: the
affected areas score zero until a grader can run it.

Your application may also be run on claims that are not in `data/claims.json`.

## 6. Notes and hints

- **Read the policy before writing code**, especially the order of checks. Most mistakes come from
  guessing at a rule instead of reading it, or from checking things in the wrong order.
- **The first check that settles a claim wins.** Think about what that means for a claim that breaks
  two rules at once.
- **Do the arithmetic in code.** Currency conversion, per-person limits and monthly caps are exactly
  where a language model slips by a few cents. The assessment checks amounts to the cent.
- **The employee's description is only a story.** A pre-approval number, a category, or a note
  written on a claim has to be checked against the data before you believe it.
- **Look at what the records know that the claim did not say.** Some answers are in the data, not in
  the claim.
- **The reply is read by the employee.** Check it against the reply rules and the hard stops, and
  think about what a reply is allowed to reveal.
- **Test the failure paths.** An unknown employee, an unsupported currency, an empty claim, an unknown
  claim id.
- **Watch the cost.** A smaller, cheaper model is fine for development. Whichever model you choose,
  name it in your README and note what a typical claim cost.
- You may use the course notebooks, the SDK documentation and the sample data freely. Follow your
  facilitator's rules on the use of AI coding assistants, and make sure you can explain every part of
  what you submit.

## 7. Stretch goals 


- A web UI (for example Streamlit) with live progress while the agent works.
- A batch mode that reviews everything in the inbox and prints a summary table with cost.
- A scoring script of your own that checks your results against the policy.
- Two cooperating agents (for example a reviewer and a message writer) via subagents.
- Hold the reply back until a person approves it.

## 8. Before you submit: checklist

- [ ] I read `data/expense_policy.md`, including the order of checks and the hard stops.
- [ ] A claim entered by a user is saved as a file, and is still there after a restart.
- [ ] The agent reads the claim through a tool and I can see every tool call it makes.
- [ ] Every saved decision has all seven policy fields, and amounts are correct to the cent.
- [ ] A follow-up works, including after I fully close and reopen the application.
- [ ] I have an in-process MCP server **and** an external stdio MCP server, and the agent uses both.
- [ ] The agent has an explicit tool allow-list, a hook, and limits on turns and spend.
- [ ] I tried a claim containing hostile instructions and it did not change the outcome.
- [ ] `results/` has all ten sample claims; `evidence/` and `reflection.md` are included.
- [ ] My README lets someone else run the project; my API key is not in the folder.
