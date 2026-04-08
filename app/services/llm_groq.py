from __future__ import annotations

import asyncio
import json
import re
import time
import random
import threading
from datetime import timezone
from email.utils import parsedate_to_datetime
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.settings import (
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_REQUESTS_PER_MINUTE,
    GROQ_REWRITE_MODEL,
    GROQ_TIMEOUT_SECONDS,
    LLM_STRICT_SCHEMA,
)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

# Models that emit <think>...</think> reasoning blocks and do NOT support
# response_format: {type: json_object}.  For these we send a plain request
# and extract the JSON object from the response text ourselves.
_NO_JSON_MODE_MODELS: frozenset[str] = frozenset({
    "qwen/qwen3-32b",
    "qwen/qwen3-14b",
    "qwen/qwen3-8b",
    "deepseek-r1-distill-llama-70b",
    "deepseek-r1-distill-llama-8b",
    "deepseek-r1-distill-qwen-32b",
    "deepseek-r1-distill-qwen-14b",
})


@dataclass
class LlmEvaluateResult:
    semantic_score: float
    issues: list[str]
    strengths: list[str]
    dimension_scores: list[dict[str, Any]] = field(default_factory=list)
    guideline_checks: list[dict[str, Any]] = field(default_factory=list)
    token_usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class LlmRewriteResult:
    improved_prompt: str
    applied_guidelines: list[str]
    unresolved_gaps: list[str]
    token_usage: dict[str, Any] = field(default_factory=dict)


def llm_configured() -> bool:
    return bool(GROQ_API_KEY)


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# Process-wide throttle state to reduce burst 429s when multiple requests land
# concurrently (e.g., Teams traffic). Updated on each 429 and honoured before
# every Groq request.
_rate_limit_lock = threading.Lock()
_next_groq_request_at = 0.0
_last_groq_request_at = 0.0


def _strip_code_fences(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```\s*$", "", value)
    return value.strip()


def _parse_json_object(content: str) -> dict[str, Any]:
    """Parse a JSON object from LLM output.

    Handles three output variants:
    1. Plain JSON string                      → parse directly
    2. Markdown-fenced JSON (```json ... ```) → strip fences, parse
    3. DeepSeek R1 / QwQ reasoning models     → strip <think>…</think>
       chain-of-thought block first, then locate and parse the JSON object
    """
    cleaned = _THINK_BLOCK.sub("", content).strip()
    cleaned = _strip_code_fences(cleaned)

    # If the model prefixed prose before the JSON object, find the first '{'
    brace_idx = cleaned.find("{")
    if brace_idx > 0:
        cleaned = cleaned[brace_idx:]

    return json.loads(cleaned)


class GroqRateLimitError(RuntimeError):
    """Raised when Groq returns 429 after all retry attempts are exhausted."""


def _parse_retry_wait_seconds(response: httpx.Response, attempt: int) -> float:
    """Compute wait time from Groq headers with safe fallbacks.

    Supports:
    - Retry-After: seconds or HTTP-date
    - x-ratelimit-reset-requests: often epoch seconds/ms in vendor APIs
    - fallback: exponential backoff with jitter
    """
    now = time.time()
    retry_after = response.headers.get("retry-after")
    reset_header = response.headers.get("x-ratelimit-reset-requests")

    if retry_after:
        # Numeric seconds is the common format.
        try:
            return max(0.5, min(float(retry_after), 60.0))
        except ValueError:
            # HTTP-date fallback.
            try:
                dt = parsedate_to_datetime(retry_after)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                delta = dt.timestamp() - now
                return max(0.5, min(delta, 60.0))
            except Exception:
                pass

    if reset_header:
        try:
            raw = float(reset_header)
            # Heuristic: very large values are likely epoch milliseconds.
            reset_epoch = raw / 1000.0 if raw > 1e12 else raw
            delta = reset_epoch - now
            if delta > 0:
                return max(0.5, min(delta, 60.0))
        except ValueError:
            pass

    # Exponential fallback with jitter; clamp to 60s to avoid over-sleeping.
    base = min(2 ** (attempt + 1), 30)
    jitter = random.uniform(0.1, 1.0)
    return min(base + jitter, 60.0)


def _wait_for_global_cooldown() -> None:
    """Sleep until process-wide Groq cooldown window has elapsed.

    If the remaining cooldown exceeds 10 s the rate-limit window is still
    active — raise GroqRateLimitError immediately so the caller can fall
    back to static scoring without blocking the request for up to 60 s.
    """
    with _rate_limit_lock:
        wait = _next_groq_request_at - time.monotonic()
    if wait > 10:
        raise GroqRateLimitError(
            f"Groq cooldown active ({wait:.0f}s remaining). "
            "Falling back to static scoring."
        )
    if wait > 0:
        time.sleep(wait)


def _enforce_client_side_pacing() -> None:
    """Throttle outgoing Groq calls to stay below configured RPM."""
    min_interval = 60.0 / float(GROQ_REQUESTS_PER_MINUTE)
    with _rate_limit_lock:
        global _last_groq_request_at
        now = time.monotonic()
        wait = (_last_groq_request_at + min_interval) - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _last_groq_request_at = now


def _set_global_cooldown(wait_seconds: float) -> None:
    """Push out next allowed request time after a 429."""
    with _rate_limit_lock:
        global _next_groq_request_at
        _next_groq_request_at = max(
            _next_groq_request_at,
            time.monotonic() + max(0.5, wait_seconds),
        )


def _chat_completion(
    messages: list[dict[str, str]],
    *,
    json_mode: bool,
    model: str | None = None,
    max_retries: int = 3,
) -> tuple[str, dict[str, Any]]:
    """Call the Groq chat completions endpoint with automatic 429 retry.

    Args:
        messages:     Ordered list of {role, content} dicts.
        json_mode:    If True, forces ``response_format: {type: json_object}``.
        model:        Optional model override.  Defaults to ``GROQ_MODEL``
                      (evaluation model).  Pass ``GROQ_REWRITE_MODEL`` for
                      reasoning-capable rewrites.
        max_retries:  Number of retry attempts on 429 before raising
                      ``GroqRateLimitError``.  Back-off: 2, 4, 8 s (capped at 30 s).
    """
    active_model = model or GROQ_MODEL
    payload: dict[str, Any] = {
        "model": active_model,
        "messages": messages,
        "temperature": 0,
    }
    # Reasoning models (Qwen3, DeepSeek R1) emit <think> blocks and reject
    # response_format: json_object — skip JSON mode for them; _parse_json_object
    # will strip the <think> block and locate the JSON object in the response.
    if json_mode and active_model not in _NO_JSON_MODE_MODELS:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(GROQ_TIMEOUT_SECONDS)

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        _wait_for_global_cooldown()
        _enforce_client_side_pacing()
        with httpx.Client(timeout=timeout) as client:
            response = client.post(GROQ_CHAT_URL, json=payload, headers=headers)

        if response.status_code == 429:
            wait = _parse_retry_wait_seconds(response, attempt)
            _set_global_cooldown(wait)

            last_exc = httpx.HTTPStatusError(
                f"429 Too Many Requests (attempt {attempt + 1}/{max_retries})",
                request=response.request,
                response=response,
            )
            # If Groq says wait longer than 10 s the account is throttled for
            # the current rate-limit window (token-per-minute or RPM cap hit).
            # Waiting and retrying would stall the request for minutes — instead
            # raise immediately so the caller can fall back to static scoring
            # and the user receives a result within seconds.
            if wait > 10:
                raise GroqRateLimitError(
                    f"Groq rate limit active (retry-after {wait:.0f}s). "
                    f"Falling back to static scoring. "
                    f"(Free-tier limit: ~30 req/min, ~14 400 tokens/min for {active_model})"
                ) from last_exc
            if attempt < max_retries - 1:
                time.sleep(wait)
                continue
            # All retries exhausted
            raise GroqRateLimitError(
                f"Groq rate limit exceeded after {max_retries} attempts. "
                f"Falling back to static scoring. "
                f"(Free-tier limit: ~30 req/min for {active_model})"
            ) from last_exc

        response.raise_for_status()
        data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Groq response missing choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Groq response missing content")
        raw_usage = data.get("usage") or {}
        usage = {
            "prompt_tokens": int(raw_usage.get("prompt_tokens") or 0),
            "completion_tokens": int(raw_usage.get("completion_tokens") or 0),
            "total_tokens": int(raw_usage.get("total_tokens") or 0),
        }
        return content, usage

    # Should never reach here — loop either returns or raises
    raise RuntimeError("_chat_completion: unexpected loop exit")


def _build_dimension_criteria(
    weights: dict[str, Any],
    validator_checks: list,
    keyword_checks: dict,
    penalty_triggers: list,
) -> list[dict[str, Any]]:
    """Map each dimension to its specific validation criteria and keywords.

    This gives the LLM an explicit per-dimension checklist so it evaluates each
    dimension against concrete evidence rather than guessing from a flat list.
    """
    dims: list[dict[str, Any]] = []
    for dim_name, weight in weights.items():
        dim_lower = dim_name.lower().replace("_", " ")
        # Cap keywords at 5 — enough signal, avoids over-inflating the payload.
        kw: list[str] = keyword_checks.get(dim_name, [])[:5]
        # Find validator_checks that are relevant to this dimension by name or keyword overlap.
        # Cap at 4 (down from 6) — top criteria give sufficient pass/fail signal.
        relevant: list[str] = []
        for vc in validator_checks:
            if isinstance(vc, str) and (
                dim_lower in vc.lower()
                or any(k.lower() in vc.lower() for k in kw if k)
            ):
                relevant.append(vc)
        # Find penalty triggers relevant to this dimension
        triggers: list[str] = []
        for pt in penalty_triggers:
            if isinstance(pt, str) and dim_lower in pt.lower():
                triggers.append(pt)
        dims.append({
            "name": dim_name,
            "weight": weight,
            "pass_requires": (
                "Prompt explicitly contains keyword evidence AND satisfies at least one criterion below."
                if kw or relevant else
                "Evaluate based on general quality for this dimension."
            ),
            "keyword_evidence": kw,
            "criteria": relevant[:4] if relevant else [],
            "penalty_triggers": triggers[:3] if triggers else [],
        })
    return dims


def llm_evaluate_prompt(
    prompt_text: str,
    *,
    persona: dict[str, Any],
    guidelines: dict[str, Any],
    source_of_truth_doc: str,
    source_of_truth_scope: str,
) -> LlmEvaluateResult:
    # --- Extract persona context ---
    weights: dict[str, Any] = persona.get("weights") if isinstance(persona.get("weights"), dict) else {}
    validator_checks: list = persona.get("validator_checks") if isinstance(persona.get("validator_checks"), list) else []
    keyword_checks: dict = persona.get("keyword_checks") if isinstance(persona.get("keyword_checks"), dict) else {}
    penalty_triggers: list = persona.get("penalty_triggers") if isinstance(persona.get("penalty_triggers"), list) else []

    # --- Extract guidelines context ---
    global_checks_raw = guidelines.get("global_checks") if isinstance(guidelines.get("global_checks"), list) else []
    global_checks: list[dict[str, Any]] = []
    for item in global_checks_raw:
        if isinstance(item, dict):
            # Send only the fields the LLM needs for pass/fail scoring.
            # Dropping applies_when_any and issue_if_missing saves ~30% of
            # the global_checks payload without affecting evaluation accuracy.
            global_checks.append({
                "id": str(item.get("id", "")),
                "description": str(item.get("description", "")),
                "keywords": item.get("keywords", [])[:8],  # cap per-check keywords
            })

    priorities = guidelines.get("claude_curated_priorities") if isinstance(guidelines.get("claude_curated_priorities"), list) else []
    penalty_per_miss = int(guidelines.get("strict_penalty_per_miss", 3))
    penalty_cap = int(guidelines.get("strict_penalty_cap", 15))
    strict_mode = bool(guidelines.get("strict_mode", True))

    # Build per-dimension criteria mapping for precise evaluation
    dimension_criteria = _build_dimension_criteria(weights, validator_checks, keyword_checks, penalty_triggers)

    # --- Hardened system prompt — strict source-of-truth evaluation, no hallucination ---
    system = (
        "You are an enterprise prompt-quality auditor. "
        "Your ONLY job is to evaluate the USER PROMPT strictly against the provided "
        "source-of-truth framework. Do NOT use your own judgment, heuristics, or general "
        "knowledge about prompt quality.\n\n"
        "━━━ EVALUATION RULES (NON-NEGOTIABLE) ━━━\n"
        "1. DIMENSIONS: Evaluate ONLY the dimensions listed in persona_dimensions. "
        "   Do NOT add, rename, or remove any dimension.\n"
        "2. PASS CRITERIA: Mark passed=true for a dimension ONLY when the prompt text "
        "   explicitly contains at least one keyword_evidence item AND satisfies at least "
        "   one criterion from that dimension's criteria list. "
        "   If the dimension has no keyword_evidence, use the criteria list alone. "
        "   Absence of evidence = FAILED — never assume implicit compliance.\n"
        "3. SCORE: Each dimension score = its weight if passed, else 0. No partial scores.\n"
        "4. GLOBAL CHECKS: Evaluate each global_check by scanning for its keywords in the prompt. "
        "   If none of the check's keywords appear, mark it failed.\n"
        "5. SEMANTIC SCORE: Compute as shown — do not substitute your own estimate.\n"
        "6. ISSUES: List ONLY gaps that are ACTUALLY missing from the prompt. "
        "   Each issue must be unique — different root cause, different wording. "
        "   Do NOT repeat or rephrase the same gap. Maximum 6 issues. "
        "   A better prompt (with more criteria satisfied) must yield fewer issues.\n"
        "7. STRENGTHS: List ONLY elements that ARE explicitly present in the prompt. "
        "   Do not list things that are absent as strengths. Maximum 5 strengths.\n"
        "8. NO HALLUCINATION: Do not infer, assume, or credit the prompt for content "
        "   that is not literally present in the prompt text.\n\n"
        "━━━ SCORING FORMULA ━━━\n"
        "  base_score = (sum_of_passed_weights / sum_of_all_weights) × 100\n"
        f"  guideline_penalty = min(failed_global_check_count × {penalty_per_miss}, {penalty_cap})\n"
        "  semantic_score = base_score − guideline_penalty  (minimum 0)\n\n"
        "RATING THRESHOLDS: ≥85 Excellent | ≥70 Good | ≥50 Needs Improvement | <50 Poor\n\n"
        f"STRICT MODE: {'ON' if strict_mode else 'OFF'} | "
        f"{penalty_per_miss} pts per failed global check | cap: {penalty_cap} pts\n\n"
        "━━━ MANDATORY RETURN FORMAT — single JSON object, no markdown, no prose ━━━\n"
        '{"semantic_score":<number 0-100>,'
        '"dimension_scores":[{"name":"<exact_dimension_name>","score":<weight_or_0>,'
        '"weight":<weight>,"passed":<true/false>,"notes":"<one specific sentence citing evidence or gap>"}],'
        '"guideline_checks":[{"id":"<exact_check_id>","passed":<true/false>,'
        f'"penalty":<0_or_{penalty_per_miss}>,"issue":"<issue_if_missing or empty string>"' + '}],'
        '"issues":["<unique actionable gap — cite the missing element>"],'
        '"strengths":["<element that IS present in the prompt>"]}'
    )

    # --- Build user payload — scoped to what the LLM strictly needs ---
    # source_of_truth_scope is omitted: it's verbose context already implied
    # by source_of_truth_document; removing it saves ~50-80 tokens per request.
    # penalty_triggers capped at 5 (was 10) — top triggers give enough signal.
    # org_guideline_priorities capped at 5 (was full list) — top priorities suffice.
    user_payload = {
        "source_of_truth_document": source_of_truth_doc,
        "persona_id": persona.get("id"),
        "persona_name": persona.get("name"),
        "persona_dimensions": dimension_criteria,
        "persona_penalty_triggers": penalty_triggers[:5],
        "org_guideline_priorities": priorities[:5],
        "global_checks": global_checks,
        "user_prompt": prompt_text,
    }

    content, eval_usage = _chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        json_mode=True,
    )
    parsed = _parse_json_object(content)

    # --- Validate core schema ---
    if LLM_STRICT_SCHEMA:
        required = {"semantic_score", "issues", "strengths"}
        if not required.issubset(parsed.keys()):
            raise ValueError("Groq eval JSON schema missing required keys")
        if not isinstance(parsed.get("issues"), list) or not isinstance(parsed.get("strengths"), list):
            raise ValueError("Groq eval JSON schema has invalid list fields")

    # --- Parse semantic_score ---
    try:
        semantic_score = float(parsed.get("semantic_score"))
    except (TypeError, ValueError):
        semantic_score = 0.0
    semantic_score = max(0.0, min(100.0, semantic_score))

    # --- Parse issues and strengths ---
    raw_issues = parsed.get("issues") if isinstance(parsed.get("issues"), list) else []
    raw_strengths = parsed.get("strengths") if isinstance(parsed.get("strengths"), list) else []
    issue_list = [str(item).strip() for item in raw_issues if str(item).strip()]
    strength_list = [str(item).strip() for item in raw_strengths if str(item).strip()]

    # --- Parse dimension_scores (soft-required: don't fail if missing) ---
    dim_list: list[dict[str, Any]] = []
    raw_dims = parsed.get("dimension_scores")
    if isinstance(raw_dims, list):
        for d in raw_dims:
            if isinstance(d, dict) and d.get("name"):
                try:
                    dim_list.append({
                        "name": str(d["name"]),
                        "score": float(d.get("score", 0)),
                        "weight": float(d.get("weight", 0)),
                        "passed": bool(d.get("passed", False)),
                        "notes": str(d["notes"]) if d.get("notes") else None,
                    })
                except (TypeError, ValueError):
                    continue

    # --- Parse guideline_checks (soft-required) ---
    gc_list: list[dict[str, Any]] = []
    raw_gc = parsed.get("guideline_checks")
    if isinstance(raw_gc, list):
        for g in raw_gc:
            if isinstance(g, dict) and g.get("id"):
                try:
                    gc_list.append({
                        "id": str(g["id"]),
                        "passed": bool(g.get("passed", True)),
                        "penalty": int(g.get("penalty", 0)),
                        "issue": str(g["issue"]) if g.get("issue") else "",
                    })
                except (TypeError, ValueError):
                    continue

    return LlmEvaluateResult(
        semantic_score=semantic_score,
        issues=issue_list,
        strengths=strength_list,
        dimension_scores=dim_list,
        guideline_checks=gc_list,
        token_usage=eval_usage,
    )


_ECHO_HEADERS = re.compile(
    r"#+\s*(original\s*(user\s*)?(request|prompt|input)|source\s*prompt|input\s*prompt)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_original_echo(improved: str, original: str) -> str:
    """Remove any section where the LLM echoed back the original prompt verbatim.

    Two patterns are detected and removed:

    1. Echo heading  — a markdown heading such as '# Original user request' or
       '# Input' immediately followed by the original text.  Everything from the
       heading onward is stripped.

    2. Trailing verbatim append — the original text appears in the FINAL 35 % of
       the improved prompt (i.e., it was appended at the end, not embedded inside
       a structural ## section).  We intentionally do NOT strip when the original
       text appears inside an early section (e.g. ## Task), because a well-written
       improved prompt naturally re-uses language from the original within its
       structured sections.
    """
    # Pattern 1: strip at the echo heading
    match = _ECHO_HEADERS.search(improved)
    if match:
        improved = improved[:match.start()].rstrip()

    # Pattern 2: trailing verbatim echo — only strip when the match sits in the
    # final 35 % of the string so we don't cut into legitimate ## Task content.
    orig_stripped = original.strip()
    if orig_stripped and orig_stripped in improved:
        idx = improved.rfind(orig_stripped)
        tail_threshold = int(len(improved) * 0.65)
        if idx > 0 and idx >= tail_threshold:
            improved = improved[:idx].rstrip()

    return improved.strip()


def llm_rewrite_prompt(
    prompt_text: str,
    *,
    persona: dict[str, Any],
    guidelines: dict[str, Any],
    issues: list[str],
) -> LlmRewriteResult:
    global_checks_raw = guidelines.get("global_checks") if isinstance(guidelines.get("global_checks"), list) else []
    rule_lines: list[str] = []
    # Cap at 8 guideline rules (was 15) — the rewrite only needs the top rules
    # to anchor the improved_prompt; additional rules add tokens with no benefit.
    for item in global_checks_raw[:8]:
        if isinstance(item, dict):
            rule_lines.append(f"- {item.get('id', '')}: {item.get('description', '')}")

    priorities = guidelines.get("claude_curated_priorities") if isinstance(guidelines.get("claude_curated_priorities"), list) else []
    # Cap at 5 priorities (was 8) — top priorities are all the rewrite needs.
    priority_lines = "\n".join(f"- {p}" for p in priorities[:5] if isinstance(p, str))
    # Cap at 8 issues (was 12) — beyond 8 the LLM dilutes rather than focuses.
    issue_lines = "\n".join(f"- {issue}" for issue in issues[:8])

    persona_id = persona.get("id", "persona_0")

    # ---------------------------------------------------------------------------
    # Persona section maps — exact ## headings + style note per persona.
    # These are the ONLY headings the LLM is allowed to use in improved_prompt.
    # ---------------------------------------------------------------------------
    persona_section_maps: dict[str, tuple[list[str], str]] = {
        "persona_0": (
            ["## Role", "## Task", "## Context", "## Output Format", "## Constraints"],
            "Plain language. Executive-ready. No technical jargon.",
        ),
        "persona_1": (
            [
                "## Role", "## Task", "## Codebase Context",
                "## Acceptance Criteria", "## Edge Cases", "## Output Format",
            ],
            "Technically precise. Carry language, framework, and version exactly as stated. "
            "Use code-block directives for expected output.",
        ),
        "persona_2": (
            [
                "## Role", "## Report Type", "## Sprint / Project Context",
                "## Data References", "## Output Format", "## Constraints",
            ],
            "Decision-ready and traceable. Keep sprint dates, audience, and data references "
            "exactly as stated — never invent them.",
        ),
        "persona_3": (
            [
                "## Role", "## Task", "## Source Documents",
                "## Inference Policy", "## Output Format",
            ],
            "Grounded in source material. Carry document names, section refs, and dates verbatim.",
        ),
        "persona_4": (
            [
                "## Role", "## Task", "## Customer Context",
                "## Policy / SLA Constraints", "## Output Format",
            ],
            "Empathetic, compliant, concise. "
            "Tone and empathy guidance goes INSIDE ## Role (one sentence) or ## Customer Context (as a bullet). "
            "NEVER create a separate ## Tone Directive section. "
            "NEVER create a ## Next Action section — the task directive is already in ## Task. "
            "## Task is ONE imperative sentence starting with an action verb (Draft / Write / Create).",
        ),
    }
    sections, style_note = persona_section_maps.get(
        persona_id, persona_section_maps["persona_0"]
    )
    section_list = "\n".join(f"    {s}" for s in sections)

    # ---------------------------------------------------------------------------
    # Known framework → required language mappings for contradiction detection.
    # The LLM receives this as a lookup table in the system prompt.
    # ---------------------------------------------------------------------------
    framework_language_table = (
        "  FastAPI → Python | Django → Python | Flask → Python | Tornado → Python\n"
        "  Spring Boot → Java | Hibernate → Java | Maven → Java | Gradle → Java/Kotlin\n"
        "  Express.js → Node.js | NestJS → Node.js | Next.js → Node.js/TypeScript\n"
        "  React → JavaScript/TypeScript | Vue.js → JavaScript/TypeScript\n"
        "  Angular → TypeScript | Svelte → JavaScript/TypeScript\n"
        "  ASP.NET / .NET → C# or VB.NET | Entity Framework → C#\n"
        "  Laravel → PHP | Symfony → PHP | CodeIgniter → PHP\n"
        "  Ruby on Rails → Ruby | Sinatra → Ruby\n"
        "  Gin → Go | Echo → Go | Fiber → Go\n"
        "  Actix → Rust | Axum → Rust\n"
    )

    system = (
        "You are a strict enterprise prompt architect. "
        "Your ONLY job is to rewrite the given prompt into a structured prompt "
        "using the mandatory section format. Follow ALL steps below in order.\n\n"

        # ── STEP 1: FACT EXTRACTION ──────────────────────────────────────────
        "━━━ STEP 1 — EXTRACT IMMUTABLE FACTS (silent, before writing) ━━━\n"
        "Scan the original prompt and identify every EXPLICIT fact. These are IMMUTABLE — "
        "carry them forward UNCHANGED into improved_prompt. Do NOT alter any of them.\n"
        "Extract:\n"
        "  • Programming language  (e.g., Java, Python, Go, TypeScript)\n"
        "  • Frameworks / libraries (e.g., FastAPI, Spring Boot, React, Express.js)\n"
        "  • Version numbers        (e.g., Python 3.10, SQLAlchemy 1.4) — carry verbatim\n"
        "  • Endpoint paths / HTTP methods (e.g., POST /users, GET /orders)\n"
        "  • Field / column names   (e.g., name, email, password, created_at)\n"
        "  • Stated HTTP status codes (e.g., 400, 409, 200)\n"
        "  • Output format directives (e.g., 'return as code blocks', 'JSON response')\n"
        "  • Scope inclusions / exclusions explicitly stated\n"
        "  • Ticket IDs, sprint names, dates — only if explicitly present\n"
        "  • Test / quality requirements explicitly stated "
        "    (e.g., 'unit tests', 'error handling', 'integration tests') "
        "    → these are FACTS; carry them into ## Acceptance Criteria\n"
        "  • Edge cases / error scenarios explicitly listed "
        "    (e.g., 'missing fields', 'duplicate email', 'empty payload', 'null input') "
        "    → these are FACTS; carry them verbatim into ## Edge Cases\n"
        "Anything NOT in this list = NOT a fact = do NOT add it.\n\n"

        # ── STEP 2: CONTRADICTION DETECTION ─────────────────────────────────
        "━━━ STEP 2 — DETECT & FLAG CONTRADICTIONS (add to unresolved_gaps) ━━━\n"
        "Before rewriting, check for these contradiction patterns:\n\n"
        "  C1. FRAMEWORK ↔ LANGUAGE MISMATCH\n"
        "      Use this lookup table:\n"
        f"{framework_language_table}"
        "      If the original says 'FastAPI in Java': FastAPI requires Python but prompt says Java.\n"
        "      → Keep BOTH values unchanged in the improved_prompt.\n"
        "      → Add to unresolved_gaps: "
        "'Contradiction: FastAPI is a Python-only framework but the prompt specifies Java. "
        "Clarify whether the intended language is Python (use FastAPI) or Java "
        "(use Spring Boot / Micronaut / Quarkus).'\n\n"
        "  C2. CONFLICTING OUTPUT FORMATS\n"
        "      e.g., 'return JSON AND a Markdown table' → both stated but incompatible.\n"
        "      → Keep both, flag: 'Contradiction: conflicting output formats requested — "
        "clarify which is primary.'\n\n"
        "  C3. CONFLICTING SCOPE\n"
        "      e.g., 'include authentication' AND 'authentication is out-of-scope'.\n"
        "      → Keep both, flag: 'Contradiction: authentication listed as both in-scope "
        "and out-of-scope — clarify.'\n\n"
        "  C4. 'LATEST VERSION' AMBIGUITY\n"
        "      If the original says 'latest version' — do NOT resolve to a specific version.\n"
        "      → Write exactly: '<library> (version not pinned — use latest stable)'\n"
        "      → Add to unresolved_gaps: 'Ambiguity: version not pinned for <library> — "
        "pin a specific version for reproducible results.'\n\n"
        "  C5. MISSING CRITICAL FIELD (for terse prompts <20 words)\n"
        "      If the prompt is too terse and has NO language/domain context at all\n"
        "      (e.g. only a ticket number like '12344' or 'develop code on ticket X'):\n"
        "      → For ## Codebase Context, produce ONLY these 3 lines:\n"
        "          '- Ticket: <ticket number>'\n"
        "          '- Stack: [Specify: Language, Framework, Version — no technical context in original]'\n"
        "          '- Project specifics: [Specify: in-scope file paths, module names, DB details]'\n"
        "      → NEVER generate individual '[Not specified]' lines per field (Language, Framework,\n"
        "        Version, DB, Module/file path, In-scope modules each on their own line).\n"
        "      → Add to unresolved_gaps: 'Missing: no technical stack specified — Language,\n"
        "        Framework, Version required before using this prompt.'\n\n"

        # ── STEP 3: WRITE IMPROVED PROMPT ────────────────────────────────────
        "━━━ STEP 3 — WRITE improved_prompt ━━━\n"
        "Use EXACTLY these ## headings in EXACTLY this order:\n"
        f"{section_list}\n\n"
        f"STYLE: {style_note}\n\n"
        "SECTION RULES:\n"
        "  • Populate each section primarily with facts extracted in Step 1.\n"
        "  • Expand terse facts into clear, expert-level full sentences.\n"
        "  • If a section has NO matching fact from the original → write a concise\n"
        "    instructional placeholder: [Specify: <what is needed>] — do NOT write\n"
        "    'Not specified in original' verbatim for every empty section.\n"
        "  • Do NOT write placeholder versions, fake ticket IDs, assumed scope,\n"
        "    invented dates, or implied requirements.\n"
        "  • ## Role: Write a specific expert role sentence anchored to the task domain.\n"
        "    If the original has no role — DERIVE one from the task + tech stack.\n"
        "    Good: 'You are a Senior Java Engineer specialising in MongoDB integration.'\n"
        "    Bad:  'Developer' or '[Not specified]'\n"
        "  • ## Task: Write ONE direct action sentence expanding the original intent.\n"
        "    NEVER write 'Based on the following request:' or re-paste the original.\n"
        "  • ## Codebase Context / ## Context: Populate from Step 1 tech-stack facts.\n"
        "    Include language, framework, version, and relevant modules when derivable.\n"
        "    CONSOLIDATION RULE: When fields are missing, NEVER generate one [Not specified]\n"
        "    per field. Instead consolidate ALL missing user-specific fields into ONE line:\n"
        "    '- Project specifics: [Specify: relevant file paths, class signatures, in-scope modules]'\n"
        "    When NO domain context exists at all → use C5 rule (3-line format).\n"
        "  • ## Edge Cases: Carry verbatim edge-case facts from Step 1.\n"
        "    Expand each into one clear sentence describing the scenario and expected handling.\n"
        "    ONLY use [Specify:...] when the original has absolutely no error/boundary language.\n"
        "  • ## Acceptance Criteria: Derive measurable pass/fail criteria from the stated\n"
        "    requirements. Each criterion must be independently verifiable.\n"
        "    Good: '- CRUD operations return correct status codes for all success/error paths'\n"
        "    Bad:  '- The task should be done correctly'\n"
        "  • ## Output Format: State the exact deliverable format, structure, and length.\n"
        "    Good: 'Return a single Java class with inline Javadoc comments in a code block.'\n"
        "    Bad:  'Code blocks'\n"
        "  • 'Gaps to resolve' items are META-INSTRUCTIONS about missing content.\n"
        "    NEVER copy them verbatim as section content — use them to guide what you write.\n\n"

        # ── ANTI-HALLUCINATION RULES ─────────────────────────────────────────
        "━━━ ANTI-HALLUCINATION RULES (NON-NEGOTIABLE) ━━━\n"
        "  H1. NEVER change, substitute, or 'fix' the programming language.\n"
        "      Java stays Java. Python stays Python. If it seems wrong → flag in unresolved_gaps.\n"
        "  H2. NEVER invent version numbers. "
        "      'Java' (no version stated) → write 'Java (version not specified)'.\n"
        "      'Python 3.10' → write 'Python 3.10' — not 3.9, not 3.11.\n"
        "  H3. NEVER invent ticket IDs, story IDs, sprint names, team names, or dates.\n"
        "  H4. NEVER invent scope items. "
        "      'include auth' or 'exclude payments' must appear verbatim in the original.\n"
        "  H5. NEVER invent HTTP status codes, response schemas, or field names "
        "      not present in the original.\n"
        "  H6. NEVER inject implicit requirements unless they directly follow from\n"
        "      a stated fact (e.g., 'CRUD operations' implies Create/Read/Update/Delete).\n"
        "  H7. NEVER resolve 'latest version' to a specific version number.\n"
        "  H8. Specificity = expand what IS there into precise expert sentences.\n"
        "      A terse original like 'implement a DB connector' should become a detailed\n"
        "      specification — not stay equally terse.\n\n"

        # ── OUTPUT FORMAT ────────────────────────────────────────────────────
        "━━━ OUTPUT FORMAT ━━━\n"
        "Return ONLY this JSON object — no markdown fences, no prose outside it:\n"
        '{"improved_prompt": "<full rewritten prompt using ## sections>",'
        ' "applied_guidelines": ["<rule ID or name applied>", ...],'
        ' "unresolved_gaps": ["<Contradiction: ...>" or "<Ambiguity: ...>" or "<Missing: ...>", ...]}\n\n'
        "FINAL CHECKS before writing:\n"
        "  ✓ improved_prompt starts with the first ## heading — zero preamble.\n"
        "  ✓ improved_prompt does NOT contain the original prompt text verbatim.\n"
        "  ✓ improved_prompt has NO section labelled Original / Input / Source / Echo.\n"
        "  ✓ Every fact from Step 1 appears unchanged in improved_prompt.\n"
        "  ✓ Every contradiction from Step 2 appears in unresolved_gaps."
    )

    # When there are no issues the primary task is structural reorganisation + fact preservation.
    gaps_block = (
        f"Gaps to resolve (address each under the most relevant ## section):\n{issue_lines}"
        if issue_lines
        else (
            "Gaps to resolve: none detected — the original scores well on content.\n"
            "PRIMARY TASK: reorganise into the mandatory ## section format.\n"
            "Use [Not specified in original — add before using] for any section with no "
            "matching content. Do NOT invent content to fill empty sections."
        )
    )
    user = (
        f"Persona: {persona.get('name')} ({persona_id})\n\n"
        "ANCHOR — carry these values from the original UNCHANGED (do not alter language, "
        "framework names, endpoint paths, field names, error codes, or output directives).\n\n"
        f"Org guideline priorities:\n{priority_lines or '- clarity, context, output format, constraints'}\n\n"
        f"Guideline checks to satisfy:\n{chr(10).join(rule_lines) if rule_lines else '- clarity, context, output format, constraints'}\n\n"
        f"{gaps_block}\n\n"
        f"Prompt to rewrite:\n{prompt_text.strip()}\n"
    )
    content, rewrite_usage = _chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        json_mode=True,
        model=GROQ_REWRITE_MODEL,
    )
    parsed = _parse_json_object(content)

    # Smaller models (8b) sometimes use alternate key names or return the prompt
    # as a nested dict {section_heading: content} instead of a markdown string.
    # Normalise all variants to a plain markdown string.
    _PROMPT_KEY_CANDIDATES = (
        "improved_prompt", "rewritten_prompt", "improved_response",
        "improved_version", "result", "prompt", "output",
    )
    improved_prompt: str | None = None
    for _key in _PROMPT_KEY_CANDIDATES:
        _val = parsed.get(_key)
        if isinstance(_val, str) and _val.strip():
            improved_prompt = _val
            break
        if isinstance(_val, dict) and _val:
            # 8b model returned prompt as {heading: content} dict → convert to markdown
            _md_lines: list[str] = []
            for _heading, _body in _val.items():
                _heading_str = str(_heading).strip()
                if not _heading_str.startswith("#"):
                    _heading_str = f"## {_heading_str}"
                _md_lines.append(_heading_str)
                if _body:
                    _md_lines.append(str(_body).strip())
                _md_lines.append("")
            improved_prompt = "\n".join(_md_lines).strip()
            break
    if not improved_prompt:
        # Last resort: grab the longest string value in the parsed dict
        _candidates = [v for v in parsed.values() if isinstance(v, str) and v.strip()]
        if _candidates:
            improved_prompt = max(_candidates, key=len)
    if not improved_prompt or not improved_prompt.strip():
        raise ValueError(
            f"Groq rewrite improved_prompt unresolvable. "
            f"Keys={list(parsed.keys())}"
        )
    # Safety strip: remove any trailing section that echoes the original prompt back.
    # LLMs occasionally append "# Original user request\n<original>" despite the rule.
    improved_prompt = _strip_original_echo(improved_prompt, prompt_text)

    applied_raw = parsed.get("applied_guidelines")
    unresolved_raw = parsed.get("unresolved_gaps")
    applied = applied_raw if isinstance(applied_raw, list) else []
    unresolved = unresolved_raw if isinstance(unresolved_raw, list) else []
    applied_out = [str(item).strip() for item in applied if str(item).strip()][:10]
    unresolved_out = [str(item).strip() for item in unresolved if str(item).strip()][:10]
    return LlmRewriteResult(
        improved_prompt=improved_prompt.strip(),
        applied_guidelines=applied_out,
        unresolved_gaps=unresolved_out,
        token_usage=rewrite_usage,
    )


# ---------------------------------------------------------------------------
# Async wrappers — Groq's sync functions use threading.Lock for rate-limiting.
# Wrapping the INDIVIDUAL functions (not the entire validation pipeline) in
# asyncio.to_thread keeps the lock scope tight and avoids event-loop deadlocks.
# ---------------------------------------------------------------------------

async def llm_evaluate_prompt_async(
    prompt_text: str,
    *,
    persona: dict[str, Any],
    guidelines: dict[str, Any],
    source_of_truth_doc: str,
    source_of_truth_scope: str,
) -> LlmEvaluateResult:
    """Async wrapper — runs sync llm_evaluate_prompt in thread pool."""
    return await asyncio.to_thread(
        llm_evaluate_prompt, prompt_text,
        persona=persona, guidelines=guidelines,
        source_of_truth_doc=source_of_truth_doc,
        source_of_truth_scope=source_of_truth_scope,
    )


async def llm_rewrite_prompt_async(
    prompt_text: str,
    *,
    persona: dict[str, Any],
    guidelines: dict[str, Any],
    issues: list[str],
) -> LlmRewriteResult:
    """Async wrapper — runs sync llm_rewrite_prompt in thread pool."""
    return await asyncio.to_thread(
        llm_rewrite_prompt, prompt_text,
        persona=persona, guidelines=guidelines, issues=issues,
    )
