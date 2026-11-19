"""Streamlit chat UI for the IT Helpdesk Assistant.

Run from this folder:
    streamlit run streamlit.py
"""

import json

import streamlit as st

from app_implementation import DEFAULT_MODEL, MODELS, ask, build_resources

st.set_page_config(page_title="IT Helpdesk Assistant", page_icon="🛠️", layout="centered")


@st.cache_resource(show_spinner="Starting helpdesk: embedding the FAQ and launching the MCP server...")
def get_resources():
    return build_resources()


TOOL_LABELS = {
    "web_search": "🌐 Web search",
    "get_current_datetime": "🕒 Date & time",
    "create_support_ticket": "🎫 New ticket",
    "check_ticket_status": "🔎 Ticket status",
}

st.title("🛠️ IT Helpdesk Assistant")
st.caption("Answers from the IT FAQ (RAG) · web search for extra fixes · MCP tools for tickets")

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("Settings")
    model = st.selectbox("Claude model", MODELS, index=MODELS.index(DEFAULT_MODEL))
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.markdown("**Try asking:**")
    st.markdown(
        "- How do I fix network connectivity issues?\n"
        "- My computer is running slow. What should I do?\n"
        "- Search for the latest Windows 11 Wi-Fi troubleshooting steps.\n"
        "- Create a ticket for my laptop running slowly. My name is Sam.\n"
        "- Check the status of ticket IT-101.\n"
        "- What is the current date and time?"
    )


def render_extras(msg: dict) -> None:
    """Show tool calls, FAQ sections and web sources under an assistant reply."""
    if msg.get("tool_calls"):
        with st.expander(f"Tools used ({len(msg['tool_calls'])})"):
            for call in msg["tool_calls"]:
                label = TOOL_LABELS.get(call["name"], call["name"])
                st.markdown(f"**{label}** `{call['name']}`")
                st.code(json.dumps(call["input"], indent=2), language="json")
                st.caption("Output")
                st.code(call["output"], language="json")
    if msg.get("faq_sections"):
        st.caption("FAQ sections consulted: " + " · ".join(s.lstrip("# ").strip() for s in msg["faq_sections"]))
    if msg.get("sources"):
        st.caption("Web sources: " + " · ".join(f"[{s['title']}]({s['url']})" for s in msg["sources"][:5]))


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            render_extras(msg)

if prompt := st.chat_input("Describe your IT issue or ask about a ticket..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Plain-text history for the model (extras are UI-only).
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]

    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking..."):
                result = ask(prompt, history, get_resources(), model=model)
            reply = {"role": "assistant", "content": result["answer"] or "_(no answer returned)_", **result}
        except Exception as exc:
            reply = {"role": "assistant", "content": f"Sorry, something went wrong: `{exc}`"}
        st.markdown(reply["content"])
        render_extras(reply)

    st.session_state.messages.append(reply)
