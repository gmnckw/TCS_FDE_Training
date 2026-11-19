"""IT Helpdesk MCP Server.

Exposes two tools over MCP (stdio transport):
  - create_support_ticket(employee, issue, description, priority) -> new ticket
  - check_ticket_status(ticket_id)                                -> ticket status

Tickets are stored in an in-memory Python dict. It is seeded from
mcp_tool_data.json (IT-101..IT-103) when that file sits next to this script.

Run standalone (normally started by app_implementation.py):
    python mcp_server.py
"""

import json
from pathlib import Path

from mcp.server import MCPServer

SEED_FILE = Path(__file__).with_name("mcp_tool_data.json")
VALID_PRIORITIES = ("Low", "Medium", "High")

mcp_server = MCPServer(name="IT Helpdesk MCP Server", version="1.0.0")

# In-memory ticket store: {"IT-101": {...}, ...}
TICKETS: dict[str, dict] = {}


def _seed_tickets() -> None:
    if SEED_FILE.exists():
        for ticket in json.loads(SEED_FILE.read_text(encoding="utf-8")):
            TICKETS[ticket["ticket_id"]] = ticket


def _next_ticket_id() -> str:
    numbers = [
        int(tid.split("-", 1)[1])
        for tid in TICKETS
        if tid.startswith("IT-") and tid.split("-", 1)[1].isdigit()
    ]
    return f"IT-{max(numbers, default=100) + 1}"


_seed_tickets()


@mcp_server.tool(
    name="create_support_ticket",
    description="Create a new IT support ticket for an employee. Returns the new ticket as JSON.",
)
def create_support_ticket(
    employee: str,
    issue: str,
    description: str = "",
    priority: str = "Medium",
) -> str:
    priority = (priority or "Medium").strip().capitalize()
    if priority not in VALID_PRIORITIES:
        return json.dumps({"error": f"priority must be one of {', '.join(VALID_PRIORITIES)}"})

    ticket = {
        "ticket_id": _next_ticket_id(),
        "employee": employee.strip(),
        "issue": issue.strip(),
        "description": description.strip(),
        "priority": priority,
        "status": "Open",
    }
    TICKETS[ticket["ticket_id"]] = ticket
    return json.dumps(ticket)


@mcp_server.tool(
    name="check_ticket_status",
    description="Look up an existing IT support ticket by its ID (e.g. IT-101) and return its status.",
)
def check_ticket_status(ticket_id: str) -> str:
    ticket = TICKETS.get(ticket_id.strip().upper())
    if ticket is None:
        return json.dumps({"error": f"Ticket {ticket_id} not found"})
    return json.dumps(ticket)


if __name__ == "__main__":
    # stdio transport: the chatbot launches this file as a subprocess.
    # Nothing may be printed to stdout here, it carries the MCP protocol.
    mcp_server.run(transport="stdio")
