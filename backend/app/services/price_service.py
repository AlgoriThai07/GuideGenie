"""Real-world price verification via Gemini + Google Search grounding.

Grounds the LLM's per-item cost estimates against live web search results in
a single batched Gemini call per generation run (not one call per item, to
keep API call volume down), and logs the attempt as a ``ToolCall`` row. Pure
service module — no FastAPI dependencies. Never raises: a failed or
unparseable call returns an empty result mapping so a bad price lookup never
aborts the itinerary generation run.
"""

import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from google import genai
from google.genai import types as genai_types
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentRunStatus
from app.models.place import Place
from app.models.tool_call import ToolCall

_PRICE_LINE_RE = re.compile(
    r"(\d+)\s*:\s*PRICE_USD\s*:\s*([\d.]+|unknown)", re.IGNORECASE
)

_SYSTEM_INSTRUCTION = (
    "You are a price-lookup assistant. For each numbered item below, use "
    "web search to find its current typical price in USD for one person. "
    "Reply with EXACTLY one line per item, in this format and nothing else:\n"
    "<index>: PRICE_USD: <number>\n"
    "or, if you cannot find a reliable price:\n"
    "<index>: PRICE_USD: unknown"
)


@dataclass
class PriceQuery:
    item_title: str
    place: Place


@dataclass
class PriceResult:
    price: Decimal


class PriceService:
    """Wraps a batched Gemini + Google Search price lookup."""

    @staticmethod
    def search_batch_prices(
        db: Session,
        agent_run_id: int,
        queries: list[PriceQuery],
        destination: str,
    ) -> dict[int, PriceResult]:
        """Ground real-world prices for ``queries`` in one Gemini call.

        Returns ``{position: PriceResult}`` for positions (matching the
        order of ``queries``) where a confident price was found; positions
        with no price are simply absent from the result. Logs exactly one
        ``ToolCall`` row for the whole batch. Never raises.
        """
        if not queries:
            return {}

        prompt_lines = [
            f"{i}. {q.item_title} — {q.place.name}, {q.place.address or destination}"
            for i, q in enumerate(queries)
        ]
        prompt = "\n".join(prompt_lines)

        t0 = time.perf_counter()
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.AI_MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION,
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                ),
            )
            text = response.text or ""
            latency_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as e:  # noqa: BLE001 — a bad batch must not abort the run
            db.rollback()
            try:
                db.add(
                    ToolCall(
                        agent_run_id=agent_run_id,
                        tool_name="gemini_price_search_batch",
                        status=AgentRunStatus.FAILED,
                        input_json={"items": [q.item_title for q in queries]},
                        error_message=f"Unexpected error: {e}",
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                        cache_hit=False,
                    )
                )
                db.commit()
            except Exception:  # noqa: BLE001 — logging itself must not raise
                db.rollback()
            return {}

        results: dict[int, PriceResult] = {}
        for match in _PRICE_LINE_RE.finditer(text):
            index_str, price_str = match.groups()
            if price_str.lower() == "unknown":
                continue
            try:
                index = int(index_str)
                price = Decimal(price_str)
            except (ValueError, InvalidOperation):
                continue
            if 0 <= index < len(queries):
                results[index] = PriceResult(price=price)

        if not results:
            db.add(
                ToolCall(
                    agent_run_id=agent_run_id,
                    tool_name="gemini_price_search_batch",
                    status=AgentRunStatus.FAILED,
                    input_json={"items": [q.item_title for q in queries]},
                    error_message="No parseable price lines",
                    latency_ms=latency_ms,
                    cache_hit=False,
                )
            )
            db.commit()
            return {}

        db.add(
            ToolCall(
                agent_run_id=agent_run_id,
                tool_name="gemini_price_search_batch",
                status=AgentRunStatus.COMPLETED,
                input_json={"items": [q.item_title for q in queries]},
                output_json={"queried": len(queries), "priced": len(results)},
                latency_ms=latency_ms,
                cache_hit=False,
            )
        )
        db.commit()
        return results
