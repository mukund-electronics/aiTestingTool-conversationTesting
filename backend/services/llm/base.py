from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    raw: dict | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self,
        system: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse: ...


# Static, conservative per-1M-token USD prices. Used only for cost
# estimation/tracking; not authoritative billing.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o-2024-08-06": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1-preview": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    # Anthropic
    "claude-opus-4-7": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "claude-3-5-haiku-latest": (1.00, 5.00),
    "claude-3-opus-20240229": (15.00, 75.00),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = PRICE_TABLE.get(model, (0.0, 0.0))
    return (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price
