"""Streamlit chat app for Claude (Day 10 task).

Sidebar controls: model, effort, thinking on/off, system instruction.
Every message builds the API request from the current sidebar values,
streams Claude's reply into the chat, and keeps the full conversation.

Run:  streamlit run app.py
"""

import anthropic
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from a .env file next to this script (or a parent folder)

MAX_TOKENS = 64000  # streaming, so a high ceiling is safe
EFFORT_LEVELS = ["low", "medium", "high", "xhigh", "max"]
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# How each model handles "thinking off" differs, so it is described per model:
#   thinking_off = None  -> the model always thinks; "off" only hides the reasoning
#   thinking_off = {...} -> the config that turns thinking off (allowed at effort <= high)
#   fallback             -> on a safety refusal, let the API retry on another model
MODELS = {
    "Claude Opus 5.5": {"id": "claude-opus-5-5", "thinking_off": None, "default_effort": "medium", "fallback": True},
    "Claude Sonnet 5.5": {"id": "claude-sonnet-5-5", "thinking_off": {"type": "between_tools"}, "default_effort": "high", "fallback": True},
    "Claude Haiku 5.5": {"id": "claude-haiku-5-5", "thinking_off": {"type": "disabled"}, "default_effort": "medium", "fallback": False},
}


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


# ---------------------------------------------------------------- session state
if "messages" not in st.session_state:
    st.session_state.messages = []  # API-format history (assistant turns keep thinking blocks)
    st.session_state.conversation_system = None  # system prompt the history was produced with
    st.session_state.last_request = None


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")

    model_name = st.selectbox("Model", list(MODELS))
    model = MODELS[model_name]

    thinking_on = st.toggle("Thinking", value=True)
    if not thinking_on and model["thinking_off"] is None:
        st.caption(f"{model_name} always thinks. Turning this off only hides the reasoning.")

    # A real "thinking off" setting is only accepted at effort high or below.
    effort_choices = EFFORT_LEVELS
    if not thinking_on and model["thinking_off"] is not None:
        effort_choices = EFFORT_LEVELS[:3]
    default = model["default_effort"] if model["default_effort"] in effort_choices else effort_choices[-1]
    effort = st.select_slider("Effort", options=effort_choices, value=default)

    system_prompt = st.text_area(
        "System instruction",
        value="You are a helpful assistant.",
        height=150,
    )

    if st.button("Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_system = None
        st.session_state.last_request = None
        st.rerun()

    if st.session_state.last_request:
        with st.expander("Last request sent"):
            st.json(st.session_state.last_request)


# ---------------------------------------------------------------- helpers
def build_request(messages: list) -> dict:
    """Combine model, messages, system instruction, effort and thinking into one request."""
    params = {
        "model": model["id"],
        "max_tokens": MAX_TOKENS,
        "messages": messages,
        "output_config": {"effort": effort},
    }
    if system_prompt.strip():
        params["system"] = system_prompt.strip()

    if thinking_on:
        params["thinking"] = {"type": "adaptive", "display": "summarized"}
    elif model["thinking_off"] is not None:
        params["thinking"] = model["thinking_off"]
    # else: model always thinks; omit `thinking` (reasoning comes back hidden)

    # Server-side refusal fallback. Skipped with `between_tools`, which only
    # Sonnet 5.5 accepts, so a fallback model could not take the same request.
    if model["fallback"] and params.get("thinking", {}).get("type") != "between_tools":
        params["betas"] = [FALLBACK_BETA]
        params["fallbacks"] = "default"
    return params


def strip_thinking(messages: list) -> list:
    """Remove thinking blocks from earlier assistant turns.

    A thinking block is only valid with the exact system prompt it was produced
    under, so when the system instruction changes mid-chat we drop them.
    """
    cleaned = []
    for m in messages:
        if m["role"] == "assistant" and isinstance(m["content"], list):
            content = [b for b in m["content"] if b.get("type") not in ("thinking", "redacted_thinking")]
            cleaned.append({"role": "assistant", "content": content or [{"type": "text", "text": ""}]})
        else:
            cleaned.append(m)
    return cleaned


def render_assistant(content: list) -> None:
    thinking = "".join(b.get("thinking", "") for b in content if b.get("type") == "thinking")
    if thinking.strip():
        with st.expander("Thinking"):
            st.markdown(thinking)
    st.markdown("".join(b.get("text", "") for b in content if b.get("type") == "text"))


# ---------------------------------------------------------------- chat history
st.title("Claude Chat")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m["role"] == "user":
            st.markdown(m["content"])
        else:
            render_assistant(m["content"])


# ---------------------------------------------------------------- new message
if prompt := st.chat_input("Ask Claude something..."):
    with st.chat_message("user"):
        st.markdown(prompt)

    # Changed system instruction -> earlier thinking blocks no longer match it.
    current_system = system_prompt.strip()
    if st.session_state.messages and st.session_state.conversation_system != current_system:
        st.session_state.messages = strip_thinking(st.session_state.messages)
    st.session_state.conversation_system = current_system

    st.session_state.messages.append({"role": "user", "content": prompt})
    params = build_request(st.session_state.messages)
    st.session_state.last_request = {k: v for k, v in params.items() if k != "messages"} | {
        "messages": f"[{len(params['messages'])} messages]"
    }

    with st.chat_message("assistant"):
        thinking_box = st.expander("Thinking", expanded=False) if thinking_on else None
        thinking_area = thinking_box.empty() if thinking_box else None
        text_area = st.empty()
        thinking_text, reply_text = "", ""

        try:
            with get_client().beta.messages.stream(**params) as stream:
                for event in stream:
                    if event.type != "content_block_delta":
                        continue
                    if event.delta.type == "thinking_delta" and thinking_area:
                        thinking_text += event.delta.thinking
                        thinking_area.markdown(thinking_text)
                    elif event.delta.type == "text_delta":
                        reply_text += event.delta.text
                        text_area.markdown(reply_text + "▌")
                final = stream.get_final_message()
            text_area.markdown(reply_text)

            if final.stop_reason == "refusal":
                st.session_state.messages.pop()  # keep history valid; let the user rephrase
                st.warning("Claude declined to answer this request. Try rephrasing it.")
            else:
                if final.model != model["id"]:
                    st.caption(f"Answered by fallback model {final.model}")
                if final.stop_reason == "max_tokens":
                    st.caption("Reply was cut off at the max_tokens limit.")
                # Keep the full content (thinking blocks included) so the next turn can reuse it.
                st.session_state.messages.append(
                    {"role": "assistant", "content": [b.to_dict() for b in final.content]}
                )
        except anthropic.AuthenticationError:
            st.session_state.messages.pop()
            st.error("Authentication failed. Set ANTHROPIC_API_KEY in a .env file (see .env.example).")
        except anthropic.BadRequestError as e:
            st.session_state.messages.pop()
            st.error(f"Request rejected: {e.message}")
        except anthropic.RateLimitError:
            st.session_state.messages.pop()
            st.error("Rate limited. Wait a moment and try again.")
        except anthropic.APIStatusError as e:
            st.session_state.messages.pop()
            st.error(f"API error ({e.status_code}): {e.message}")
        except anthropic.APIConnectionError:
            st.session_state.messages.pop()
            st.error("Network error. Check your internet connection.")
