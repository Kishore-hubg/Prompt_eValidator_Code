"""LLM token pricing rates (USD per 1M tokens).

Rates are hardcoded here for cost estimation in the admin dashboard.
Update these when provider pricing changes.

Sources (as of 2026-04):
  Groq: https://console.groq.com/settings/billing/pricing
  Anthropic: https://www.anthropic.com/pricing
"""
from __future__ import annotations

# Structure: model_id -> {"input": price_per_1M, "output": price_per_1M}
_PRICING: dict[str, dict[str, float]] = {
    # ── Groq models ──────────────────────────────────────────────────────────
    "llama-3.3-70b-versatile":      {"input": 0.59,  "output": 0.79},
    "llama-3.1-70b-versatile":      {"input": 0.59,  "output": 0.79},
    "llama3-70b-8192":              {"input": 0.59,  "output": 0.79},
    "llama-3.1-8b-instant":         {"input": 0.05,  "output": 0.08},
    "llama3-8b-8192":               {"input": 0.05,  "output": 0.08},
    "mixtral-8x7b-32768":           {"input": 0.24,  "output": 0.24},
    "gemma2-9b-it":                 {"input": 0.20,  "output": 0.20},
    "deepseek-r1-distill-llama-70b":{"input": 0.75,  "output": 0.99},
    "qwen/qwen3-32b":               {"input": 0.29,  "output": 0.59},
    # ── Anthropic models ─────────────────────────────────────────────────────
    "claude-sonnet-4-6":            {"input": 3.00,  "output": 15.00},
    "claude-opus-4-6":              {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5-20251001":    {"input": 0.25,  "output": 1.25},
    "claude-3-5-sonnet-20241022":   {"input": 3.00,  "output": 15.00},
    "claude-3-5-haiku-20241022":    {"input": 0.80,  "output": 4.00},
}

# Fallback rates used when model is unknown
_DEFAULT_RATE: dict[str, float] = {"input": 0.50, "output": 1.00}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return estimated USD cost for a single LLM call.

    Args:
        model:             Model ID string (e.g. ``llama-3.3-70b-versatile``).
        prompt_tokens:     Number of input/prompt tokens used.
        completion_tokens: Number of output/completion tokens generated.

    Returns:
        Estimated cost in USD, rounded to 8 decimal places.
    """
    rate = _PRICING.get(model, _DEFAULT_RATE)
    cost = (
        (prompt_tokens / 1_000_000) * rate["input"]
        + (completion_tokens / 1_000_000) * rate["output"]
    )
    return round(cost, 8)
