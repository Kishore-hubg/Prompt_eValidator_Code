"""improver.py — deterministic (non-LLM) fallback prompt rewriter.

Used when the LLM rewrite call fails or is unavailable.  Produces the same
## section structure as the LLM rewrite so the UI renders consistently
regardless of which path was taken.  Does NOT echo the original prompt back
and does NOT paste evaluation issues as section content.
"""
from __future__ import annotations

import re as _re
from app.services.persona_loader import get_persona

# ---------------------------------------------------------------------------
# Per-persona section configs — mirrors llm_groq.persona_section_maps exactly
# so fallback output is structurally identical to LLM output.
# ---------------------------------------------------------------------------
_PERSONA_SECTIONS: dict[str, dict] = {
    "persona_0": {
        "role": "You are an expert enterprise analyst and business communication specialist.",
        "sections": ["## Role", "## Task", "## Context", "## Output Format", "## Constraints"],
    },
    "persona_1": {
        "role": "You are a senior software engineer and QA-aware coding assistant.",
        "sections": [
            "## Role", "## Task", "## Codebase Context",
            "## Acceptance Criteria", "## Edge Cases", "## Output Format",
        ],
    },
    "persona_2": {
        "role": "You are a delivery-focused technical project manager.",
        "sections": [
            "## Role", "## Report Type", "## Sprint / Project Context",
            "## Data References", "## Output Format", "## Constraints",
        ],
    },
    "persona_3": {
        "role": "You are a business analysis and product delivery assistant.",
        "sections": [
            "## Role", "## Task", "## Source Documents",
            "## Inference Policy", "## Output Format",
        ],
    },
    "persona_4": {
        "role": "You are a customer support communication specialist who drafts empathetic, policy-compliant responses.",
        "sections": [
            "## Role", "## Task", "## Customer Context",
            "## Policy / SLA Constraints", "## Output Format",
        ],
    },
}

# ---------------------------------------------------------------------------
# Per-section instructional placeholders — shown when the original prompt
# has no matching content for that section.  These are GUIDES for the user,
# NOT evaluation issues.
# ---------------------------------------------------------------------------
_PLACEHOLDERS: dict[str, str] = {
    "## Context":
        "[Specify: source material (document name / URL), audience, purpose, "
        "and any relevant background information]",
    "## Constraints":
        "[Specify: tone (formal / casual / technical), length limit, "
        "scope boundaries, and any content exclusions]",
    "## Codebase Context":
        "[Specify: programming language, framework and version, "
        "relevant modules or file paths, and any architectural constraints]",
    "## Acceptance Criteria":
        "[Specify: measurable outcomes — e.g., all unit tests pass, "
        "response time < 200 ms, output matches schema X]",
    "## Edge Cases":
        "[Specify: boundary values, null / empty inputs, "
        "duplicate records, timeout scenarios, and error states]",
    "## Output Format":
        "[Specify: format (code blocks / prose / JSON / table), "
        "length, and structure (e.g., step-by-step / bullet list / report)]",
    "## Sprint / Project Context":
        "[Specify: sprint name or ID, project name, stakeholders, "
        "relevant tickets or milestones]",
    "## Source Documents":
        "[Specify: document names, section references, or URLs "
        "the response should be grounded in]",
    "## Inference Policy":
        "[Specify: whether to infer beyond source material, "
        "citation format, and confidence thresholds]",
    "## Tone Directive":
        "[Specify: tone (empathetic / professional / formal), "
        "language level, and any brand voice guidelines]",
    "## Customer Context":
        "[Specify: customer name, issue summary, product affected, "
        "account tier, and prior interaction history]",
    "## Policy / SLA Constraints":
        "[Specify: applicable policies, SLA windows, escalation rules, "
        "and compliance requirements]",
    "## Next Action":
        "[Specify: what the agent should offer the customer next — "
        "e.g., escalate, schedule callback, send article]",
    "## Report Type":
        "[Specify: report type — e.g., sprint retrospective, "
        "velocity report, risk summary, stakeholder update]",
    "## Data References":
        "[Specify: data sources, dashboards, metric names, "
        "and date ranges the report should reference]",
}

# ---------------------------------------------------------------------------
# Known tech-stack vocabulary for codebase context extraction
# ---------------------------------------------------------------------------
_LANGUAGES = [
    "python", "java", "typescript", "javascript", "go", "c#", "csharp",
    "ruby", "php", "rust", "kotlin", "swift", "scala", "c++",
]
_FRAMEWORKS: dict[str, str] = {
    "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "tornado": "Tornado",
    "spring boot": "Spring Boot", "spring": "Spring", "hibernate": "Hibernate",
    "express.js": "Express.js", "express": "Express.js",
    "nestjs": "NestJS", "nest.js": "NestJS",
    "next.js": "Next.js", "nextjs": "Next.js",
    "react": "React", "angular": "Angular", "vue.js": "Vue.js", "vue": "Vue.js",
    "svelte": "Svelte",
    "laravel": "Laravel", "symfony": "Symfony",
    "rails": "Ruby on Rails", "ruby on rails": "Ruby on Rails",
    "gin": "Gin (Go)", "echo": "Echo (Go)", "fiber": "Fiber (Go)",
    "actix": "Actix (Rust)", "axum": "Axum (Rust)",
    "asp.net": "ASP.NET", ".net": ".NET",
    "sqlalchemy": "SQLAlchemy", "mongoose": "Mongoose", "prisma": "Prisma",
}
_VERSION_RE = _re.compile(
    r"(?i)\b(python|java|node(?:\.js)?|typescript|react|angular|vue|django|fastapi"
    r"|spring|express|laravel|rails|ruby|go|kotlin|php|rust)\s+([\d]+(?:\.[\d]+)*)\b"
)

# Shown when the user gives almost no detail — never substitute a fabricated job title.
_ROLE_PLACEHOLDER_THIN = (
    "[Not specified in original — add before using. Describe the role "
    "(title + domain) the model should adopt.]"
)


def is_prompt_too_thin_for_rewrite(text: str) -> bool:
    """True when auto-improve should not call the LLM rewrite (avoids invented personas).

    Heuristic: very short text, fewer than three words, or a single token like AAAA
    made of one repeated character.
    """
    t = text.strip()
    if not t:
        return True
    if len(t) < 12:
        return True
    words = t.split()
    if len(words) < 3:
        return True
    if len(words) == 1 and len(t) >= 2:
        letters = [c for c in t.lower() if c.isalpha()]
        if len(letters) >= 2 and len(set(letters)) == 1:
            return True
    return False


def _extract_task_statement(text: str) -> str:
    """Return the core imperative from the original prompt — first meaningful line."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return text.strip()[:200]
    first = lines[0]
    if len(first) < 20 and len(lines) > 1:
        first = lines[1]
    if len(first) > 200:
        m = _re.match(r"^(.{40,200}[.!?])\s", first)
        first = m.group(1) if m else first[:200]
    return first


def _extract_tech_stack(text: str) -> list[str]:
    """Extract language / framework / version facts stated in the original prompt."""
    found: list[str] = []
    text_lower = text.lower()
    seen_techs: set[str] = set()

    for m in _VERSION_RE.finditer(text):
        tech = m.group(1).lower()
        ver = m.group(2)
        label = m.group(1).title()
        entry = f"{label} {ver}"
        if entry not in found:
            found.append(entry)
            seen_techs.add(tech)

    for lang in _LANGUAGES:
        if lang in text_lower and lang not in seen_techs:
            display = "C#" if lang in ("c#", "csharp") else lang.title()
            found.append(display)
            break

    for key in sorted(_FRAMEWORKS, key=len, reverse=True):
        if key in text_lower:
            entry = _FRAMEWORKS[key]
            if entry not in found:
                found.append(entry)
            break

    return found[:4]


def _extract_edge_cases(text: str) -> list[str]:
    """Extract explicit edge cases / error scenarios from the original prompt."""
    edge_kws = (
        "missing", "empty", "null", "invalid", "duplicate", "not found",
        "error", "exception", "fail", "edge case", "boundary", "conflict",
        "unauthorized", "forbidden", "timeout", "overflow",
    )
    cases: list[str] = []
    sentences = _re.split(r"[.!?\n]|(?:,\s+(?:and|or|but)\s+)", text)
    for sent in sentences:
        s = sent.strip()
        if not s or len(s) < 5:
            continue
        if any(kw in s.lower() for kw in edge_kws):
            clean = _re.sub(r"^[-*•\d.)\s]+", "", s).strip()
            if clean and clean not in cases:
                cases.append(clean)
        if len(cases) >= 5:
            break
    return cases[:5]


def _extract_output_format(text: str) -> str:
    """Extract any explicit output format directive from the original prompt."""
    text_lower = text.lower()
    if "```" in text or "code block" in text_lower:
        return "Return the implementation in clearly labelled code blocks."
    if "json" in text_lower:
        return "Return output as a valid JSON object."
    if "markdown table" in text_lower or "table" in text_lower:
        return "Return output as a Markdown table."
    if "bullet" in text_lower or "list" in text_lower:
        return "Return output as a bullet-point list."
    if "step" in text_lower and ("by step" in text_lower or "steps" in text_lower):
        return "Return output as numbered steps."
    if "summary" in text_lower or "report" in text_lower:
        return "Return a structured written report with clear section headings."
    return ""


def _extract_constraints(text: str) -> list[str]:
    """Extract explicit constraints stated in the original prompt."""
    constraint_kws = (
        "only", "must not", "do not", "exclude", "no more than", "at most",
        "limit", "within", "avoid", "formal", "casual", "concise", "brief",
        "maximum", "minimum", "required", "mandatory",
    )
    found: list[str] = []
    sentences = _re.split(r"[.!?\n]", text)
    for sent in sentences:
        s = sent.strip()
        if not s or len(s) < 8:
            continue
        if any(kw in s.lower() for kw in constraint_kws):
            clean = _re.sub(r"^[-*•\d.)\s]+", "", s).strip()
            if clean and clean not in found:
                found.append(clean)
        if len(found) >= 3:
            break
    return found


def improve_prompt(
    original_prompt: str,
    persona_id: str,
    issues: list[str],  # noqa: ARG001
    *,
    thin_input: bool = False,
) -> str:
    """Build a structured ## section prompt without the LLM.

    Mirrors the output format of ``llm_rewrite_prompt`` so the UI shows
    consistent section headings regardless of which path executed.

    Rules:
    - Section content is ONLY extracted from the original prompt text.
    - Evaluation issues are NEVER inserted as section content.
    - Empty sections get a clear instructional placeholder telling the user
      exactly what to fill in — not a list of evaluation gaps.
    - When ``thin_input`` is True (garbage or ultra-short input), ## Role uses
      a placeholder instead of the persona’s generic example role line so we
      never imply the user asked for that persona wording.

    Args:
        original_prompt: The user's raw prompt text.
        persona_id:      One of persona_0 … persona_4.
        issues:          Identified gaps (kept for signature compatibility,
                         NOT inserted into section content).
        thin_input:      If True, skip generic ## Role line; put verbatim input in task.

    Returns:
        Structured improved prompt string starting with the first ## heading.
    """
    cfg = _PERSONA_SECTIONS.get(persona_id, _PERSONA_SECTIONS["persona_0"])

    # Pre-extract all facts from the original prompt once
    task_stmt   = (
        original_prompt.strip()
        if thin_input
        else _extract_task_statement(original_prompt)
    )
    tech_stack  = _extract_tech_stack(original_prompt)
    edge_cases  = _extract_edge_cases(original_prompt)
    output_fmt  = _extract_output_format(original_prompt)
    constraints = _extract_constraints(original_prompt)

    lines: list[str] = []

    for section in cfg["sections"]:
        lines.append(section)

        if section == "## Role":
            lines.append(_ROLE_PLACEHOLDER_THIN if thin_input else cfg["role"])

        elif section in ("## Task", "## Report Type"):
            lines.append(task_stmt)

        elif section == "## Codebase Context":
            if tech_stack:
                lines.append("\n".join(f"- {t}" for t in tech_stack))
            else:
                lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Acceptance Criteria":
            # Extract quality/test requirements directly from original text
            criteria_kws = ("unit test", "integration test", "test", "coverage",
                            "error handling", "validation", "schema", "response time",
                            "performance", "security", "auth")
            criteria = []
            for sent in _re.split(r"[.!?\n]", original_prompt):
                s = sent.strip()
                if s and any(kw in s.lower() for kw in criteria_kws):
                    clean = _re.sub(r"^[-*•\d.)\s]+", "", s).strip()
                    if clean and clean not in criteria:
                        criteria.append(clean)
            if criteria:
                lines.append("\n".join(f"- {c}" for c in criteria[:4]))
            else:
                lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Edge Cases":
            if edge_cases:
                lines.append("\n".join(f"- {e}" for e in edge_cases))
            else:
                lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Output Format":
            if output_fmt:
                lines.append(output_fmt)
            else:
                lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Constraints":
            if constraints:
                lines.append("\n".join(f"- {c}" for c in constraints))
            else:
                lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Context":
            # Extract purpose/audience hints that add meaningful context BEYOND the task.
            # Require len > 40 to avoid echoing the task sentence itself.
            context_kws = ("to help", "so that", "audience", "stakeholder",
                           "team", "customer", "for the", "background", "purpose")
            ctx_hints = []
            for sent in _re.split(r"[.!?\n]", original_prompt):
                s = sent.strip()
                if s and len(s) > 40 and any(kw in s.lower() for kw in context_kws):
                    clean = _re.sub(r"^[-*•\d.)\s]+", "", s).strip()
                    if clean and clean not in ctx_hints:
                        ctx_hints.append(clean)
            if ctx_hints:
                lines.append("\n".join(f"- {c}" for c in ctx_hints[:2]))
            else:
                lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Source Documents":
            lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Inference Policy":
            lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Sprint / Project Context":
            lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Data References":
            lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Tone Directive":
            lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Customer Context":
            lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Policy / SLA Constraints":
            lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        elif section == "## Next Action":
            lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        else:
            lines.append(_PLACEHOLDERS.get(section, "[Not specified in original — add before using]"))

        lines.append("")  # blank line between sections

    return "\n".join(lines).strip()
