from __future__ import annotations

import json
import os
from typing import Any

from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.agents import AgentFinish
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.analytics import calculate_spending_next_days
from app.analytics import find_most_expensive_category
from app.analytics import list_payments_next_days
from app.settings import get_current_date
from app.tools import CurrencyConversionError
from app.tools import convert_currency as convert_currency_core
from app.tools import get_obligations as get_obligations_core

load_dotenv()


@tool("get_obligations")
def get_obligations_tool(tool_input: str = "") -> str:
    """Return user obligations from JSON. Input JSON: {"status": "...", "category": "..."}."""
    payload = _parse_tool_input(tool_input)
    obligations = get_obligations_core(
        status=payload.get("status"),
        category=payload.get("category"),
    )
    return json.dumps(obligations, ensure_ascii=False, indent=2)


@tool("convert_currency")
def convert_currency_tool(tool_input: str = "") -> str:
    """Convert money. Input JSON: {"amount": 10.0, "from_currency": "USD", "to_currency": "RUB"}."""
    payload = _parse_tool_input(tool_input)
    try:
        converted = convert_currency_core(
            float(payload["amount"]),
            str(payload["from_currency"]),
            str(payload["to_currency"]),
        )
    except (CurrencyConversionError, KeyError, TypeError, ValueError) as exc:
        return f"ERROR: {exc}. Report that the conversion is unavailable; do not invent a rate."
    return str(converted)


@tool("calculate_spending_next_days")
def calculate_spending_next_days_tool(tool_input: str = "") -> str:
    """Deterministically calculate active spending for next N days. Input JSON: {"days": 30, "target_currency": "RUB"}."""
    payload = _parse_tool_input(tool_input)
    result = calculate_spending_next_days(
        days=int(payload.get("days", 30)),
        target_currency=str(payload.get("target_currency", "RUB")),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool("find_most_expensive_category")
def find_most_expensive_category_tool(tool_input: str = "") -> str:
    """Deterministically find the most expensive active category. Input JSON: {"target_currency": "RUB"}."""
    payload = _parse_tool_input(tool_input)
    result = find_most_expensive_category(
        target_currency=str(payload.get("target_currency", "RUB")),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool("list_payments_next_days")
def list_payments_next_days_tool(tool_input: str = "") -> str:
    """Deterministically list active payments for next N days. Input JSON: {"days": 7}."""
    payload = _parse_tool_input(tool_input)
    result = list_payments_next_days(days=int(payload.get("days", 7)))
    return json.dumps(result, ensure_ascii=False, indent=2)


TOOLS = [
    get_obligations_tool,
    convert_currency_tool,
    calculate_spending_next_days_tool,
    find_most_expensive_category_tool,
    list_payments_next_days_tool,
]


def _parse_tool_input(tool_input: str | dict[str, Any] | None) -> dict[str, Any]:
    if tool_input is None or tool_input == "":
        return {}

    if isinstance(tool_input, dict):
        return tool_input

    try:
        parsed = json.loads(tool_input)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


REACT_PROMPT = PromptTemplate.from_template(
    """You are an AI agent for a smart registry of subscriptions and recurring payments.
Answer in Russian. Use tools whenever the user asks about obligations, dates, totals,
categories, currencies, or payment status.

Current date: {current_date}
Default target currency: RUB

Rules:
- Use only the data returned by tools.
- For the three common scenarios, prefer deterministic business tools:
  calculate_spending_next_days, find_most_expensive_category, list_payments_next_days.
- Use get_obligations and convert_currency directly for custom analysis that is not covered
  by the deterministic business tools.
- For date ranges, compare next_payment_date with the current date.
- Interpret "this week" / "на этой неделе" as the next 7 days including current date,
  unless the user explicitly asks for a calendar week.
- For totals across currencies, convert every non-target currency item before summing.
- Never estimate exchange rates yourself and never write "conditional" or "assumed" rates.
- For category comparisons, aggregate obligations by category and currency first, then call
  convert_currency for every non-RUB category/currency subtotal before comparing categories.
- A category comparison final answer is invalid unless you have received an Observation from
  convert_currency for each non-RUB category/currency subtotal.
- Do not infer EUR/RUB from USD/RUB or any previous conversion. Every currency subtotal needs
  its own convert_currency Action.
- Usually ignore obligations that are not active unless the user asks otherwise.
- If a tool returns an error or there is not enough data, say that explicitly.
- Keep the final answer concise, but include the basis for the calculation.
- When you have enough information, do not call more tools.
- The final response must always start with exactly "Final Answer:".

You have access to the following tools:

{tools}

Use this format:

Question: the input question
Thought: what you need to do next
Action: the action to take, should be one of [{tool_names}]
Action Input: a JSON object with arguments for the action
Observation: the result of the action
... this Thought/Action/Action Input/Observation cycle can repeat
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}"""
)


class TraceCallbackHandler(BaseCallbackHandler):
    """Collects and prints ReAct events so they are visible in API responses and logs."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        text = response.generations[0][0].text
        self.events.append({"type": "llm", "content": text})
        print(text, flush=True)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        name = serialized.get("name", "tool")
        self.events.append({"type": "action", "tool": name, "input": input_str})
        print(f"Action: {name}\nAction Input: {input_str}", flush=True)

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        self.events.append({"type": "observation", "content": str(output)})
        print(f"Observation: {output}", flush=True)

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        self.events.append({"type": "observation", "content": f"ERROR: {error}"})
        print(f"Observation: ERROR: {error}", flush=True)

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> Any:
        output = finish.return_values.get("output", "")
        self.events.append({"type": "final", "content": output})


def build_agent_executor(callbacks: list[BaseCallbackHandler] | None = None) -> AgentExecutor:
    model_name = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set. Create .env in the project root from "
            ".env.example and put your DeepSeek API key there."
        )

    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )
    agent = create_react_agent(llm=llm, tools=TOOLS, prompt=REACT_PROMPT)
    return AgentExecutor(
        agent=agent,
        tools=TOOLS,
        callbacks=callbacks,
        verbose=True,
        handle_parsing_errors=(
            "Could not parse the previous step. If you already know the answer, "
            "respond with exactly: Thought: I now know the final answer\\nFinal Answer: ..."
        ),
        max_iterations=12,
        return_intermediate_steps=True,
    )


def ask_agent(question: str) -> dict[str, Any]:
    trace_handler = TraceCallbackHandler()
    executor = build_agent_executor(callbacks=[trace_handler])
    result = executor.invoke(
        {
            "input": question,
            "current_date": get_current_date().isoformat(),
        },
        config={"callbacks": [trace_handler]},
    )
    return {
        "answer": result["output"],
        "trace": trace_handler.events,
    }
