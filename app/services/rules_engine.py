from __future__ import annotations
import re
from typing import Dict, List, Tuple
from app.services.persona_loader import get_persona
from app.services.prompt_guidelines_loader import load_prompt_guidelines

ACTION_VERBS = [
    "summarize", "draft", "extract", "analyze", "explain", "create",
    "generate", "rewrite", "classify", "translate", "review", "compare",
    "identify", "validate", "refactor", "debug", "write", "prepare"
]
OUTPUT_HINTS = [
    "bullet", "bullets", "table", "paragraph", "paragraphs", "json", "yaml", "xml",
    "numbered", "list", "checklist", "template", "matrix", "steps", "email"
]
TECH_HINTS = [
    "python", "java", "javascript", "typescript", "node", "react", "fastapi",
    "spring", "cypress", "playwright", "selenium", "express", "sql", "api"
]
PM_HINTS = ["sprint", "velocity", "status report", "risk log", "estimate", "burndown", "roadmap"]
BA_HINTS = ["brd", "user story", "acceptance criteria", "requirements", "roadmap", "sop", "document", "section"]
SUPPORT_HINTS = ["customer", "ticket", "reply", "escalation", "kb", "knowledge base", "issue"]

def _contains_any(text: str, terms: List[str]) -> bool:
    t = text.lower()
    return any(term in t for term in terms)


def _evaluate_keyword_checks(prompt_text: str, checks: Dict[str, List[str]]) -> Dict[str, bool]:
    lowered = prompt_text.lower()
    results: Dict[str, bool] = {}
    for dim, terms in checks.items():
        results[dim] = _contains_any(lowered, terms)
    return results


def evaluate_guidelines(prompt_text: str) -> dict:
    cfg = load_prompt_guidelines()
    if not cfg.get("strict_mode", True):
        return {
            "strict_mode": False,
            "penalty_applied": 0,
            "checks": [],
            "issues": [],
            "sources": cfg.get("sources", []),
        }

    lowered = prompt_text.lower()
    words = _word_count(prompt_text)
    misses: List[str] = []
    checks: List[dict] = []

    for check in cfg.get("global_checks", []):
        check_id = check.get("id", "unnamed_check")
        description = check.get("description", "")
        min_wc = int(check.get("min_word_count", 0))
        if words < min_wc:
            checks.append(
                {
                    "id": check_id,
                    "description": description,
                    "passed": True,
                    "status": "skipped",
                    "message": f"Skipped because prompt has fewer than {min_wc} words.",
                }
            )
            continue

        applies_when_any = check.get("applies_when_any", [])
        if applies_when_any and not any(term in lowered for term in applies_when_any):
            checks.append(
                {
                    "id": check_id,
                    "description": description,
                    "passed": True,
                    "status": "skipped",
                    "message": "Skipped because applicability conditions are not met.",
                }
            )
            continue

        keywords = check.get("keywords", [])
        passed = any(term in lowered for term in keywords)
        checks.append(
            {
                "id": check_id,
                "description": description,
                "passed": passed,
                "status": "applied",
                "message": "Pass" if passed else check.get("issue_if_missing", "Guideline check failed."),
            }
        )
        if not passed:
            misses.append(check.get("issue_if_missing", "Guideline check failed."))

    penalty = min(
        len(misses) * int(cfg.get("strict_penalty_per_miss", 3)),
        int(cfg.get("strict_penalty_cap", 15)),
    )
    return {
        "strict_mode": True,
        "penalty_applied": penalty,
        "checks": checks,
        "issues": misses,
        "sources": cfg.get("sources", []),
    }

def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))

def _starts_with_action_verb(text: str) -> bool:
    m = re.match(r"^\s*([a-zA-Z]+)", text)
    return bool(m and m.group(1).lower() in ACTION_VERBS)

def _has_context(text: str) -> bool:
    lowered = text.lower()
    clues = ["based on", "using", "for", "audience", "context", "document", "source", "given", "from", "section", "team", "customer"]
    return sum(1 for c in clues if c in lowered) >= 2 or _word_count(text) >= 18

def _has_output_format(text: str) -> bool:
    return _contains_any(text, OUTPUT_HINTS)

def _looks_open_ended(text: str) -> bool:
    short = _word_count(text) < 8
    generic = bool(re.search(r"\b(tell me about|help me with|write about|explain)\b", text.lower()))
    return short or generic

def _has_constraints(text: str) -> bool:
    lowered = text.lower()
    patterns = ["tone", "word", "limit", "only", "must", "should", "do not", "dont ", "technical", "non-technical", "formal", "casual"]
    return _contains_any(lowered, patterns)

def _has_audience(text: str) -> bool:
    return _contains_any(text, ["audience", "client", "executive", "leadership", "customer", "team", "technical", "non-technical", "stakeholder"])

def _has_language_framework(text: str) -> bool:
    return _contains_any(text, TECH_HINTS)

def _has_version_hint(text: str) -> bool:
    # Accept common explicit version mentions like "3.12", "v2", "2022.1"
    lowered = text.lower()
    if re.search(r"\bv\d+(?:\.\d+){0,2}\b", lowered):
        return True
    if re.search(r"\b\d+(?:\.\d+){1,2}\b", lowered):
        return True
    return False

def _has_edge_case_request(text: str) -> bool:
    return _contains_any(text, ["edge case", "boundary", "null", "timeout", "error state", "concurrency", "invalid input", "empty input"])

def _has_pm_context(text: str) -> bool:
    return _contains_any(text, PM_HINTS) and _has_audience(text)

def _has_ba_grounding(text: str) -> bool:
    return _contains_any(text, ["based on", "section", "document", "source", "transcript", "requirements", "brd"])

def _has_support_context(text: str) -> bool:
    return _contains_any(text, SUPPORT_HINTS)

def evaluate_prompt(prompt_text: str, persona_id: str) -> Tuple[float, List[dict], List[str], List[str]]:
    persona = get_persona(persona_id)
    weights: Dict[str, float] = persona["weights"]
    lowered = prompt_text.lower()
    keyword_checks = _evaluate_keyword_checks(prompt_text, persona.get("keyword_checks", {}))

    dimension_scores: List[dict] = []
    strengths: List[str] = []
    issues: List[str] = []

    def add_dimension(name: str, passed: bool, note: str | None = None):
        weight = float(weights.get(name, 0))
        score = weight if passed else 0.0
        dimension_scores.append({
            "name": name,
            "score": score,
            "weight": weight,
            "passed": passed,
            "notes": note
        })

    action_verb = _starts_with_action_verb(prompt_text)
    context = _has_context(prompt_text)
    output_format = _has_output_format(prompt_text)
    constraints = _has_constraints(prompt_text)
    open_ended = _looks_open_ended(prompt_text)

    for dim, passed, note in [
        ("clarity", action_verb or not open_ended, "Starts clearly and signals intent." if action_verb else "Task is broad or underspecified."),
        ("context", context, "Includes useful task context." if context else "Missing task, source, or audience context."),
        ("specificity", _word_count(prompt_text) >= 12, "Prompt has enough detail." if _word_count(prompt_text) >= 12 else "Prompt is too short or generic."),
        ("output_format", output_format, "Output format is defined." if output_format else "No output format defined."),
        ("ambiguity_reduction", not open_ended, "Prompt reduces ambiguity." if not open_ended else "Prompt is open-ended."),
        ("constraints", constraints, "Constraints are present." if constraints else "Constraints are missing."),
        ("actionability", _contains_any(lowered, ["next step", "recommend", "suggest", "action", "owner", "fix"]), "Action-oriented request." if _contains_any(lowered, ["next step", "recommend", "suggest", "action", "owner", "fix"]) else "Could be more action-oriented."),
        ("accuracy", _contains_any(lowered, ["based on", "only", "source", "cite", "grounded"]), "Grounding cues included." if _contains_any(lowered, ["based on", "only", "source", "cite", "grounded"]) else "No explicit grounding instruction.")
    ]:
        if dim in weights:
            add_dimension(dim, passed, note)

    if persona_id == "persona_1":
        technical_precision = (
            keyword_checks.get("technical_precision", False)
            or _has_language_framework(prompt_text)
            or _has_version_hint(prompt_text)
        )
        edge_cases = keyword_checks.get("edge_cases", _has_edge_case_request(prompt_text))
        testability = keyword_checks.get("testability", _contains_any(lowered, ["test", "expected", "assert", "acceptance", "verify"]))
        role_alignment = keyword_checks.get("role_alignment", _contains_any(lowered, ["bug", "feature", "refactor", "unit test", "automation", "qa", "sdet"]))
        reproducibility = keyword_checks.get("reproducibility", output_format)

        add_dimension("technical_precision", technical_precision, "Language/framework specified." if technical_precision else "Missing language/framework.")
        add_dimension("edge_cases", edge_cases, "Edge cases requested." if edge_cases else "No edge-case request found.")
        add_dimension("testability", testability, "Verifiable output requested." if testability else "No testability cue found.")
        add_dimension("reproducibility", reproducibility, "Structured output improves reproducibility." if reproducibility else "Missing repeatable structure.")
        add_dimension("role_alignment", role_alignment, "Task type declared." if role_alignment else "Task type not declared.")

        if not technical_precision:
            issues.append("Specify the programming language, framework, and version.")
        if not edge_cases:
            issues.append("Request explicit edge cases such as boundaries, null inputs, errors, and timeouts.")

    elif persona_id == "persona_2":
        reproducibility = keyword_checks.get("reproducibility", _contains_any(lowered, ["same structure", "template", "weekly", "standard format"]))
        prioritization = keyword_checks.get("prioritization", _contains_any(lowered, ["priority", "rank", "risk", "impact", "top 3"]))
        traceability = keyword_checks.get("traceability", _contains_any(lowered, ["velocity", "story", "history", "data", "metric", "reference"]))
        business_relevance = keyword_checks.get("business_relevance", _contains_any(lowered, ["fixed bid", "t&m", "managed services", "staff augmentation", "client"]))

        add_dimension("reproducibility", reproducibility, "Template/reuse cue present." if reproducibility else "No reproducibility cue found.")
        add_dimension("prioritization", prioritization, "Prioritization criteria present." if prioritization else "No prioritization criteria present.")
        add_dimension("traceability", traceability, "Data grounding present." if traceability else "No traceability / data reference present.")
        add_dimension("business_relevance", business_relevance, "Engagement relevance present." if business_relevance else "Engagement model not referenced.")
        if not _has_pm_context(prompt_text):
            issues.append("Embed sprint context, team, dates, audience, and reporting goal.")

    elif persona_id == "persona_3":
        business_relevance = keyword_checks.get("business_relevance", _contains_any(lowered, ["business", "stakeholder", "user", "product", "roadmap", "requirement"]))
        grounding = keyword_checks.get("grounding", _has_ba_grounding(prompt_text))
        traceability = keyword_checks.get("traceability", _contains_any(lowered, ["section", "story id", "source", "citation", "trace"]))
        prioritization = keyword_checks.get("prioritization", _contains_any(lowered, ["moscow", "wsjf", "priority", "rank"]))

        add_dimension("business_relevance", business_relevance, "Business framing present." if business_relevance else "Business relevance is weak.")
        add_dimension("grounding", grounding, "Source grounding present." if grounding else "Source grounding missing.")
        add_dimension("traceability", traceability, "Traceability cues present." if traceability else "Traceability cues missing.")
        add_dimension("prioritization", prioritization, "Prioritization method included." if prioritization else "No prioritization method included.")
        if not grounding:
            issues.append("Reference the source document, section, transcript, or business context explicitly.")

    elif persona_id == "persona_4":
        tone_empathy = keyword_checks.get("tone_empathy", _contains_any(lowered, ["empathetic", "calm", "professional", "friendly", "reassuring"]))
        compliance = keyword_checks.get("compliance", _contains_any(lowered, ["policy", "compliant", "approved", "privacy", "sla"]))
        speed = keyword_checks.get("speed", _contains_any(lowered, ["short", "concise", "quick", "fast"]))
        add_dimension("tone_empathy", tone_empathy, "Tone is specified." if tone_empathy else "No tone guidance specified.")
        add_dimension("compliance", compliance, "Compliance cue present." if compliance else "No compliance cue present.")
        add_dimension("speed", speed, "Speed/conciseness cue present." if speed else "No speed cue present.")
        if not _has_support_context(prompt_text):
            issues.append("Add customer issue context and the desired next step or escalation path.")

    # Drop dimensions that carry zero weight for this persona.
    # These arise when keyword_checks contains a key (e.g. "traceability",
    # "business_relevance") that is NOT in the persona's weights dict.
    # weight=0 dimensions don't affect the score but are confusing in the UI
    # — they appear as "0 / 0  Gap" even when the overall score is 100.
    dimension_scores = [d for d in dimension_scores if d["weight"] > 0]

    total_weight = sum(item["weight"] for item in dimension_scores) or 1.0
    total_score = sum(item["score"] for item in dimension_scores)
    final_score = round((total_score / total_weight) * 100, 2)
    guideline_eval = evaluate_guidelines(prompt_text)
    guideline_penalty = int(guideline_eval.get("penalty_applied", 0))
    guideline_issues = list(guideline_eval.get("issues", []))
    final_score = round(max(0.0, final_score - guideline_penalty), 2)

    if final_score >= 85:
        strengths.append("The prompt is well-structured and likely to produce high-quality output.")
    if action_verb:
        strengths.append("It starts with a clear action or intent.")
    if context:
        strengths.append("It includes useful context.")
    if output_format:
        strengths.append("It defines the output structure.")
    if constraints:
        strengths.append("It includes constraints that reduce ambiguity.")
    if not strengths:
        strengths.append("The prompt has a valid core request to build on.")
    if guideline_penalty == 0:
        strengths.append("Prompt aligns with core prompt-guideline controls.")

    if not action_verb:
        issues.append("Start with a stronger action verb so the task is unmistakable.")
    if not context:
        issues.append("Add more context about the source, purpose, or audience.")
    if not output_format:
        issues.append("Declare the expected output format.")
    if not constraints:
        issues.append("Add constraints such as length, tone, scope, or exclusions.")
    if open_ended:
        issues.append("Narrow the scope to avoid generic output.")
    issues.extend(guideline_issues)

    seen = set()
    issues = [x for x in issues if not (x in seen or seen.add(x))]

    return final_score, dimension_scores, strengths, issues, guideline_eval
