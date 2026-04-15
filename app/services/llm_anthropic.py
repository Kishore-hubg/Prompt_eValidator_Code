from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.settings import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    ANTHROPIC_TIMEOUT_SECONDS,
    LLM_STRICT_SCHEMA,
)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


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
    return bool(ANTHROPIC_API_KEY)


def _strip_code_fences(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```\s*$", "", value)
    return value.strip()


def _parse_json_object(content: str) -> dict[str, Any]:
    return json.loads(_strip_code_fences(content))


def _chat_completion(system: str, user_content: str, max_tokens: int = 4096) -> tuple[str, dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": user_content}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    timeout = httpx.Timeout(ANTHROPIC_TIMEOUT_SECONDS)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(ANTHROPIC_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    raw_usage = data.get("usage") or {}
    usage = {
        "prompt_tokens": int(raw_usage.get("input_tokens") or 0),
        "completion_tokens": int(raw_usage.get("output_tokens") or 0),
        "total_tokens": int((raw_usage.get("input_tokens") or 0) + (raw_usage.get("output_tokens") or 0)),
    }
    blocks = data.get("content") or []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                return text, usage
    raise ValueError("Anthropic response missing text block")


def _build_dimension_criteria(
    weights: dict[str, Any],
    validator_checks: list,
    keyword_checks: dict,
    penalty_triggers: list,
) -> list[dict[str, Any]]:
    """Map each dimension to its specific validation criteria and keywords."""
    dims: list[dict[str, Any]] = []
    for dim_name, weight in weights.items():
        dim_lower = dim_name.lower().replace("_", " ")
        # Cap keywords at 5 — sufficient signal, avoids over-inflating the payload.
        kw: list[str] = keyword_checks.get(dim_name, [])[:5]
        relevant: list[str] = []
        for vc in validator_checks:
            if isinstance(vc, str) and (
                dim_lower in vc.lower()
                or any(k.lower() in vc.lower() for k in kw if k)
            ):
                relevant.append(vc)
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
            # Send only id, description, keywords — drops verbose fields to save tokens.
            global_checks.append({
                "id": str(item.get("id", "")),
                "description": str(item.get("description", "")),
                "keywords": item.get("keywords", [])[:8],
            })

    priorities = guidelines.get("claude_curated_priorities") if isinstance(guidelines.get("claude_curated_priorities"), list) else []
    penalty_per_miss = int(guidelines.get("strict_penalty_per_miss", 3))
    penalty_cap = int(guidelines.get("strict_penalty_cap", 15))
    strict_mode = bool(guidelines.get("strict_mode", True))

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

    content, eval_usage = _chat_completion(system, json.dumps(user_payload, ensure_ascii=False), max_tokens=1500)
    parsed = _parse_json_object(content)

    # --- Validate core schema ---
    if LLM_STRICT_SCHEMA:
        required = {"semantic_score", "issues", "strengths"}
        if not required.issubset(parsed.keys()):
            raise ValueError("Anthropic eval JSON schema missing required keys")
        if not isinstance(parsed.get("issues"), list) or not isinstance(parsed.get("strengths"), list):
            raise ValueError("Anthropic eval JSON schema has invalid list fields")

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
                        "notes": str(d.get("notes", "")) if d.get("notes") else "",
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
    """Remove any section where the LLM echoed back the original prompt."""
    match = _ECHO_HEADERS.search(improved)
    if match:
        improved = improved[:match.start()].rstrip()
    orig_stripped = original.strip()
    if orig_stripped and orig_stripped in improved:
        idx = improved.rfind(orig_stripped)
        if idx > 0:
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
    for item in global_checks_raw[:8]:
        if isinstance(item, dict):
            rule_lines.append(f"- {item.get('id', '')}: {item.get('description', '')}")

    priorities = guidelines.get("claude_curated_priorities") if isinstance(guidelines.get("claude_curated_priorities"), list) else []
    priority_lines = "\n".join(f"- {p}" for p in priorities[:5] if isinstance(p, str))
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
            "## Task is ONE imperative sentence starting with an action verb (Draft / Write / Create). "
            "## Customer Context captures: issue type, delay/urgency details, audience, and tone expectation as a bullet. "
            "## Policy / SLA Constraints captures: what must be included, what to avoid, and SLA rules.",
        ),
    }
    sections, style_note = persona_section_maps.get(
        persona_id, persona_section_maps["persona_0"]
    )
    section_list = "\n".join(f"    {s}" for s in sections)

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

        "━━━ STEP 0 — NORMALISE INPUT (silent, no output) ━━━\n"
        "Before anything else, silently correct ALL spelling errors and grammar issues.\n"
        "Infer the correct technical term from context — common corrections:\n"
        "  mongoDB/mongo db → MongoDB | expres/expresjs → Express.js\n"
        "  pythno/pythn/pyton → Python | javascrpt/javasript → JavaScript\n"
        "  nodjs/node js → Node.js | recat/raect → React | fasapi → FastAPI\n"
        "  springboot/spring boot → Spring Boot | postgress/postges → PostgreSQL\n"
        "  tets/tset → tests | connetor/conecter → connector | bckend → backend\n"
        "  summrise/sumarise → summarise | documnt/documet → document\n"
        "  endponit/endpoit → endpoint | implment/implemet → implement\n"
        "  authetication/aunthentication → authentication | databse → database\n"
        "If a sentence is grammatically broken (e.g. 'Devlop bckend login cod'), "
        "infer the intended meaning and proceed as if correctly written.\n"
        "NEVER flag spelling as an issue. NEVER show corrections explicitly.\n"
        "This step is SILENT — use the normalised understanding for all steps below.\n\n"

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
        "  C2. CONFLICTING OUTPUT FORMATS — keep both, flag the conflict.\n"
        "  C3. CONFLICTING SCOPE — keep both, flag the conflict.\n"
        "  C4. 'LATEST VERSION' AMBIGUITY — write '<library> (version not pinned — use latest stable)'\n"
        "      and add to unresolved_gaps.\n"
        "  C5. TERSE PROMPT (< 20 words, no stack specified) — DO NOT write [Not specified].\n"
        "      Instead: infer the most appropriate standard stack for the task domain using\n"
        "      your expert knowledge, then add ONE entry to unresolved_gaps:\n"
        "      'Stack not specified in original — defaulted to <your chosen stack>. Confirm before using.'\n"
        "      Example: 'backend login for a web app' → Node.js/TypeScript + Express + JWT + PostgreSQL\n"
        "      Example: 'REST API' with no language → Node.js/TypeScript + Express (most common)\n"
        "      Example: 'data pipeline' with no language → Python + pandas/SQLAlchemy\n"
        "      A smart default is a contribution. A [Not specified] placeholder is a failure.\n\n"

        "━━━ STEP 3 — WRITE improved_prompt ━━━\n"
        "Use EXACTLY these ## headings in EXACTLY this order:\n"
        f"{section_list}\n\n"
        f"STYLE: {style_note}\n\n"
        "━━━ GOLDEN RULE — INTELLIGENT COMPLETION ━━━\n"
        "You are a SENIOR EXPERT. When the original prompt omits a technical detail, "
        "USE YOUR DOMAIN KNOWLEDGE to supply the best-practice default. "
        "NEVER leave a section blank or write '[Not specified]' for anything a senior engineer "
        "would know. A placeholder is a failure — a smart default is a contribution.\n\n"
        "  ALLOWED [Not specified in original — add before using] ONLY for:\n"
        "    - User-specific values that CANNOT be guessed: exact file paths, module names,\n"
        "      internal ticket IDs, sprint names, team names, custom field names,\n"
        "      proprietary connection strings, specific audience names.\n"
        "  FOR EVERYTHING ELSE — fill with expert knowledge. See rules below.\n\n"
        "━━━ MANDATORY FORMAT RULES (apply to every section) ━━━\n"
        "  F1. NEVER write prose paragraphs. Every section body must use:\n"
        "      - Bullet list  (- item) for multi-value sections\n"
        "      - Single imperative sentence for ## Task and ## Role only\n"
        "      BAD:  'The codebase involves Java and MongoDB as the database.'\n"
        "      GOOD: '- Language: Java\\n- Database: MongoDB'\n"
        "  F2. ## Role — MUST be exactly ONE sentence starting with 'You are a …'.\n"
        "      Derive from language + domain. Derivation is ALWAYS possible.\n"
        "      BAD:  'The role for this task is a Java Developer.'\n"
        "      GOOD: 'You are a Senior Java Engineer specialising in MongoDB integration.'\n"
        "  F3. ## Task — MUST be exactly ONE imperative sentence starting with an action verb.\n"
        "      Action verbs: Implement / Create / Write / Design / Analyze / Generate / Build\n"
        "      BAD:  'The task involves implementing a connector considering collection needs.'\n"
        "      GOOD: 'Implement a Java-based MongoDB database connector.'\n"
        "  F4. ## Codebase Context — MUST be a '- Key: Value' bullet list.\n"
        "      RULE: If the original states a version → carry it EXACTLY.\n"
        "      RULE: If the original omits a version → write the current best-practice default.\n"
        "      RULE: If the original omits the language entirely → infer from task domain.\n"
        "        Task domain → recommended default stack (these are examples; apply judgment):\n"
        "          Backend login / auth API  → Node.js 20 LTS + TypeScript + Express + JWT + bcrypt + PostgreSQL\n"
        "          REST API (no lang stated) → Node.js 20 LTS + TypeScript + Express.js 4.x\n"
        "          Data pipeline             → Python 3.12 + pandas + SQLAlchemy\n"
        "          ML / AI feature           → Python 3.12 + FastAPI + PyTorch or scikit-learn\n"
        "          Enterprise API            → Java 17 LTS + Spring Boot 3.x + Maven\n"
        "          CLI tool (no lang)        → Node.js 20 LTS + TypeScript or Python 3.12\n"
        "        Versions: always write 'X.x (latest stable)' or 'X LTS (recommended)'\n"
        "        DO NOT write a specific patch version (never '20.11.1') — use major only.\n"
        "      RULE: For auth/login tasks, ALWAYS include these when not stated:\n"
        "          '- Authentication: JWT (access token + refresh token pattern)'\n"
        "          '- Password hashing: bcrypt (cost factor 12 recommended)'\n"
        "          '- Endpoint: POST /api/auth/login'\n"
        "          '- Request body: { email: string, password: string }'\n"
        "      RULE: Module/file paths, class/interface signatures, in-scope/out-of-scope module\n"
        "            lists are user-specific → NEVER generate individual [Not specified] lines\n"
        "            for each. ALWAYS consolidate ALL missing user-specific fields into ONE line:\n"
        "            '- Project specifics: [Specify: relevant file paths, class/interface signatures,\n"
        "               and in-scope modules for this ticket/task]'\n"
        "      CONSOLIDATION RULE — CRITICAL:\n"
        "        When the original prompt provides NO language/framework/domain context at all\n"
        "        (e.g., only a ticket number like '12344', or 'develop code on ticket X'),\n"
        "        do NOT generate individual [Not specified] for Language, Framework, Version, DB.\n"
        "        Instead produce ONLY:\n"
        "          '- Ticket: <ticket number>'\n"
        "          '- Stack: [Specify: Language, Framework, Version — no technical context in original]'\n"
        "          '- Project specifics: [Specify: in-scope file paths, module names, DB details]'\n"
        "        When domain context EXISTS (e.g., 'backend login', 'data pipeline', 'REST API')\n"
        "        → apply the domain inference rules above and list all derivable fields explicitly.\n"
        "      EXCLUDE all prose about developer skill, knowledge gaps, or recommendations.\n"
        "  F5. ## Acceptance Criteria — MUST be a bullet list of measurable outcomes.\n"
        "      RULE: If the original states criteria → list them exactly.\n"
        "      RULE: If the original states NONE → derive 3–5 sensible acceptance criteria\n"
        "            directly from the ## Task. A senior engineer always knows what 'done' looks like.\n"
        "        Example for MongoDB connector task:\n"
        "          '- Successfully establishes a connection to a MongoDB instance'\n"
        "          '- Returns a usable MongoCollection or MongoCursor reference'\n"
        "          '- Throws a descriptive exception on connection failure'\n"
        "          '- Connection is closed/released properly after use'\n"
        "      NEVER add [QA], [Security], [Scope], [In-scope] labels unless in original.\n"
        "      NEVER use prose.\n"
        "  F6. ## Edge Cases — MUST be a bullet list of specific, named failure scenarios.\n"
        "      RULE: If the original lists edge cases → carry them verbatim.\n"
        "      RULE: If the original lists NONE → derive the top 4–6 edge cases that any\n"
        "            senior engineer would anticipate for this task domain.\n"
        "        Example for MongoDB connector:\n"
        "          '- MongoDB host is unreachable (connection timeout)'\n"
        "          '- Invalid credentials (authentication failure)'\n"
        "          '- Database or collection does not exist'\n"
        "          '- Network interruption mid-query'\n"
        "          '- Null or empty collection returns empty cursor'\n"
        "      NEVER write vague sentences like 'potential errors may occur'.\n"
        "  F7. ## Output Format — MUST be a bullet list of explicit output directives.\n"
        "      RULE: If the original specifies format → use it exactly.\n"
        "      RULE: If the original specifies NONE → derive the most appropriate format\n"
        "            for this task type (code task → code block; analysis → structured report; etc.).\n"
        "        Example for Java code task:\n"
        "          '- Return the full implementation in a single Java code block'\n"
        "          '- Include inline comments explaining key steps'\n"
        "      NEVER write prose. NEVER invent sub-fields not in original.\n\n"
        "SECTION RULES:\n"
        "  • Stated facts from Step 1 → carry EXACTLY unchanged.\n"
        "  • Missing technical fields → fill with domain-expert best-practice defaults.\n"
        "  • User-specific unknowables (file paths, module names, signatures, scope) → ONE consolidated\n"
        "    '- Project specifics: [Specify: ...]' line — NEVER one [Not specified] per field.\n"
        "  • Do NOT write placeholder versions when best-practice defaults are known.\n"
        "  • Do NOT use [Not specified] for Edge Cases, Acceptance Criteria, or Output Format\n"
        "    when the task domain makes appropriate defaults obvious.\n"
        "  • 'Gaps to resolve' items are META-INSTRUCTIONS — NEVER copy them as section content.\n\n"

        "━━━ ANTI-HALLUCINATION RULES (NON-NEGOTIABLE) ━━━\n"
        "  H1. NEVER change, substitute, or 'fix' the programming language.\n"
        "      Java stays Java. Python stays Python. If it seems wrong → flag in unresolved_gaps.\n"
        "  H2. NEVER invent version numbers.\n"
        "  H3. NEVER invent ticket IDs, story IDs, sprint names, team names, or dates.\n"
        "  H4. NEVER invent scope items, sub-categories, or enterprise template fields.\n"
        "  H5. NEVER invent HTTP status codes, response schemas, or field names not in the original.\n"
        "  H6. NEVER inject implicit requirements.\n"
        "  H7. ## Role — ALWAYS derive a specific expert role sentence when the task domain,\n"
        "      language, or technology IS present in the original. Derivation is MANDATORY.\n"
        "      Example: Java + MongoDB → 'You are a Senior Java Engineer specialising in\n"
        "      MongoDB integration and Java Collections design.'\n"
        "      Example: Python + FastAPI → 'You are a Senior Python Engineer specialising\n"
        "      in FastAPI REST API development.'\n"
        "      Use [Not specified in original — add before using] ONLY when the original\n"
        "      contains ZERO technical, domain, or subject-matter context whatsoever.\n"
        "  H8. NEVER resolve 'latest version' to a specific version number.\n"
        "  H9. Specificity = expand what IS there. Never add what is NOT there.\n"
        " H10. NEVER add enterprise boilerplate fields ([QA], [Security], [Scope],\n"
        "      user story IDs, OWASP references, CVE standards, auth mechanisms) unless\n"
        "      those exact terms are present in the original prompt.\n\n"

        "━━━ OUTPUT FORMAT ━━━\n"
        "Return ONLY this JSON object — no markdown fences, no prose outside it:\n"
        '{"improved_prompt": "<full rewritten prompt using ## sections>",'
        ' "applied_guidelines": ["<rule ID or name applied>", ...],'
        ' "unresolved_gaps": ["<Contradiction/Ambiguity/Missing: ...>", ...]}\n\n'
        "FINAL CHECKS before writing:\n"
        "  ✓ improved_prompt starts with the first ## heading — zero preamble.\n"
        "  ✓ improved_prompt does NOT contain the original prompt text verbatim.\n"
        "  ✓ improved_prompt has NO section labelled Original / Input / Source / Echo.\n"
        "  ✓ Every fact from Step 1 appears unchanged in improved_prompt.\n"
        "  ✓ Every contradiction from Step 2 appears in unresolved_gaps.\n"
        "  ✓ ZERO prose paragraphs — every section is bullet lists or a single sentence.\n"
        "  ✓ ## Role starts with 'You are a …' — derived from tech/domain context.\n"
        "  ✓ ## Task is ONE imperative sentence starting with an action verb.\n"
        "  ✓ ## Codebase Context has ZERO individual [Not specified] lines.\n"
        "    If domain context exists → fill Language, Framework, Version, DB with best-practice defaults.\n"
        "    If ONLY a ticket number or no domain context → use exactly 3 lines:\n"
        "      '- Ticket: X', '- Stack: [Specify: ...]', '- Project specifics: [Specify: ...]'\n"
        "    User-specific fields (file paths, class signatures, module names, scope) → ONE consolidated line.\n"
        "  ✓ ## Edge Cases has REAL scenarios — not [Not specified] or vague sentences.\n"
        "  ✓ ## Acceptance Criteria has REAL testable conditions — not [Not specified].\n"
        "  ✓ ## Output Format has REAL directives — not [Not specified].\n"
        "  ✓ [Not specified in original — add before using] appears ONLY for user-specific\n"
        "    values: file paths, ticket IDs, sprint names, internal team/module names."
    )

    gaps_block = (
        f"Gaps to resolve (address each under the most relevant ## section):\n{issue_lines}"
        if issue_lines
        else (
            "Gaps to resolve: none detected — the original scores well on content.\n"
            "PRIMARY TASK: reorganise into the mandatory ## section format.\n"
            "Apply the GOLDEN RULE: use domain expertise to fill every section with\n"
            "best-practice defaults for the task domain.\n"
            "NEVER write [Not specified] for standard technical fields — only for\n"
            "user-specific unknowables: exact file paths, module names, internal ticket\n"
            "IDs, sprint names, team names, proprietary connection strings."
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

    content, rewrite_usage = _chat_completion(system, user)
    parsed = _parse_json_object(content)
    if LLM_STRICT_SCHEMA:
        required = {"improved_prompt", "applied_guidelines", "unresolved_gaps"}
        if not required.issubset(parsed.keys()):
            raise ValueError("Anthropic rewrite JSON schema missing required keys")
        if not isinstance(parsed.get("applied_guidelines"), list) or not isinstance(parsed.get("unresolved_gaps"), list):
            raise ValueError("Anthropic rewrite JSON schema has invalid list fields")
    improved_prompt = parsed.get("improved_prompt")
    if not isinstance(improved_prompt, str) or not improved_prompt.strip():
        raise ValueError("Anthropic rewrite missing non-empty improved_prompt")
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
# Native-async variants — use httpx.AsyncClient so the FastAPI event loop
# is never blocked during Anthropic API calls.
# ---------------------------------------------------------------------------

async def _chat_completion_async(system: str, user_content: str, max_tokens: int = 4096) -> tuple[str, dict[str, Any]]:
    """Async version of _chat_completion using httpx.AsyncClient."""
    payload: dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": user_content}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    timeout = httpx.Timeout(ANTHROPIC_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(ANTHROPIC_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    raw_usage = data.get("usage") or {}
    usage = {
        "prompt_tokens": int(raw_usage.get("input_tokens") or 0),
        "completion_tokens": int(raw_usage.get("output_tokens") or 0),
        "total_tokens": int((raw_usage.get("input_tokens") or 0) + (raw_usage.get("output_tokens") or 0)),
    }
    blocks = data.get("content") or []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                return text, usage
    raise ValueError("Anthropic response missing text block")


async def llm_evaluate_prompt_async(
    prompt_text: str,
    *,
    persona: dict[str, Any],
    guidelines: dict[str, Any],
    source_of_truth_doc: str,
    source_of_truth_scope: str,
) -> LlmEvaluateResult:
    """Async version of llm_evaluate_prompt — identical logic, async HTTP call only."""
    weights: dict[str, Any] = persona.get("weights") if isinstance(persona.get("weights"), dict) else {}
    validator_checks: list = persona.get("validator_checks") if isinstance(persona.get("validator_checks"), list) else []
    keyword_checks: dict = persona.get("keyword_checks") if isinstance(persona.get("keyword_checks"), dict) else {}
    penalty_triggers: list = persona.get("penalty_triggers") if isinstance(persona.get("penalty_triggers"), list) else []

    global_checks_raw = guidelines.get("global_checks") if isinstance(guidelines.get("global_checks"), list) else []
    global_checks: list[dict[str, Any]] = []
    for item in global_checks_raw:
        if isinstance(item, dict):
            global_checks.append({
                "id": str(item.get("id", "")),
                "description": str(item.get("description", "")),
                "keywords": item.get("keywords", [])[:8],
            })

    priorities = guidelines.get("claude_curated_priorities") if isinstance(guidelines.get("claude_curated_priorities"), list) else []
    penalty_per_miss = int(guidelines.get("strict_penalty_per_miss", 3))
    penalty_cap = int(guidelines.get("strict_penalty_cap", 15))
    strict_mode = bool(guidelines.get("strict_mode", True))

    dimension_criteria = _build_dimension_criteria(weights, validator_checks, keyword_checks, penalty_triggers)

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

    content, eval_usage = await _chat_completion_async(system, json.dumps(user_payload, ensure_ascii=False), max_tokens=1500)
    parsed = _parse_json_object(content)

    if LLM_STRICT_SCHEMA:
        required = {"semantic_score", "issues", "strengths"}
        if not required.issubset(parsed.keys()):
            raise ValueError("Anthropic eval JSON schema missing required keys")
        if not isinstance(parsed.get("issues"), list) or not isinstance(parsed.get("strengths"), list):
            raise ValueError("Anthropic eval JSON schema has invalid list fields")

    try:
        semantic_score = float(parsed.get("semantic_score"))
    except (TypeError, ValueError):
        semantic_score = 0.0
    semantic_score = max(0.0, min(100.0, semantic_score))

    raw_issues = parsed.get("issues") if isinstance(parsed.get("issues"), list) else []
    raw_strengths = parsed.get("strengths") if isinstance(parsed.get("strengths"), list) else []
    issue_list = [str(item).strip() for item in raw_issues if str(item).strip()]
    strength_list = [str(item).strip() for item in raw_strengths if str(item).strip()]

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
                        "notes": str(d.get("notes", "")) if d.get("notes") else "",
                    })
                except (TypeError, ValueError):
                    continue

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


async def llm_rewrite_prompt_async(
    prompt_text: str,
    *,
    persona: dict[str, Any],
    guidelines: dict[str, Any],
    issues: list[str],
) -> LlmRewriteResult:
    """Async wrapper for llm_rewrite_prompt — runs in thread pool.

    The rewrite system prompt is large and CPU-bound to build; the HTTP call
    duration dominates (5–8 s).  Running in a thread is correct here — it frees
    the event loop for other concurrent requests while the rewrite executes.
    """
    return await asyncio.to_thread(
        llm_rewrite_prompt, prompt_text,
        persona=persona, guidelines=guidelines, issues=issues,
    )
