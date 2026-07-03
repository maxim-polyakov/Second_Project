from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.demo_agent import ask_demo_agent
from app.tools import CurrencyConversionError
from app.tools import convert_currency as convert_currency_core
from app.tools import get_obligations as get_obligations_core

load_dotenv()


class GetObligationsInput(BaseModel):
    status: str | None = Field(
        default=None,
        description="Optional obligation status filter, for example active, paused, cancelled.",
    )
    category: str | None = Field(
        default=None,
        description="Optional category filter, for example entertainment, education, cloud.",
    )


class ConvertCurrencyInput(BaseModel):
    amount: float = Field(description="Amount of money to convert.")
    from_currency: str = Field(description="Source ISO currency code, for example USD.")
    to_currency: str = Field(description="Target ISO currency code, for example RUB.")


@tool("get_obligations", args_schema=GetObligationsInput)
def get_obligations_tool(status: str | None = None, category: str | None = None) -> str:
    """Return user obligations from the local JSON fixture, filtered by status/category."""
    obligations = get_obligations_core(status=status, category=category)
    return json.dumps(obligations, ensure_ascii=False, indent=2)


@tool("convert_currency", args_schema=ConvertCurrencyInput)
def convert_currency_tool(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert a monetary amount with the public frankfurter.app API."""
    try:
        converted = convert_currency_core(amount, from_currency, to_currency)
    except CurrencyConversionError as exc:
        return f"ERROR: {exc}. Report that the conversion is unavailable; do not invent a rate."
    return str(converted)


TOOLS = [get_obligations_tool, convert_currency_tool]


REACT_PROMPT = PromptTemplate.from_template(
    """You are an AI agent for a smart registry of subscriptions and recurring payments.
Answer in Russian. Use tools whenever the user asks about obligations, dates, totals,
categories, currencies, or payment status.

Current date: {current_date}
Default target currency: RUB

Rules:
- Use only the data returned by tools.
- For date ranges, compare next_payment_date with the current date.
- For totals across currencies, convert every non-target currency item before summing.
- Usually ignore obligations that are not active unless the user asks otherwise.
- If a tool returns an error or there is not enough data, say that explicitly.
- Keep the final answer concise, but include the basis for the calculation.

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
            "Could not parse the previous step. Continue using the required "
            "Thought/Action/Action Input/Observation format."
        ),
        max_iterations=8,
        return_intermediate_steps=True,
    )


def ask_agent(question: str) -> dict[str, Any]:
    if os.getenv("DEMO_MODE", "false").lower() == "true":
        return ask_demo_agent(question)

    trace_handler = TraceCallbackHandler()
    executor = build_agent_executor(callbacks=[trace_handler])
    result = executor.invoke(
        {
            "input": question,
            "current_date": date.today().isoformat(),
        }
    )
    return {
        "answer": result["output"],
        "trace": trace_handler.events,
    }
