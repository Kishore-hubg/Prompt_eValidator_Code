from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

_log = logging.getLogger("prompt_validator.validation")

from app.core.settings import (
    ANTHROPIC_MODEL,
    GROQ_MODEL,
    LLM_FALLBACK_ON_VALIDATE_FAILURE,
    LLM_PROVIDER,
    LLM_VALIDATE_REQUIRED,
    PROMPT_CACHE_TTL_SECONDS,
    STATIC_PRESCREEN_THRESHOLD,
)

# ---------------------------------------------------------------------------
# In-memory prompt-result cache — avoids redundant LLM calls for identical
# (prompt_text, persona_id, auto_improve) requests within PROMPT_CACHE_TTL_SECONDS.
# Structure: { cache_key: (expire_timestamp, result_dict) }
# Process-local only; resets on server restart.  No external dependency needed.
# ---------------------------------------------------------------------------
_validation_cache: dict[str, tuple[float, dict[str, Any]]] = {}
import httpx
from app.services.improver import improve_prompt, is_prompt_too_thin_for_rewrite
from app.services import llm_anthropic, llm_groq
from app.services.llm_groq import GroqRateLimitError
from app.services.persona_loader import get_persona
from app.services.prompt_guidelines_loader import load_prompt_guidelines
from app.services.rules_engine import evaluate_guidelines, evaluate_prompt as static_evaluate_prompt
from app.services.data_strategy import SOURCE_OF_TRUTH_DOC, SOURCE_OF_TRUTH_SCOPE
from app.services.suggestion_engine import derive_issue_based_suggestions
from app.core.pricing import calculate_cost


def _normalize(text: str) -> str:
    """Normalize a string for semantic deduplication (lowercase, collapse whitespace, strip punctuation)."""
    import re as _re
    return _re.sub(r"[^a-z0-9 ]", "", text.lower().strip()).split()[:8].__str__()


def dedupe_preserve(items: list[str]) -> list[str]:
    """Deduplicate preserving first-seen order.

    Uses both exact-string and normalized (semantic) comparison so that
    rephrases of the same gap (e.g. 'missing output format' / 'no format
    declared') are collapsed to the first occurrence.
    """
    seen_exact: set[str] = set()
    seen_norm: set[str] = set()
    output: list[str] = []
    for item in items:
        text = item.strip()
        if not text:
            continue
        norm = _normalize(text)
        if text in seen_exact or norm in seen_norm:
            continue
        seen_exact.add(text)
        seen_norm.add(norm)
        output.append(text)
    return output


def _recompute_score(
    dimension_scores: list[dict[str, Any]],
    guideline_evaluation: dict[str, Any],
    guidelines: dict[str, Any],
) -> float:
    """Recompute the final score server-side from dimension pass/fail results.

    LLMs frequently return a semantic_score that is inconsistent with their
    own dimension evaluations (e.g. all dimensions pass but score is 82 instead
    of >=85).  Computing server-side guarantees the displayed score is always
    mathematically consistent with the Dimension Breakdown shown to the user.

    Formula (mirrors the scoring rule in the LLM system prompt):
        base_score = (sum_passed_weights / sum_all_weights) * 100
        penalty    = min(guideline_penalty_applied, strict_penalty_cap)
        final      = max(0, base_score - penalty)
    """
    if not dimension_scores:
        return 0.0
    total_weight = sum(float(d.get("weight", 0)) for d in dimension_scores) or 1.0
    passed_weight = sum(
        float(d.get("weight", 0)) for d in dimension_scores if d.get("passed", False)
    )
    base_score = (passed_weight / total_weight) * 100
    penalty = int(guideline_evaluation.get("penalty_applied", 0))
    penalty_cap = int(guidelines.get("strict_penalty_cap", 15))
    penalty = min(penalty, penalty_cap)
    return round(max(0.0, base_score - penalty), 2)


def _build_guideline_evaluation_from_llm(
    guideline_checks: list[dict[str, Any]],
    guidelines: dict[str, Any],
) -> dict[str, Any]:
    """Build the guideline_evaluation block from LLM-returned guideline_checks."""
    checks_out: list[dict[str, Any]] = []
    issues_out: list[str] = []
    penalty_total = 0

    for gc in guideline_checks:
        passed = bool(gc.get("passed", True))
        penalty = int(gc.get("penalty", 0))
        issue = str(gc.get("issue", "")).strip() if gc.get("issue") else ""
        if not passed:
            penalty_total += penalty
            if issue:
                issues_out.append(issue)
        checks_out.append({
            "id": gc.get("id", ""),
            "description": "",
            "passed": passed,
            "status": "applied",
            "message": issue if not passed else "Pass",
        })

    return {
        "strict_mode": bool(guidelines.get("strict_mode", True)),
        "penalty_applied": penalty_total,
        "checks": checks_out,
        "issues": issues_out,
        "sources": guidelines.get("sources", []),
    }


def _cache_key(prompt_text: str, persona_id: str, auto_improve: bool) -> str:
    """Stable SHA-256 key for the validation cache."""
    raw = f"{persona_id}:{auto_improve}:{prompt_text.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_llm_validation(
    prompt_text: str,
    persona_id: str,
    *,
    auto_improve: bool,
) -> dict[str, Any]:
    # ── Cache lookup ────────────────────────────────────────────────────────
    # Return immediately for identical requests within the TTL window.
    # Cache is bypassed when PROMPT_CACHE_TTL_SECONDS=0.
    if PROMPT_CACHE_TTL_SECONDS > 0:
        key = _cache_key(prompt_text, persona_id, auto_improve)
        cached = _validation_cache.get(key)
        if cached is not None:
            expire_ts, cached_result = cached
            if time.monotonic() < expire_ts:
                return cached_result
            # Expired — evict stale entry
            del _validation_cache[key]

    persona = get_persona(persona_id)
    guidelines = load_prompt_guidelines()

    dimension_scores: list[dict[str, Any]] = []
    merged_strengths: list[str] = []
    merged_issues: list[str] = []
    _eval_token_usage: dict[str, Any] = {}
    _rewrite_token_usage: dict[str, Any] = {}

    # Default guideline_evaluation — populated from LLM response or static fallback below
    guideline_evaluation: dict[str, Any] = {
        "strict_mode": bool(guidelines.get("strict_mode", True)),
        "penalty_applied": 0,
        "checks": [],
        "issues": [],
        "sources": guidelines.get("sources", []),
    }

    llm_evaluation: dict[str, Any] = {
        "used": False,
        "provider": None,
        "model": None,
        "semantic_score": None,
        "static_score": None,
        "scoring_mode": "llm_only",
        "source_of_truth_document": SOURCE_OF_TRUTH_DOC,
        "source_of_truth_scope": SOURCE_OF_TRUTH_SCOPE,
        "rewrite_applied_guidelines": None,
        "rewrite_unresolved_gaps": None,
        "error": None,
    }
    final_score = 0.0

    # Resolve provider/module early — needed for both eval and rewrite paths.
    provider = _selected_provider()
    llm_module = _provider_module(provider)
    if not llm_module:
        raise RuntimeError("A configured LLM provider is required but none is available.")

    # ── Static pre-screen ───────────────────────────────────────────────────
    # Run the lightweight rules engine first.  If the static score already
    # meets STATIC_PRESCREEN_THRESHOLD (default 85 = "Excellent") the LLM
    # evaluation call is skipped entirely — saving ~800-1 200 tokens per
    # request.  The rewrite path still runs normally if auto_improve=True.
    # Set STATIC_PRESCREEN_THRESHOLD=0 to always call the LLM.
    _skip_llm_eval = False
    if STATIC_PRESCREEN_THRESHOLD > 0:
        ps_score, ps_dims, ps_strengths, ps_issues, ps_ge = static_evaluate_prompt(
            prompt_text, persona_id
        )
        if ps_score >= STATIC_PRESCREEN_THRESHOLD:
            final_score = ps_score
            dimension_scores = ps_dims
            merged_issues = dedupe_preserve(ps_issues)
            merged_strengths = dedupe_preserve(ps_strengths)
            guideline_evaluation.update({
                "penalty_applied": ps_ge.get("penalty_applied", 0),
                "checks": ps_ge.get("checks", []),
                "issues": ps_ge.get("issues", []),
            })
            llm_evaluation["scoring_mode"] = "static_prescreen"
            _skip_llm_eval = True

    if not _skip_llm_eval:
        llm_evaluation["used"] = True
        llm_evaluation["provider"] = provider
        llm_evaluation["model"] = GROQ_MODEL if provider == "groq" else ANTHROPIC_MODEL

    if not _skip_llm_eval:
        try:
            try:
                evaluation = llm_module.llm_evaluate_prompt(
                    prompt_text,
                    persona=persona,
                    guidelines=guidelines,
                    source_of_truth_doc=SOURCE_OF_TRUTH_DOC,
                    source_of_truth_scope=SOURCE_OF_TRUTH_SCOPE,
                )
            except (httpx.HTTPStatusError, GroqRateLimitError):
                # httpx.HTTPStatusError → Anthropic 4xx/5xx (billing, rate limit, etc.)
                # GroqRateLimitError    → Groq 429 exhausted
                fallback_module = _fallback_module_on_primary_failure(provider)
                if not fallback_module:
                    raise
                llm_module = fallback_module
                _fb_is_groq = fallback_module is llm_groq
                llm_evaluation["provider"] = "groq" if _fb_is_groq else "anthropic"
                llm_evaluation["model"] = GROQ_MODEL if _fb_is_groq else ANTHROPIC_MODEL
                llm_evaluation["scoring_mode"] = "llm_fallback_provider"
                evaluation = llm_module.llm_evaluate_prompt(
                    prompt_text,
                    persona=persona,
                    guidelines=guidelines,
                    source_of_truth_doc=SOURCE_OF_TRUTH_DOC,
                    source_of_truth_scope=SOURCE_OF_TRUTH_SCOPE,
                )

            llm_evaluation["semantic_score"] = evaluation.semantic_score  # kept for audit/debug
            _eval_token_usage = getattr(evaluation, "token_usage", {}) or {}
            dimension_scores = getattr(evaluation, "dimension_scores", [])
            merged_issues = dedupe_preserve(evaluation.issues)[:6]        # cap: LLM may ignore the limit
            merged_strengths = dedupe_preserve(evaluation.strengths)[:5]

            # Build guideline_evaluation from LLM's guideline_checks when available
            if getattr(evaluation, "guideline_checks", None):
                guideline_evaluation = _build_guideline_evaluation_from_llm(
                    getattr(evaluation, "guideline_checks", []), guidelines
                )
                # Merge any guideline-level issues into the main issues list
                for gi in guideline_evaluation["issues"]:
                    if gi not in merged_issues:
                        merged_issues.append(gi)
            else:
                # LLM omitted guideline_checks — compute them statically for display only
                static_ge = evaluate_guidelines(prompt_text)
                guideline_evaluation.update({
                    "penalty_applied": static_ge.get("penalty_applied", 0),
                    "checks": static_ge.get("checks", []),
                    "issues": static_ge.get("issues", []),
                })
                merged_issues = dedupe_preserve(merged_issues + static_ge.get("issues", []))

            # Recompute score server-side from dimension pass/fail + guideline penalty.
            # This fixes the common LLM inconsistency where all dimensions pass but the
            # LLM-reported semantic_score is lower than the formula dictates.
            if dimension_scores:
                final_score = _recompute_score(dimension_scores, guideline_evaluation, guidelines)
            else:
                # No dimension breakdown available — fall back to LLM's own score
                final_score = evaluation.semantic_score

        except Exception as exc:  # noqa: BLE001
            # Re-raise GroqRateLimitError as-is ONLY when LLM is strictly
            # required AND fallback is disabled.  When fallback is allowed, a
            # rate-limit falls through to static scoring so the user always
            # receives a result rather than an error page.
            _is_rate_limit = isinstance(exc, (GroqRateLimitError, httpx.HTTPStatusError))
            if isinstance(exc, GroqRateLimitError) and (
                LLM_VALIDATE_REQUIRED or not LLM_FALLBACK_ON_VALIDATE_FAILURE
            ):
                raise

            llm_evaluation["error"] = str(exc)

            if LLM_VALIDATE_REQUIRED or not LLM_FALLBACK_ON_VALIDATE_FAILURE:
                raise RuntimeError(f"LLM validation failed: {exc}") from exc

            # --- Static rules-engine fallback ---
            # Distinguish rate-limit / provider-error fallback from generic LLM error.
            llm_evaluation["scoring_mode"] = (
                "rate_limit_fallback" if _is_rate_limit else "static_fallback"
            )
            fallback_score, fallback_dims, fallback_strengths, fallback_issues, fallback_ge = static_evaluate_prompt(
                prompt_text, persona_id
            )
            final_score = fallback_score
            dimension_scores = fallback_dims
            guideline_evaluation.update({
                "penalty_applied": fallback_ge.get("penalty_applied", 0),
                "checks": fallback_ge.get("checks", []),
                "issues": fallback_ge.get("issues", []),
            })
            merged_issues = dedupe_preserve(fallback_issues)
            merged_strengths = dedupe_preserve(fallback_strengths)

    # Derive persona-filtered suggestions from the validated issues so the
    # rewrite LLM focuses on the gaps that matter most for this persona,
    # falling back to persona default suggestions when no issue keywords match.
    rewrite_issues = derive_issue_based_suggestions(
        persona_id,
        merged_issues,
        fallback=merged_issues,  # use raw issues as fallback so rewrite is never empty
    )

    rewrite_strategy = "template"
    if auto_improve:
        if is_prompt_too_thin_for_rewrite(prompt_text):
            # Skip LLM rewrite — models tend to invent full persona narratives for nonsense input.
            improved_prompt = improve_prompt(
                prompt_text, persona_id, merged_issues, thin_input=True
            )
            rewrite_strategy = "template_thin"
        else:
            try:
                try:
                    rewrite = llm_module.llm_rewrite_prompt(
                        prompt_text,
                        persona=persona,
                        guidelines=guidelines,
                        issues=rewrite_issues,
                    )
                except (httpx.HTTPStatusError, GroqRateLimitError):
                    fallback_module = _fallback_module_on_primary_failure(provider)
                    if not fallback_module:
                        raise
                    llm_module = fallback_module
                    _fb_is_groq = fallback_module is llm_groq
                    llm_evaluation["provider"] = "groq" if _fb_is_groq else "anthropic"
                    llm_evaluation["model"] = GROQ_MODEL if _fb_is_groq else ANTHROPIC_MODEL
                    llm_evaluation["scoring_mode"] = "llm_fallback_provider"
                    rewrite = llm_module.llm_rewrite_prompt(
                        prompt_text,
                        persona=persona,
                        guidelines=guidelines,
                        issues=rewrite_issues,
                    )
                improved_prompt = rewrite.improved_prompt
                _rewrite_token_usage = getattr(rewrite, "token_usage", {}) or {}
                llm_evaluation["rewrite_applied_guidelines"] = rewrite.applied_guidelines
                llm_evaluation["rewrite_unresolved_gaps"] = rewrite.unresolved_gaps
                rewrite_strategy = "llm"
            except Exception as _rw_exc:  # noqa: BLE001
                _log.warning("LLM rewrite failed (%s: %s) — using template fallback",
                             type(_rw_exc).__name__, _rw_exc)
                thin_fb = is_prompt_too_thin_for_rewrite(prompt_text)
                improved_prompt = improve_prompt(
                    prompt_text, persona_id, merged_issues, thin_input=thin_fb
                )
    else:
        improved_prompt = prompt_text

    # Filter out zero-weight dimensions (e.g. TRACEABILITY, BUSINESS RELEVANCE)
    # so the UI never shows a confusing "0/0" dimension card.  These dimensions
    # carry no scoring weight and are irrelevant to the final score.
    dimension_scores = [d for d in dimension_scores if float(d.get("weight", 0)) > 0]

    # ── Token usage aggregation ─────────────────────────────────────────────
    # Collect tokens from eval + rewrite sentinel dicts (populated above when
    # LLM calls succeeded; remain empty for static pre-screen / fallback paths).
    _eval_prompt_tokens      = int(_eval_token_usage.get("prompt_tokens", 0))
    _eval_completion_tokens  = int(_eval_token_usage.get("completion_tokens", 0))
    _rewrite_prompt_tokens   = int(_rewrite_token_usage.get("prompt_tokens", 0))
    _rewrite_completion_tokens = int(_rewrite_token_usage.get("completion_tokens", 0))
    _total_tokens = _eval_prompt_tokens + _eval_completion_tokens + _rewrite_prompt_tokens + _rewrite_completion_tokens
    _model = llm_evaluation.get("model") or ""
    _cost = calculate_cost(
        _model,
        _eval_prompt_tokens + _rewrite_prompt_tokens,
        _eval_completion_tokens + _rewrite_completion_tokens,
    ) if _total_tokens > 0 else 0.0
    token_usage_data: dict[str, Any] = {
        "eval_prompt_tokens": _eval_prompt_tokens,
        "eval_completion_tokens": _eval_completion_tokens,
        "rewrite_prompt_tokens": _rewrite_prompt_tokens,
        "rewrite_completion_tokens": _rewrite_completion_tokens,
        "total_tokens": _total_tokens,
        "estimated_cost_usd": _cost,
        "model": _model,
        "provider": llm_evaluation.get("provider") or "",
    }

    result: dict[str, Any] = {
        "score": final_score,
        "dimension_scores": dimension_scores,
        "strengths": merged_strengths,
        "issues": merged_issues,
        "guideline_evaluation": guideline_evaluation,
        "improved_prompt": improved_prompt,
        "llm_evaluation": llm_evaluation,
        "rewrite_strategy": rewrite_strategy,
        "token_usage": token_usage_data,
    }

    # ── Cache store ─────────────────────────────────────────────────────────
    # Only cache successful results (no LLM error recorded).
    # Pre-screened and fallback results are also safe to cache.
    if PROMPT_CACHE_TTL_SECONDS > 0 and not llm_evaluation.get("error"):
        key = _cache_key(prompt_text, persona_id, auto_improve)
        expire_ts = time.monotonic() + PROMPT_CACHE_TTL_SECONDS
        _validation_cache[key] = (expire_ts, result)

    return result


def _selected_provider() -> str | None:
    pref = LLM_PROVIDER if LLM_PROVIDER in {"auto", "groq", "anthropic"} else "auto"
    if pref == "groq":
        return "groq" if llm_groq.llm_configured() else None
    if pref == "anthropic":
        return "anthropic" if llm_anthropic.llm_configured() else None
    # auto: Anthropic first, Groq as fallback
    if llm_anthropic.llm_configured():
        return "anthropic"
    if llm_groq.llm_configured():
        return "groq"
    return None


def _provider_module(provider: str | None):
    if provider == "groq":
        return llm_groq
    if provider == "anthropic":
        return llm_anthropic
    return None


def _fallback_module_on_primary_failure(provider: str | None):
    """Return the secondary provider module when the primary fails.

    Only active when LLM_PROVIDER=auto (cross-provider fallback).
    Pinned providers (LLM_PROVIDER=groq/anthropic) have no fallback.

    auto + primary=anthropic fails → try Groq
    auto + primary=groq fails     → try Anthropic
    """
    pref = LLM_PROVIDER if LLM_PROVIDER in {"auto", "groq", "anthropic"} else "auto"
    if pref != "auto":
        return None
    if provider == "anthropic" and llm_groq.llm_configured():
        return llm_groq
    if provider == "groq" and llm_anthropic.llm_configured():
        return llm_anthropic
    return None


async def run_llm_validation_async(
    prompt_text: str,
    persona_id: str,
    *,
    auto_improve: bool = False,
) -> dict[str, Any]:
    """Anthropic-only async validation pipeline.

    Uses native httpx.AsyncClient (non-blocking) for the eval call and an
    asyncio.to_thread wrapper for the rewrite call.  No Groq code paths,
    no threading.Lock exposure — zero deadlock risk.
    Always returns a result: falls back to static scoring if Anthropic fails.
    """
    # ── Cache lookup ─────────────────────────────────────────────────────────
    if PROMPT_CACHE_TTL_SECONDS > 0:
        key = _cache_key(prompt_text, persona_id, auto_improve)
        cached = _validation_cache.get(key)
        if cached is not None:
            expire_ts, cached_result = cached
            if time.monotonic() < expire_ts:
                return cached_result
            del _validation_cache[key]

    if not llm_anthropic.llm_configured():
        raise RuntimeError("Anthropic API key is not configured.")

    persona = get_persona(persona_id)
    guidelines = load_prompt_guidelines()

    dimension_scores: list[dict[str, Any]] = []
    merged_strengths: list[str] = []
    merged_issues: list[str] = []
    _eval_token_usage_async: dict[str, Any] = {}
    _rewrite_token_usage_async: dict[str, Any] = {}

    guideline_evaluation: dict[str, Any] = {
        "strict_mode": bool(guidelines.get("strict_mode", True)),
        "penalty_applied": 0,
        "checks": [],
        "issues": [],
        "sources": guidelines.get("sources", []),
    }

    llm_evaluation: dict[str, Any] = {
        "used": False,
        "provider": "anthropic",
        "model": ANTHROPIC_MODEL,
        "semantic_score": None,
        "static_score": None,
        "scoring_mode": "llm_only",
        "source_of_truth_document": SOURCE_OF_TRUTH_DOC,
        "source_of_truth_scope": SOURCE_OF_TRUTH_SCOPE,
        "rewrite_applied_guidelines": None,
        "rewrite_unresolved_gaps": None,
        "error": None,
    }
    final_score = 0.0

    # ── Static pre-screen ────────────────────────────────────────────────────
    _skip_llm_eval = False
    if STATIC_PRESCREEN_THRESHOLD > 0:
        ps_score, ps_dims, ps_strengths, ps_issues, ps_ge = static_evaluate_prompt(
            prompt_text, persona_id
        )
        if ps_score >= STATIC_PRESCREEN_THRESHOLD:
            final_score = ps_score
            dimension_scores = ps_dims
            merged_issues = dedupe_preserve(ps_issues)
            merged_strengths = dedupe_preserve(ps_strengths)
            guideline_evaluation.update({
                "penalty_applied": ps_ge.get("penalty_applied", 0),
                "checks": ps_ge.get("checks", []),
                "issues": ps_ge.get("issues", []),
            })
            llm_evaluation["scoring_mode"] = "static_prescreen"
            _skip_llm_eval = True

    # ── Anthropic LLM evaluation (async, non-blocking) ───────────────────────
    if not _skip_llm_eval:
        llm_evaluation["used"] = True
        try:
            evaluation = await llm_anthropic.llm_evaluate_prompt_async(
                prompt_text,
                persona=persona,
                guidelines=guidelines,
                source_of_truth_doc=SOURCE_OF_TRUTH_DOC,
                source_of_truth_scope=SOURCE_OF_TRUTH_SCOPE,
            )
            llm_evaluation["semantic_score"] = evaluation.semantic_score
            _eval_token_usage_async = getattr(evaluation, "token_usage", {}) or {}
            dimension_scores = getattr(evaluation, "dimension_scores", [])
            merged_issues = dedupe_preserve(evaluation.issues)[:6]
            merged_strengths = dedupe_preserve(evaluation.strengths)[:5]

            if getattr(evaluation, "guideline_checks", None):
                guideline_evaluation = _build_guideline_evaluation_from_llm(
                    getattr(evaluation, "guideline_checks", []), guidelines
                )
                for gi in guideline_evaluation["issues"]:
                    if gi not in merged_issues:
                        merged_issues.append(gi)
            else:
                static_ge = evaluate_guidelines(prompt_text)
                guideline_evaluation.update({
                    "penalty_applied": static_ge.get("penalty_applied", 0),
                    "checks": static_ge.get("checks", []),
                    "issues": static_ge.get("issues", []),
                })
                merged_issues = dedupe_preserve(merged_issues + static_ge.get("issues", []))

            if dimension_scores:
                final_score = _recompute_score(dimension_scores, guideline_evaluation, guidelines)
            else:
                final_score = evaluation.semantic_score

        except Exception as exc:  # noqa: BLE001
            llm_evaluation["error"] = str(exc)
            _log.warning("Anthropic eval failed (%s: %s) — falling back to static scoring",
                         type(exc).__name__, exc)
            if LLM_VALIDATE_REQUIRED or not LLM_FALLBACK_ON_VALIDATE_FAILURE:
                raise RuntimeError(f"LLM validation failed: {exc}") from exc
            llm_evaluation["scoring_mode"] = "static_fallback"
            fb_score, fb_dims, fb_strengths, fb_issues, fb_ge = static_evaluate_prompt(
                prompt_text, persona_id
            )
            final_score = fb_score
            dimension_scores = fb_dims
            guideline_evaluation.update({
                "penalty_applied": fb_ge.get("penalty_applied", 0),
                "checks": fb_ge.get("checks", []),
                "issues": fb_ge.get("issues", []),
            })
            merged_issues = dedupe_preserve(fb_issues)
            merged_strengths = dedupe_preserve(fb_strengths)

    rewrite_issues = derive_issue_based_suggestions(
        persona_id, merged_issues, fallback=merged_issues,
    )

    # ── Anthropic LLM rewrite (thread-wrapped — rewrite prompt is large to build)
    rewrite_strategy = "template"
    improved_prompt = prompt_text
    if auto_improve:
        if is_prompt_too_thin_for_rewrite(prompt_text):
            improved_prompt = improve_prompt(
                prompt_text, persona_id, merged_issues, thin_input=True
            )
            rewrite_strategy = "template_thin"
        else:
            try:
                rewrite = await llm_anthropic.llm_rewrite_prompt_async(
                    prompt_text,
                    persona=persona,
                    guidelines=guidelines,
                    issues=rewrite_issues,
                )
                improved_prompt = rewrite.improved_prompt
                _rewrite_token_usage_async = getattr(rewrite, "token_usage", {}) or {}
                llm_evaluation["rewrite_applied_guidelines"] = rewrite.applied_guidelines
                llm_evaluation["rewrite_unresolved_gaps"] = rewrite.unresolved_gaps
                rewrite_strategy = "llm"
            except Exception as _rw_exc:  # noqa: BLE001
                _log.warning("Anthropic rewrite failed (%s: %s) — using template fallback",
                             type(_rw_exc).__name__, _rw_exc)
                thin_fb = is_prompt_too_thin_for_rewrite(prompt_text)
                improved_prompt = improve_prompt(
                    prompt_text, persona_id, merged_issues, thin_input=thin_fb
                )

    dimension_scores = [d for d in dimension_scores if float(d.get("weight", 0)) > 0]

    # ── Token usage aggregation (async path) ─────────────────────────────────
    _ae_pt  = int(_eval_token_usage_async.get("prompt_tokens", 0))
    _ae_ct  = int(_eval_token_usage_async.get("completion_tokens", 0))
    _ar_pt  = int(_rewrite_token_usage_async.get("prompt_tokens", 0))
    _ar_ct  = int(_rewrite_token_usage_async.get("completion_tokens", 0))
    _a_total = _ae_pt + _ae_ct + _ar_pt + _ar_ct
    _a_model = llm_evaluation.get("model") or ""
    _a_cost = calculate_cost(_a_model, _ae_pt + _ar_pt, _ae_ct + _ar_ct) if _a_total > 0 else 0.0
    token_usage_data_async: dict[str, Any] = {
        "eval_prompt_tokens": _ae_pt,
        "eval_completion_tokens": _ae_ct,
        "rewrite_prompt_tokens": _ar_pt,
        "rewrite_completion_tokens": _ar_ct,
        "total_tokens": _a_total,
        "estimated_cost_usd": _a_cost,
        "model": _a_model,
        "provider": llm_evaluation.get("provider") or "",
    }

    result: dict[str, Any] = {
        "score": final_score,
        "dimension_scores": dimension_scores,
        "strengths": merged_strengths,
        "issues": merged_issues,
        "guideline_evaluation": guideline_evaluation,
        "improved_prompt": improved_prompt,
        "llm_evaluation": llm_evaluation,
        "rewrite_strategy": rewrite_strategy,
        "token_usage": token_usage_data_async,
    }

    if PROMPT_CACHE_TTL_SECONDS > 0 and not llm_evaluation.get("error"):
        key = _cache_key(prompt_text, persona_id, auto_improve)
        expire_ts = time.monotonic() + PROMPT_CACHE_TTL_SECONDS
        _validation_cache[key] = (expire_ts, result)

    return result
