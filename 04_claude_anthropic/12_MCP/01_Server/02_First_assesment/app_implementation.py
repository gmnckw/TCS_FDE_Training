"""Core logic of the IT Helpdesk chatbot (no Streamlit code in this file).

Pieces:
  - RAG:        it_sector.txt -> chunks -> Voyage AI embeddings -> in-memory vector DB (numpy)
  - MCP:        mcp_server.py started as a subprocess; a persistent session keeps tickets alive
  - Tools:      web_search (Anthropic server-side tool), get_current_datetime (client tool),
                create_support_ticket / check_ticket_status (forwarded to the MCP server)
  - LLM:        Anthropic Messages API; the model decides which tools to call.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import datetime as dt
import json
import os
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import numpy as np
import voyageai
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

FAQ_FILE = BASE_DIR / "it_sector.txt"
MCP_SERVER_FILE = BASE_DIR / "mcp_server.py"

MODELS = ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"]
DEFAULT_MODEL = "claude-sonnet-5-5"
EMBED_MODEL = "voyage-3.5"
TOP_K = 3

# Server-side tool: Anthropic runs the search and returns the results to the model.
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}

# Client-side tool: executed locally by this app.
DATETIME_TOOL = {
    "name": "get_current_datetime",
    "description": "Return the current local date and time. Use it for any question about today's date or the current time.",
    "input_schema": {"type": "object", "properties": {}},
}

SYSTEM_PROMPT = """You are the IT Helpdesk Assistant for company employees.

How to answer:
- Each question comes with "FAQ context" retrieved from the IT support FAQ. Use it first and cite the FAQ section title when you rely on it.
- Call web_search only when the FAQ does not cover the problem, or the employee asks for the latest or external solutions. Cite the URLs you used.
- Call get_current_datetime for questions about today's date or time.
- Call create_support_ticket when the employee asks to raise or create a ticket. You need the employee's name and the issue; ask for them if missing. Use priority Low, Medium or High (default Medium).
- Call check_ticket_status when the employee asks about a ticket ID such as IT-101.
- Never invent ticket IDs, statuses or dates. Report only what the tools return.

Format:
- Start with a one-sentence answer.
- For troubleshooting, give short numbered steps.
- Keep replies concise and friendly."""


# --------------------------------------------------------------------------- RAG
def load_faq_chunks(path: Path = FAQ_FILE) -> list[str]:
    """Split the FAQ into one chunk per '## ' section (heading + Q + A)."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    return [part.strip() for part in parts if part.strip()]


class VectorStore:
    """Tiny vector database: normalised Voyage embeddings held in a numpy matrix."""

    def __init__(self, chunks: list[str], vo: voyageai.Client):
        self.vo = vo
        self.chunks = chunks
        result = vo.embed(chunks, model=EMBED_MODEL, input_type="document")
        matrix = np.asarray(result.embeddings, dtype=np.float32)
        self.matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)

    def search(self, query: str, k: int = TOP_K) -> list[tuple[str, float]]:
        result = self.vo.embed([query], model=EMBED_MODEL, input_type="query")
        q = np.asarray(result.embeddings[0], dtype=np.float32)
        q = q / np.linalg.norm(q)
        scores = self.matrix @ q
        top = np.argsort(-scores)[:k]
        return [(self.chunks[i], float(scores[i])) for i in top]


# --------------------------------------------------------------------------- MCP
class MCPBridge:
    """Keeps one MCP client session open on a background event loop.

    Streamlit runs on its own threads, so calls are marshalled onto the loop with
    run_coroutine_threadsafe. A single long-lived server process means tickets
    created in one call are still there for the next call.
    """

    def __init__(self, server_file: Path = MCP_SERVER_FILE, timeout: float = 60):
        self.timeout = timeout
        # The subprocess transport needs the Proactor loop on Windows.
        loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
        self.loop = loop
        self.thread = threading.Thread(target=loop.run_forever, name="mcp-loop", daemon=True)
        self.thread.start()

        self.tools: list[dict[str, Any]] = []
        self._session: ClientSession | None = None
        self._ready: concurrent.futures.Future = concurrent.futures.Future()
        self._stop: concurrent.futures.Future = concurrent.futures.Future()
        # One task owns the whole session lifecycle, so enter and exit happen in the same task.
        asyncio.run_coroutine_threadsafe(self._lifecycle(server_file), loop)
        self._ready.result(timeout)

    async def _lifecycle(self, server_file: Path) -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(server_file)],
            cwd=str(server_file.parent),
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    self._session = session
                    self.tools = [
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "input_schema": tool.input_schema,
                        }
                        for tool in listed.tools
                    ]
                    self._ready.set_result(True)
                    await asyncio.wrap_future(self._stop)  # keep the session open until close()
        except Exception as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)
            else:
                raise

    def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Call an MCP tool. Returns (text, is_error)."""

        async def _call():
            return await self._session.call_tool(name, arguments)

        result = asyncio.run_coroutine_threadsafe(_call(), self.loop).result(self.timeout)
        text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
        return text, bool(result.is_error)

    def close(self) -> None:
        if not self._stop.done():
            self._stop.set_result(None)


# --------------------------------------------------------------------------- Resources
@dataclass
class Resources:
    client: anthropic.Anthropic
    store: VectorStore
    bridge: MCPBridge


def build_resources() -> Resources:
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    voyage_key = os.getenv("VOYAGE_API_KEY")
    if not anthropic_key or not voyage_key:
        raise RuntimeError("ANTHROPIC_API_KEY and VOYAGE_API_KEY must be set in .env")

    client = anthropic.Anthropic(api_key=anthropic_key)
    # max_retries: Voyage rate-limits accounts without billing to a few requests per minute,
    # so retry with exponential backoff instead of failing the first question.
    voyage = voyageai.Client(api_key=voyage_key, max_retries=8)
    store = VectorStore(load_faq_chunks(), voyage)
    bridge = MCPBridge()
    return Resources(client=client, store=store, bridge=bridge)


# --------------------------------------------------------------------------- Chat
def _local_datetime() -> str:
    now = dt.datetime.now().astimezone()
    return json.dumps(
        {
            "date": now.strftime("%A, %d %B %Y"),
            "time": now.strftime("%H:%M:%S"),
            "iso": now.isoformat(timespec="seconds"),
            "timezone": now.tzname(),
        }
    )


def _run_client_tool(name: str, args: dict[str, Any], res: Resources) -> tuple[str, bool]:
    if name == "get_current_datetime":
        return _local_datetime(), False
    try:
        return res.bridge.call_tool(name, args)
    except Exception as exc:  # surface MCP failures to the model instead of crashing
        return f"Tool '{name}' failed: {exc}", True


def _faq_context(question: str, res: Resources) -> tuple[str, list[str]]:
    hits = res.store.search(question)
    titles = [chunk.splitlines()[0] for chunk, _ in hits]
    block = "\n\n".join(f"[score {score:.2f}]\n{chunk}" for chunk, score in hits)
    return block, titles


def ask(question: str, history: list[dict[str, str]], res: Resources, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Answer one employee question.

    history: prior turns as {"role", "content"} text dicts (no RAG context stored).
    Returns {"answer", "tool_calls", "faq_sections", "sources"}.
    """
    faq_block, faq_sections = _faq_context(question, res)
    user_turn = f"FAQ context (retrieved from it_sector.txt):\n{faq_block}\n\nEmployee question: {question}"
    messages: list[dict[str, Any]] = [*history, {"role": "user", "content": user_turn}]

    tools = [WEB_SEARCH_TOOL, DATETIME_TOOL, *res.bridge.tools]
    tool_calls: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []

    while True:
        response = res.client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
        # Echo the assistant turn back exactly (server tool blocks must be preserved).
        messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in response.content]})

        for block in response.content:
            if block.type == "server_tool_use":
                tool_calls.append({"name": block.name, "input": block.input, "output": "run by Anthropic (web search)"})
            elif block.type == "web_search_tool_result" and isinstance(block.content, list):
                for item in block.content:
                    if getattr(item, "url", None):
                        sources.append({"title": item.title, "url": item.url})

        if response.stop_reason == "pause_turn":  # server tool loop hit its limit; resume
            continue
        if response.stop_reason != "tool_use":
            break

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            output, is_error = _run_client_tool(block.name, block.input, res)
            tool_calls.append({"name": block.name, "input": block.input, "output": output})
            results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error}
            )
        messages.append({"role": "user", "content": results})

    answer = "".join(b.text for b in response.content if b.type == "text").strip()
    return {
        "answer": answer,
        "tool_calls": tool_calls,
        "faq_sections": faq_sections,
        "sources": sources,
    }
