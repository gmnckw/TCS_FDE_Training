"""Web UI for the expense claim reviewer (Streamlit).

    streamlit run app.py

Same building blocks as the CLI (store, agent, scoring); nothing here bypasses the
guardrails. Employee-written text is always shown with st.text (never rendered as
Markdown or HTML), because it is untrusted.
"""
from __future__ import annotations

import asyncio
import html
import json
from typing import Any

import streamlit as st

from expense_app import config, policy, scoring, store
from expense_app.agent import ReviewSession, review_prompt
from ui_theme import render_theme_toggle

st.set_page_config(page_title="Expense Claim Reviewer", page_icon="🧾", layout="wide")
config.ensure_dirs()
render_theme_toggle()          # bottom-left light/dark switch (ui_theme.py)

# Solid badge colours with white text: readable on both the light and the dark theme.
DECISION_COLOURS = {"approve": "#15803d", "reject": "#b91c1c", "needs_info": "#b45309", "escalate": "#6d28d9"}

# Layout styles shared by both themes (colours come from the theme, via currentColor).
st.markdown("""
<style>
.claim-fields { border-collapse: collapse; width: 100%; font-size: 0.92rem; margin-bottom: 0.6rem; }
.claim-fields th, .claim-fields td { text-align: left; padding: 0.3rem 0.6rem; vertical-align: top;
    border: none; border-bottom: 1px solid rgba(128,128,128,0.25); }
.claim-fields th { width: 38%; font-weight: 600; opacity: 0.75; }
.decision-head { font-size: 1.35rem; margin: 0.2rem 0 0.8rem 0; }
.decision-head small { font-size: 0.8rem; opacity: 0.7; margin-left: 0.4rem; }
.decision-badge { color: #fff; border-radius: 6px; padding: 0.15rem 0.55rem; font-weight: 700;
    letter-spacing: 0.03em; font-size: 1.05rem; }
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ agent runs with live progress
def run_agent(claim_id: str, prompt: str, resume: str | None, label: str) -> dict[str, Any] | None:
    """Run one agent turn, streaming each tool call into a status box as it happens."""
    with st.status(label, expanded=True) as box:
        lines: list[str] = []

        def echo(line: str) -> None:
            lines.append(line.strip())
            if line.strip().startswith("!!"):
                box.warning(line.strip()[3:])
            else:
                box.write(f"`{line.strip()[3:]}`" if line.strip().startswith("->") else line.strip())

        async def go() -> dict[str, Any]:
            async with ReviewSession(claim_id, resume=resume, echo=echo) as s:
                return await s.ask(prompt)

        try:
            summary = asyncio.run(go())
        except Exception as exc:  # surface SDK / MCP / budget errors in the page
            box.update(label=f"Failed: {type(exc).__name__}", state="error")
            st.error(f"{type(exc).__name__}: {exc}")
            return None
        box.update(label=f"{label} - done: {summary['turns']} turns, {len(summary['tools'])} tool calls, "
                         f"${summary['cost_usd']:.4f}", state="complete", expanded=False)
        return summary


# ------------------------------------------------------------------ small views
def show_claim(c: dict[str, Any]) -> None:
    # Every value is escaped and sits inside a raw HTML block, so employee-entered text
    # can never be rendered as Markdown, links or HTML.
    rows = [("Employee", c["employee"]), ("Amount", f"{c['amount']:.2f} {c['currency']}"),
            ("Expense date", c["expense_date"]), ("Receipt", c["receipt"]),
            ("Category (as entered)", c["category"]), ("Vendor", c["vendor"]),
            ("Pre-approval (as entered)", c.get("pre_approval") or "none"), ("Submitted", c["submitted_at"])]
    cells = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in rows)
    st.markdown(f'<table class="claim-fields">{cells}</table>', unsafe_allow_html=True)
    st.caption("Description (untrusted, shown as plain text):")
    st.text(c["description"])
    signals = policy.injection_signals(c["description"])
    if signals:
        st.warning(f"Instruction-like text detected in the claim: {signals}")


def show_decision(d: dict[str, Any]) -> None:
    colour = DECISION_COLOURS.get(d["decision"], "#6b7280")
    st.markdown(f'<div class="decision-head"><span class="decision-badge" style="background:{colour}">'
                f'{html.escape(d["decision"].upper())}</span> <b>${d["approved_amount_usd"]:.2f}</b> '
                f'<small>revision {d["revision"]} · saved {html.escape(d["saved_at"])}</small></div>',
                unsafe_allow_html=True)
    cols = st.columns(3)
    # "none" rather than "-": a lone "-" under a line turns that line into a Markdown heading.
    cols[0].markdown("**policy_refs**  \n" + (", ".join(d["policy_refs"]) or "none"))
    cols[1].markdown("**flags**  \n" + (", ".join(f"`{f}`" for f in d["flags"]) or "none"))
    esc = d["escalate_to"] + (f" ({d['escalation_reason']})" if d["escalate_to"] != "none" else "")
    cols[2].markdown("**escalate_to**  \n" + esc)
    with st.expander("Reviewer notes (for finance, not the employee)"):
        st.text(d.get("reviewer_notes", ""))
    st.markdown("**Draft reply to the employee**")
    st.code(d["reply_to_employee"], language=None, wrap_lines=True)


def show_approval(cid: str, d: dict[str, Any]) -> None:
    a = d.get("approval") or {"status": "pending_review"}
    st.subheader("Release the reply")
    if a["status"] == "approved":
        st.success(f"Approved by {a['by']} at {a['at']} (revision {a['revision']}). "
                   f"Released to `released/{cid}.reply.md`.")
    elif a["status"] == "changes_requested":
        st.warning(f"Changes requested by {a['by']}: {a.get('note', '')}. Ask the agent to revise it below.")
    else:
        st.info("Held: nobody has approved this reply yet. The agent cannot release it; only a person can.")
    name = st.text_input("Your name (finance reviewer)", key="reviewer_name")
    note = st.text_input("Note (required when requesting changes)", key=f"note_{cid}_{d['revision']}")
    c1, c2 = st.columns(2)
    if c1.button("Approve and release reply", type="primary", key=f"approve_{cid}", width="stretch",
                 disabled=a["status"] == "approved"):
        try:
            store.set_approval(cid, "approved", name, note)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if c2.button("Request changes (hold reply)", key=f"changes_{cid}", width="stretch"):
        try:
            store.set_approval(cid, "changes_requested", name, note)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def show_conversation(cid: str) -> None:
    st.subheader("Conversation with the agent")
    session = store.get_session(cid)
    for turn in store.load_chat(cid):
        is_review = turn["prompt"].startswith(("A new expense claim", "Expense claim"))
        with st.chat_message("user"):
            st.write("Review started" if is_review else turn["prompt"])
        with st.chat_message("assistant"):
            st.markdown(turn["answer"] or "_(no text)_")
            st.caption(f"{len(turn['tools'])} tool calls: {', '.join(turn['tools']) or '-'} · "
                       f"${turn['cost_usd']:.4f} · {turn['at']}")
    if not session:
        st.caption("Review the claim first to start a conversation.")
        return
    st.caption(f"Session {session[:8]}... is stored on disk, so this conversation survives a restart.")
    question = st.chat_input(f"Ask a follow-up about {cid}, e.g. 'why was the amount reduced?'")
    if question:
        before = (store.load_decision(cid) or {}).get("revision")
        if run_agent(cid, question, resume=session, label="Agent is answering"):
            after = (store.load_decision(cid) or {}).get("revision")
            if after != before:
                st.toast(f"Decision updated: revision {before} -> {after}. The reply needs approval again.")
            st.rerun()


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🧾 Expense reviewer")
    st.caption("The assistant only recommends. A finance reviewer decides and releases replies.")
    st.markdown(f"**Model** `{config.MODEL}`  \n**Limits** {config.MAX_TURNS} turns, "
                f"${config.MAX_BUDGET_USD:.2f} per run")
    if st.button("Load the 10 sample claims", width="stretch"):
        added = store.seed_samples()
        st.success(f"Added {len(added)}" if added else "Already loaded")
    runs = [json.loads(line) for line in config.RUNS_FILE.read_text("utf-8").splitlines()] \
        if config.RUNS_FILE.exists() else []
    st.metric("Agent spend so far", f"${sum(r.get('cost_usd', 0) for r in runs):.2f}", f"{len(runs)} runs",
              delta_color="off")

tab_claims, tab_new, tab_batch = st.tabs(["Claims", "New claim", "Batch & score"])

# ------------------------------------------------------------------ new claim (R1)
with tab_new:
    st.subheader("Enter a claim")
    with st.form("claim_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        employee = c1.text_input("Employee full name")
        expense_date = c2.date_input("Expense date", value=None, format="YYYY-MM-DD")
        category = c3.selectbox("Category", config.CATEGORIES)
        c4, c5, c6 = st.columns(3)
        vendor = c4.text_input("Vendor")
        amount = c5.number_input("Amount", min_value=0.0, step=0.01, format="%.2f")
        currency = c6.text_input("Currency (3 letters)", value="USD", max_chars=3)
        c7, c8 = st.columns(2)
        receipt = c7.radio("Receipt", ["attached", "missing"], horizontal=True)
        pre_approval = c8.text_input("Pre-approval number (optional)")
        description = st.text_area("Description: what was it, and why was it needed?")
        review_now = st.checkbox("Review it straight away", value=True)
        submitted = st.form_submit_button("Save claim", type="primary")
    if submitted:
        try:
            path = store.save_claim({"employee": employee, "expense_date": str(expense_date or ""),
                                     "category": category, "vendor": vendor, "amount": amount,
                                     "currency": currency, "receipt": receipt, "pre_approval": pre_approval,
                                     "description": description})
        except ValueError as exc:
            st.error(f"Not saved: {exc}")
        else:
            cid = path.stem
            st.success(f"Saved {cid} to inbox/{path.name}")
            st.session_state["selected"] = cid
            if review_now:
                run_agent(cid, review_prompt(cid), resume=None, label=f"Reviewing {cid}")
                d = store.load_decision(cid)
                if d:
                    show_decision(d)
                st.info("Open the Claims tab to ask follow-ups and approve the reply.")

# ------------------------------------------------------------------ claims list and detail (R2, R3)
with tab_claims:
    claims = store.list_claims("all")
    if not claims:
        st.info("The inbox is empty. Enter a claim, or load the sample claims from the sidebar.")
    else:
        rows = []
        for c in claims:
            d = store.load_decision(c["id"]) or {}
            rows.append({"claim": c["id"], "employee": c["employee"], "date": c["expense_date"],
                         "amount": f"{c['amount']:.2f} {c['currency']}", "vendor": c["vendor"],
                         "decision": d.get("decision", "pending"),
                         "approved_usd": d.get("approved_amount_usd"),
                         "escalate_to": d.get("escalate_to", ""),
                         "reply": (d.get("approval") or {}).get("status", "") if d else ""})
        st.dataframe(rows, width="stretch", hide_index=True)
        ids = [c["id"] for c in claims]
        default = ids.index(st.session_state["selected"]) if st.session_state.get("selected") in ids else 0
        cid = st.selectbox("Open claim", ids, index=default)
        st.session_state["selected"] = cid
        claim = store.load_claim(cid)
        decision = store.load_decision(cid)

        left, right = st.columns([1, 1], gap="large")
        with left:
            st.subheader(f"Claim {cid}")
            show_claim(claim)
            label = "Re-review from scratch" if decision else "Review this claim"
            if st.button(label, type="secondary" if decision else "primary", key=f"review_{cid}"):
                if run_agent(cid, review_prompt(cid, fresh=bool(decision)), resume=None, label=f"Reviewing {cid}"):
                    st.rerun()
        with right:
            if decision:
                st.subheader("Recommended decision")
                show_decision(decision)
                problems = policy.decision_problems(decision, claim)
                if problems:
                    st.error("Policy re-check failed: " + "; ".join(problems))
            else:
                st.info("No decision yet.")
        if decision:
            st.divider()
            a, b = st.columns([1, 1], gap="large")
            with a:
                show_conversation(cid)
            with b:
                show_approval(cid, decision)

# ------------------------------------------------------------------ batch mode and scoring
with tab_batch:
    st.subheader("Review everything pending")
    pending = store.list_claims("pending")
    st.write(f"{len(pending)} claim(s) pending.")
    if st.button("Review all pending claims", disabled=not pending, type="primary"):
        bar = st.progress(0.0)
        out = []
        for i, c in enumerate(pending, 1):
            s = run_agent(c["id"], review_prompt(c["id"]), resume=None, label=f"Reviewing {c['id']}")
            d = store.load_decision(c["id"]) or {}
            out.append({"claim": c["id"], "employee": c["employee"], "decision": d.get("decision", "ERROR"),
                        "approved_usd": d.get("approved_amount_usd"), "escalate_to": d.get("escalate_to"),
                        "flags": ", ".join(d.get("flags", [])), "cost_usd": round((s or {}).get("cost_usd", 0), 4)})
            bar.progress(i / len(pending))
        st.dataframe(out, width="stretch", hide_index=True)
        st.metric("Batch cost", f"${sum(r['cost_usd'] for r in out):.4f}")

    st.divider()
    st.subheader("Score against expected outcomes")
    st.caption("Compares saved decisions with tests/expected_samples.json (our own reading of the policy), "
               "field by field, and re-checks every reply against the hard stops.")
    source = st.radio("Decisions to score", ["outbox", "results"], horizontal=True)
    expected = scoring.load_expected()
    table = []
    for ecid, want in expected.items():
        got = scoring.load_decision_from(source, ecid)
        if not got:
            table.append({"claim": ecid, "score": 0.0, "notes": "no decision saved"})
            continue
        r = scoring.score_one(got, want, scoring.sample_claim(ecid))
        table.append({"claim": ecid, **{k: round(v, 2) for k, v in r["fields"].items()},
                      "reply_ok": r["reply_ok"], "score": round(r["total"], 2),
                      "notes": "; ".join(r["diffs"] + r["reply_problems"])})
    st.dataframe(table, width="stretch", hide_index=True)
    st.metric("Overall", f"{sum(t['score'] for t in table) / len(table):.1%}")
