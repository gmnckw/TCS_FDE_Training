# Day 10 Task: Streamlit chat app with Claude

A chat UI where you choose the Claude model, effort level, thinking on/off, and system instruction from the sidebar. Each message builds the API request from those settings, then streams the reply.

## Run it

```bash
cd 04_claude_anthropic/10_streamlit_chat_app
pip install -r requirements.txt
cp .env.example .env        # then put your real key in .env
streamlit run app.py
```

## Sidebar settings and the request they build

| Sidebar | Request field |
|---|---|
| Model | `model` |
| Effort | `output_config.effort` |
| Thinking on | `thinking: {"type": "adaptive", "display": "summarized"}`; the reasoning shows in a "Thinking" expander |
| Thinking off | Depends on the model (see below) |
| System instruction | `system` |
| Chat history | `messages` |

Open **Last request sent** in the sidebar to see the exact settings used for the last message.

### Thinking off on each model

| Model | What "off" sends |
|---|---|
| Opus 5.5 | This model always thinks. The app leaves out `thinking` and hides the reasoning. |
| Sonnet 5.5 | `{"type": "between_tools"}` (effort can only be low, medium or high) |
| Haiku 5.5 | `{"type": "disabled"}` (effort can only be low, medium or high) |

## Other behavior

- **Refusal fallback:** On Opus 5.5 and Sonnet 5.5 (with thinking on), requests include `fallbacks: "default"`. If Claude declines for a safety reason, the API retries on another model.
- **Multi-turn memory:** Earlier assistant turns are sent back with their thinking blocks. If you change the system instruction partway through a chat, those blocks are removed, because they only work with the system prompt they were created under.
