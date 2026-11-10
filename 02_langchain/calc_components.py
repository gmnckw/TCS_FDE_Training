"""Reusable building blocks for the Day-4 calculator use case.

Notebooks import from here instead of rebuilding the model, tools and agent every time:

    from calc_components import get_model, build_calculator_agent, ask
"""

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_aws import ChatBedrockConverse
from langchain_core.tools import tool

DEFAULT_MODEL_ID = "amazon.nova-lite-v1:0"


def get_model(model_id=DEFAULT_MODEL_ID, temperature=0, max_tokens=512, **kwargs):
    """One place to configure the Bedrock model. Extra kwargs go straight to ChatBedrockConverse."""
    load_dotenv()  # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    return ChatBedrockConverse(
        model=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


@tool
def add(a: float, b: float) -> float:
    """Add two numbers: a + b."""
    return a + b


@tool
def subtract(a: float, b: float) -> float:
    """Subtract b from a: a - b."""
    return a - b


@tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers: a * b."""
    return a * b


@tool
def divide(a: float, b: float) -> str | float:
    """Divide a by b: a / b."""
    if b == 0:
        return "Error: cannot divide by zero"
    return a / b


CALCULATOR_TOOLS = [add, subtract, multiply, divide]

CALCULATOR_PROMPT = """You are a calculator assistant.

Rules:
- ALWAYS use the tools (add, subtract, multiply, divide) for arithmetic. Never calculate in your head.
- Call ONE tool at a time.
- If the user says 'that', 'it' or 'the result', use the result of the previous calculation in this conversation.
- If you do not know which number the user means, ask them. Do not guess.
- After the tool returns, reply with a short sentence containing the answer.
"""


def build_calculator_agent(
    model=None,
    *,
    system_prompt=CALCULATOR_PROMPT,
    tools=None,
    checkpointer=None,
    middleware=(),
    response_format=None,
):
    """Build the calculator agent. Every option has a sensible default, so the simplest call is `build_calculator_agent()`."""
    return create_agent(
        model=model or get_model(),
        tools=CALCULATOR_TOOLS if tools is None else tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        middleware=list(middleware),
        response_format=response_format,
    )


def ask(agent, question, thread_id=None, verbose=True):
    """Send one question and return the full result. Pass thread_id only for an agent with a checkpointer."""
    config = {"configurable": {"thread_id": thread_id}} if thread_id else None
    result = agent.invoke({"messages": [{"role": "user", "content": question}]}, config)

    if verbose:
        msgs = result["messages"]
        turn = msgs[max(i for i, m in enumerate(msgs) if m.type == "human"):]
        print(f"\n>>> {question}")
        for m in turn:
            for call in getattr(m, "tool_calls", []) or []:
                print(f"    tool call: {call['name']}({call['args']})")
        print(f"    ANSWER: {msgs[-1].text}")
    return result
