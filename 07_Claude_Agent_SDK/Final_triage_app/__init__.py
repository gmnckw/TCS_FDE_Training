"""Support Ticket Triage Assistant - a small Claude Agent SDK app.

User content is saved as a local file, an agent loop triages it and drafts a
reply, and the result is handed back to the user. Built on: sessions
(ClaudeSDKClient + resume), MCP (one external stdio server, one in-process
SDK server), custom tools, and hooks.

Module map (read in this order):
    config.py          paths, env loading, model choice
    store.py           the local file store: tickets, results, session ids
    ticket_store_mcp.py  EXTERNAL MCP server (separate process) over the inbox
    tools.py           IN-PROCESS MCP server: KB search, account lookup, save
    hooks.py           guardrails that run around every tool call
    agent.py           system prompt, agent options, resumable TriageSession
    ui.py              the Streamlit web front end (`streamlit run triage_app/ui.py`)

ui.py is the only front end. It holds no agent logic - it just collects input, calls
store.py and agent.py, and renders the results - so another front end could be added
over the same modules without touching them.
"""
