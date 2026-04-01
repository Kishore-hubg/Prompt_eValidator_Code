"""
Central validation orchestration layer.

All validation requests — from the REST API, MCP server, Teams bot, or
any future channel — should enter through this module.  It routes to the
LLM-primary pipeline (prompt_validation.run_llm_validation) and inherits
its automatic static-rules-engine fallback when an LLM provider is
unavailable or returns an error.

Data flow
---------
    caller
      └─► validate()                          ← this module
            └─► run_llm_validation()           ← services/prompt_validation.py
                  ├─► llm_evaluate_prompt()    ← services/llm_groq.py  or  llm_anthropic.py
                  │     sends:   persona weights, validator_checks, keyword_checks,
                  │              penalty_triggers, global_checks, scoring formula
                  │     returns: semantic_score, dimension_scores,
                  │              guideline_checks, issues, strengths
                  ├─► [on LLM failure] static_evaluate_prompt() ← services/rules_engine.py
                  └─► [if auto_improve] llm_rewrite_prompt()

Return keys
-----------
    score               float 0-100
    dimension_scores    list[dict]  per-dimension breakdown from LLM or static engine
    strengths           list[str]
    issues              list[str]
    guideline_evaluation dict       strict-mode checks + penalty applied
    improved_prompt     str
    llm_evaluation      dict        provider, model, scoring_mode, error, etc.
    rewrite_strategy    str         "llm" | "template" | "static_fallback"
"""
from __future__ import annotations

from typing import Any

from app.services.prompt_validation import run_llm_validation


def validate(
    prompt_text: str,
    persona_id: str,
    *,
    auto_improve: bool = True,
) -> dict[str, Any]:
    """Validate a prompt and optionally produce an improved version.

    Parameters
    ----------
    prompt_text:  Raw user prompt (non-empty string).
    persona_id:   Target persona — one of persona_0 … persona_4.
    auto_improve: When True the rewrite step is also executed.

    Returns
    -------
    dict with keys documented in the module docstring above.
    """
    return run_llm_validation(prompt_text, persona_id, auto_improve=auto_improve)
