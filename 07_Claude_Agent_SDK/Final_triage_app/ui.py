"""Streamlit front end for the support triage assistant.

    streamlit run triage_app/ui.py

Same app as the CLI - same inbox, outbox, sessions and agent - with a browser UI on
top. Nothing in store.py / agent.py / tools.py / hooks.py was changed for it, which
is the point of keeping those modules free of any front-end code.

How Streamlit shapes this file (worth knowing before editing it):

* Streamlit RE-RUNS THIS WHOLE SCRIPT on every click or keystroke. So nothing can live
  in a normal variable between interactions; anything that must survive goes in
  st.session_state, or on disk (the store already persists tickets, decisions and
  session ids).
* Because of that, we do NOT keep one agent connection open like the CLI chat does.
  Each action (triage, follow-up) opens a TriageSession, does its work, and closes it.
  Follow-ups still remember everything, because they `resume` the saved session id.
  Cost of this choice: ~3 seconds per action to start the MCP servers.
* Buttons use callbacks (on_click) for state changes, because a callback runs BEFORE the
  script re-runs, so widgets render with the new state on the very next pass.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# `streamlit run triage_app/ui.py` puts triage_app/ itself on sys.path, not its parent,
# so `import triage_app` would fail. Add the course root before importing the package.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402  (must come after the sys.path fix)

from Final_triage_app import config, store  # noqa: E402

# set_page_config must be the first Streamlit call in the script.
st.set_page_config(page_title="Support Triage", page_icon=":material/support_agent:", layout="wide")

OTHER = "Someone else..."                       # sentinel option in the customer dropdown
PRIORITY_COLOR = {"P1": "red", "P2": "orange", "P3": "blue", "P4": "gray"}
PRIORITY_LABEL = {"P1": "Critical", "P2": "High", "P3": "Normal", "P4": "Low"}
QUICK_FOLLOWUPS = ["Make the reply shorter", "Make the reply friendlier",
                   "Why did you pick this priority?"]


# ---------------------------------------------------------------- state & data

def init_state() -> None:
    """Create every session_state key once, so the rest of the code can assume they exist."""
    defaults = {
        "selected": None,        # ticket id being viewed, "new" for the form, None = welcome
        "auto_triage": None,     # ticket id the agent should run on at the next render
        "trace": {},             # ticket id -> list of tool-call lines the agent made
        "chat": {},              # ticket id -> follow-up conversation shown on screen
        "summary": {},           # ticket id -> the agent's closing note
        "meta": {},              # ticket id -> model / turns / cost of the last run
        "cost": 0.0,             # running USD total for this browser session
        "form_error": "",
        "pending_prompt": None,  # follow-up chosen via a quick-reply button
        # NOTE: the form's widget keys (f_choice, f_subject, ...) are deliberately NOT seeded
        # here. Pre-seeding a widget's key on an earlier run makes the server think it holds
        # that value while the browser draws the plain default - e.g. a checkbox that looks
        # unticked but is "on". Widgets get their defaults from their own `value=` argument.
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


@st.cache_data
def account_names() -> list[str]:
    """Customer names from data/accounts.json (the account lookup tool keys on these)."""
    return list(json.loads(config.ACCOUNTS_FILE.read_text(encoding="utf-8")).keys())


@st.cache_data
def sample_tickets() -> dict[str, dict]:
    """The course's sample tickets, by id, for the 'fill from a sample' helper."""
    data = json.loads(config.SAMPLE_TICKETS.read_text(encoding="utf-8"))
    return {t["id"]: t for t in data}


def run_async(coro):
    """Run a coroutine to completion from Streamlit's synchronous script thread.

    The agent SDK and the stdio MCP server both launch subprocesses. On Windows that only
    works on the Proactor event loop, but Streamlit's web server can leave the Selector
    policy installed, and a plain asyncio.run() would then fail with NotImplementedError.
    So on Windows we build a Proactor loop explicitly.
    """
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --------------------------------------------------------------- agent actions

def api_key_ok() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    st.error("ANTHROPIC_API_KEY is not set. Put it in `.env` or `notebooks/.env` and restart.")
    return False


def record_run(tid: str, s: dict) -> None:
    """Remember what the agent said and what the run cost, for display."""
    st.session_state.summary[tid] = s.get("text", "")
    st.session_state.meta[tid] = {"models": s.get("models", []), "turns": s["turns"],
                                  "tools": len(s["tools"]), "cost": s["cost_usd"],
                                  "outcome": s["subtype"]}
    st.session_state.cost += s["cost_usd"]


def run_triage(tid: str) -> bool:
    """Run the agent loop on a ticket, streaming each tool call into a live status panel."""
    if not api_key_ok():
        return False
    from Final_triage_app.agent import TriageSession, triage_prompt   # lazy: keeps first paint fast

    trace = st.session_state.trace[tid] = []
    with st.status(f"Agent loop running on {tid}...", expanded=True) as status:
        status.write("Starting the session and both MCP servers (about 3 seconds)...")

        def echo(line: str) -> None:        # called by TriageSession for every tool call
            trace.append(line.strip())
            status.write(f"`{line.strip()}`")

        async def go():
            async with TriageSession(tid, echo=echo) as session:
                return await session.ask(triage_prompt(tid))

        try:
            s = run_async(go())
        except Exception as exc:            # noqa: BLE001 - show any failure to the user
            status.update(label="Agent run failed", state="error")
            st.error(f"{type(exc).__name__}: {exc}")
            return False
        status.update(label=f"Done: {s['subtype']}, {s['turns']} turns, ${s['cost_usd']:.4f}",
                      state="complete", expanded=False)
    record_run(tid, s)
    return True


def run_follow_up(tid: str, prompt: str) -> tuple[bool, str]:
    """Send a follow-up message into the ticket's saved session and return the agent's answer."""
    if not api_key_ok():
        return False, ""
    from Final_triage_app.agent import TriageSession

    trace = st.session_state.trace.setdefault(tid, [])
    saved = store.get_session(tid)          # resume = same conversation, full memory

    async def go():
        async with TriageSession(tid, resume=saved,
                                 echo=lambda line: trace.append("(follow-up) " + line.strip())) as session:
            return await session.ask(prompt)

    try:
        with st.spinner("Agent is working (resuming the saved session)..."):
            s = run_async(go())
    except Exception as exc:                # noqa: BLE001
        st.error(f"{type(exc).__name__}: {exc}")
        return False, ""
    record_run(tid, s)
    return True, s.get("text") or "(the agent made the change without comment)"


# -------------------------------------------------------------------- callbacks

def select_ticket(tid: str) -> None:
    st.session_state.selected = tid


def start_new() -> None:
    st.session_state.selected = "new"


def load_samples() -> None:
    store.seed_samples()


def fill_from_sample() -> None:
    """Copy a sample ticket into the form fields (a demo convenience)."""
    t = sample_tickets().get(st.session_state.get("sample_pick"))
    if not t:
        return
    st.session_state.f_choice = t["customer"] if t["customer"] in account_names() else OTHER
    st.session_state.f_other = "" if t["customer"] in account_names() else t["customer"]
    st.session_state.f_subject = t["subject"]
    st.session_state.f_body = t["body"]


def submit_ticket() -> None:
    """Requirement 1: turn what the user typed into a file in the inbox."""
    ss = st.session_state
    choice = ss.get("f_choice")
    name = (ss.get("f_other", "") if choice == OTHER else choice or "").strip()
    subject, body = ss.get("f_subject", ""), ss.get("f_body", "")
    if not (name and subject.strip() and body.strip()):
        ss.form_error = "Please fill in the customer, subject and description."
        return
    path = store.save_ticket(name, subject, body, channel="web")
    ss.form_error = ""
    ss.selected = path.stem
    ss.auto_triage = path.stem if ss.get("f_auto", True) else None   # run the agent next render, or leave pending
    ss.f_subject = ss.f_body = ss.f_other = ""


def ask_quick(prompt: str) -> None:
    st.session_state.pending_prompt = prompt


# ---------------------------------------------------------------------- sidebar

def sidebar() -> None:
    with st.sidebar:
        st.markdown("### :material/support_agent: Support Triage")
        st.caption(f"Model: `{config.MODEL or 'SDK default'}`")
        st.button("New ticket", icon=":material/add:", type="primary", width="stretch", on_click=start_new)

        tickets = store.list_tickets("all")
        results = {t["id"]: store.load_result(t["id"]) for t in tickets}
        c1, c2, c3 = st.columns(3)
        c1.metric("Pending", sum(t["status"] == "pending" for t in tickets))
        c2.metric("Done", sum(t["status"] == "processed" for t in tickets))
        c3.metric("Escalated", sum(bool(r and r["escalate"]) for r in results.values()))

        st.divider()
        if not tickets:
            st.caption("No tickets yet.")
        # Newest first; the selected ticket is drawn as a filled (primary) button.
        for t in reversed(tickets):
            r = results[t["id"]]
            icon = ":material/check_circle:" if t["status"] == "processed" else ":material/schedule:"
            tag = f" [{r['priority']}]" if r else ""
            st.button(f"{t['id']}{tag}  {t.get('subject', '')[:26]}", icon=icon, key=f"sel_{t['id']}",
                      type="primary" if st.session_state.selected == t["id"] else "secondary",
                      width="stretch", on_click=select_ticket, args=(t["id"],))

        st.divider()
        st.button("Load the 8 sample tickets", icon=":material/download:", width="stretch",
                  on_click=load_samples, help="Copies data/tickets.json into the inbox (skips ones already there).")
        st.caption(f"Session spend: ${st.session_state.cost:.4f}")
        st.caption(f"Files: `{config.WORKSPACE}`")


# ------------------------------------------------------------------------ views

def welcome_view() -> None:
    st.title("Support Triage Assistant")
    st.write("Describe a customer problem. It is saved as a file, an agent loop picks it up, "
             "triages it and drafts a reply, and you can keep talking to the agent about it.")
    st.button("Submit a ticket", icon=":material/add:", type="primary", on_click=start_new)
    st.markdown(
        "**How it works**\n"
        "1. Your text is saved to `workspace/inbox/TKT-xxxx.md`.\n"
        "2. The agent reads it through an MCP server, searches the knowledge base, looks up the "
        "account, and decides category, priority and queue under the routing policy.\n"
        "3. The decision and draft reply are written to `workspace/outbox/` and shown here.\n"
        "4. Ask follow-ups - they resume the same agent session.")


def new_ticket_view() -> None:
    st.header("New ticket")
    names = account_names()
    if st.session_state.get("f_choice") is None:
        st.session_state.f_choice = names[0]     # set in the same run as the widget: this is safe

    with st.container(border=True):
        left, right = st.columns([3, 2], vertical_alignment="bottom")
        left.selectbox("Try a sample ticket (optional)", list(sample_tickets()), index=None,
                       key="sample_pick", placeholder="Pick one to fill in the form below",
                       format_func=lambda i: f"{i} - {sample_tickets()[i]['subject']}")
        right.button("Fill the form", on_click=fill_from_sample, icon=":material/edit_note:")

    st.selectbox("Customer", names + [OTHER], key="f_choice",
                 help="Names in the account database let the agent look up the plan and contract.")
    if st.session_state.f_choice == OTHER:
        st.text_input("Customer name", key="f_other", placeholder="Not in the account database - fine, the agent copes.")
    st.text_input("Subject", key="f_subject", placeholder="e.g. Charged twice for March")
    st.text_area("Describe the problem", key="f_body", height=180)
    st.checkbox("Run the agent as soon as I submit", value=True, key="f_auto",
                help="Untick to only save the file; you can run the agent later from the ticket page.")
    if st.session_state.form_error:
        st.warning(st.session_state.form_error)
    st.button("Submit ticket", type="primary", icon=":material/send:", on_click=submit_ticket)


def result_view(tid: str) -> None:
    """The decision card, the draft reply, and the agent's activity."""
    r = store.load_result(tid)
    color = PRIORITY_COLOR.get(r["priority"], "gray")

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        # Same metric style as the other two so the row lines up; the colour rides on a badge.
        c1.metric("Priority", r["priority"])
        c1.markdown(f":{color}-badge[{PRIORITY_LABEL.get(r['priority'], '')}]")
        c2.metric("Category", r["category"])
        c3.metric("Queue", r["queue"])
        if r["escalate"]:
            st.warning(f"**Escalated** to `{r['queue']}`. {r.get('escalation_reason', '')}")
        else:
            st.success("Handled at tier 1 - no escalation.")
        st.caption(f"KB used: {', '.join(r['kb_articles'])}  |  revision {r.get('revision', 1)}  |  saved {r['saved_at']}")

    st.markdown("#### Draft reply")
    with st.container(border=True):
        # Markdown folds single newlines into spaces; two trailing spaces keep the line breaks.
        st.markdown(r["draft_reply"].strip().replace("\n", "  \n"))
    reply_file = config.OUTBOX / f"{tid}.reply.md"
    left, right = st.columns([1, 3], vertical_alignment="center")
    if reply_file.exists():
        left.download_button("Download .md", reply_file.read_text(encoding="utf-8"),
                             file_name=reply_file.name, icon=":material/download:")
    right.caption(f"Saved at `{reply_file}`")

    meta = st.session_state.meta.get(tid)
    note = st.session_state.summary.get(tid)
    with st.expander("Agent activity", expanded=False):
        if meta:
            st.caption(f"Last run: {meta['outcome']} | {', '.join(meta['models']) or '?'} | "
                       f"{meta['turns']} turns | {meta['tools']} tool calls | ${meta['cost']:.4f}")
        if note:
            st.info(note)
        trace = st.session_state.trace.get(tid)
        # Use a real if/else, not a one-line conditional expression: Streamlit's "magic"
        # auto-wraps bare expression statements in st.write(), which breaks on those.
        if trace:
            st.code("\n".join(trace), language=None)
        else:
            st.caption("No activity recorded in this browser session (the agent ran earlier or "
                       f"from the CLI). Full history: `{config.AUDIT_FILE}`")


def chat_view(tid: str) -> None:
    """Follow-up conversation with the agent (resumes the ticket's saved session)."""
    st.markdown("#### Ask the agent")
    history = st.session_state.chat.setdefault(tid, [])
    for msg in history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    st.caption("Quick asks:")
    cols = st.columns(len(QUICK_FOLLOWUPS))
    for col, text in zip(cols, QUICK_FOLLOWUPS):
        col.button(text, key=f"quick_{text}", on_click=ask_quick, args=(text,), width="stretch")

    # chat_input returns the typed text once, then None; a quick-ask button feeds the same path.
    prompt = st.chat_input("e.g. Make it two sentences, or: should this be escalated?")
    prompt = prompt or st.session_state.pop("pending_prompt", None)
    if not prompt:
        return

    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        ok, answer = run_follow_up(tid, prompt)
        if ok:
            history.append({"role": "assistant", "content": answer})
    if ok:
        st.rerun()        # re-render so the result card shows any revision the agent saved


def ticket_view(tid: str) -> None:
    path = store.find_ticket(tid)
    if path is None:
        st.session_state.selected = None
        st.rerun()
    t = store.parse_ticket(path)

    st.header(f"{tid}  -  {t.get('subject', '')}")
    st.caption(f"{t.get('customer')}  |  via {t.get('channel')}  |  received {t.get('received_at')}  |  "
               f"**{t['status']}**")

    # Triage queued by submit / "Run the agent": clear the flag FIRST so a failure cannot loop forever.
    if st.session_state.auto_triage == tid:
        st.session_state.auto_triage = None
        triaged = run_triage(tid)
        if triaged:
            st.rerun()

    has_result = store.load_result(tid) is not None
    with st.expander("Customer's ticket (the saved file)", expanded=not has_result):
        st.text(t["body"])        # st.text shows it verbatim: no markdown/HTML interpretation of user text
        st.caption(f"`{t['path']}`")

    if not has_result:
        st.info("The agent has not triaged this ticket yet.")
        if st.button("Run the agent", type="primary", icon=":material/play_arrow:"):
            st.session_state.auto_triage = tid
            st.rerun()
        return

    result_view(tid)
    st.divider()
    chat_view(tid)


# ------------------------------------------------------------------------- main

def main() -> None:
    init_state()
    sidebar()
    sel = st.session_state.selected
    if sel == "new":
        new_ticket_view()
    elif sel:
        ticket_view(sel)
    else:
        welcome_view()


main()
