"""Per-model token pricing for LLM cost calculation."""

from __future__ import annotations

from typing import Optional

# Prices in USD per token. Update when providers change pricing.
PRICING: dict[str, dict[str, float]] = {
    "gpt-5.5":          {"input": 3.00 / 1_000_000, "output": 12.00 / 1_000_000, "cached_input": 1.50 / 1_000_000},
    "gpt-5.4":          {"input": 2.00 / 1_000_000, "output": 8.00 / 1_000_000, "cached_input": 1.00 / 1_000_000},
    "gpt-5.4-mini":     {"input": 0.30 / 1_000_000, "output": 1.20 / 1_000_000, "cached_input": 0.15 / 1_000_000},
    "gpt-5.2":          {"input": 1.00 / 1_000_000, "output": 4.00 / 1_000_000, "cached_input": 0.50 / 1_000_000},
    "sonar-pro":        {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "gemini-2.5-flash": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
}


def calculate_cost(
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    cached_tokens: Optional[int] = None,
) -> Optional[float]:
    prices = PRICING.get(model)
    if not prices:
        return None
    cost = 0.0
    pt = int(prompt_tokens or 0)
    ct = int(completion_tokens or 0)
    cached = int(cached_tokens or 0)
    non_cached_input = max(0, pt - cached)
    cost += non_cached_input * prices.get("input", 0)
    cost += cached * prices.get("cached_input", prices.get("input", 0))
    cost += ct * prices.get("output", 0)
    return round(cost, 6)
