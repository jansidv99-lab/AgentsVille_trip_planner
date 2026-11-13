# Phase 5 – B0 Step 3: approximate LLM cost estimation for eval reports and (later) production metrics.
# Prices are USD per 1M tokens (OpenAI list prices for the gpt-4.1 family). Vocareum billing may differ:
# treat cost_usd as an ESTIMATE for comparing runs and spotting trends, not an invoice.

from typing import Optional

# model -> (input USD / 1M tokens, output USD / 1M tokens). Edit here if prices change.
PRICES_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
}


# Phase 5 – B0 Step 3: estimated cost of one call; None when the model or token counts are unknown
def estimate_cost(model: Optional[str], prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> Optional[float]:
    prices = PRICES_PER_1M.get(str(model)) if model else None
    if prices is None or prompt_tokens is None or completion_tokens is None:
        return None
    price_in, price_out = prices
    return round((prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000, 6)
