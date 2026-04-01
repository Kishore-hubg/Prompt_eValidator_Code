"""
Persona-aware suggestion derivation.

Maps unresolved validation issues to focused, actionable suggestions
tailored to each persona's domain and output expectations.

Used by:
  - app/api/routes.py          → API response suggestions field
  - app/services/prompt_validation.py → rewrite call (so LLM targets the right gaps)
"""
from __future__ import annotations


def derive_issue_based_suggestions(
    persona_id: str,
    issues: list[str],
    fallback: list[str],
) -> list[str]:
    """Return focused suggestions mapped from current unresolved issues.

    If no issue keywords match, returns *fallback* (the persona's default
    suggestions from persona_criteria_source_truth.json).
    """
    issue_text = " ".join(issues).lower()
    mapped: list[str] = []

    def add_if(keywords: list[str], suggestion: str) -> None:
        if any(k in issue_text for k in keywords):
            mapped.append(suggestion)

    if persona_id == "persona_0":
        add_if(["action verb", "direct task instruction"], "Start with a clear action verb and direct task instruction.")
        add_if(["context", "source", "audience", "purpose"], "Add source, audience, and purpose context.")
        add_if(["output format", "structure"], "Declare the expected output format and structure.")
        add_if(["constraints", "scope", "open-ended", "generic"], "Add explicit constraints (scope, inclusions/exclusions, tone, length).")
        add_if(["grounded", "reference", "citation"], "Require grounded output with source references/citations.")

    elif persona_id == "persona_1":
        add_if(
            ["language", "framework", "version", "technical precision"],
            "[Developer] Specify language, framework, and version explicitly (e.g., Python 3.12, FastAPI 0.115+, Pydantic v2).",
        )
        add_if(
            ["codebase context", "interface", "class", "signature"],
            "[Developer] Provide codebase context: include the relevant interface, class, or function signature.",
        )
        add_if(
            ["security", "owasp", "cve", "injection", "auth", "authorization", "authentication", "vulnerability"],
            "[Developer] Add security constraints: reference OWASP Top 10, required auth mechanism, and any CVE/compliance standard.",
        )
        add_if(
            ["user story", "acceptance criteria", "ac "],
            "[QA] Add user story / acceptance-criteria reference (for example: US-123, AC2).",
        )
        add_if(
            ["edge case", "null", "timeout", "error state", "boundary"],
            "[QA] Request explicit edge coverage: boundary values, null inputs, timeout, and error states.",
        )
        add_if(
            ["test format", "tc-id", "preconditions", "expected result"],
            "[QA] Specify test format: TC-ID | Preconditions | Test Steps | Expected Result | Priority.",
        )
        add_if(["scope", "open-ended", "generic output"], "[Both] Define in-scope and out-of-scope modules/scenarios.")
        add_if(["output format", "structure"], "[Both] Declare exact output structure (code blocks/files/tables).")
        add_if(
            ["action verb", "direct task instruction"],
            "[Both] Start with a strong action verb and direct instruction (Implement/Generate/Refactor/Validate).",
        )

    elif persona_id == "persona_2":
        add_if(["output format", "report type", "structure"], "Declare report type first (status report, risk log, sprint summary, estimate comparison, escalation note).")
        add_if(["context", "sprint", "team", "dates", "audience"], "Embed sprint context: sprint number, team, reporting period, dates, and audience.")
        add_if(["priority", "rank", "impact", "top 3"], "Specify prioritization criteria (rank/impact/top items) for decision-ready output.")
        add_if(["traceability", "data reference", "history", "metric"], "Add traceability: include velocity/history/metric references used in analysis.")
        add_if(["engagement model", "business relevance"], "Include engagement model context (fixed bid, T&M, managed services, or staff augmentation) when relevant.")

    elif persona_id == "persona_3":
        add_if(["source", "grounding", "document", "section", "transcript"], "[BA] Reference source material explicitly (document and section).")
        add_if(["citation", "reference", "traceability"], "[BA] Require source citation/traceability for each extracted or analyzed item.")
        add_if(["inference", "unstated"], "[BA] Set inference policy (explicit-only vs allowed inference).")
        add_if(["audience", "business relevance"], "[PO] Specify target audience (delivery team, stakeholder, or executive).")
        add_if(["acceptance criteria"], "[PO] Request testable acceptance criteria for each user story/output item.")
        add_if(["priority", "moscow", "wsjf"], "[PO] Add prioritization framework (MoSCoW, WSJF, or value vs effort).")
        add_if(["output format", "structure"], "[Both] Define output structure (requirements matrix, user story table, BRD section, or roadmap view).")

    elif persona_id == "persona_4":
        add_if(["tone", "empathy"], "Add tone directive (empathetic, firm, apologetic, informative, or neutral).")
        add_if(["compliance", "policy", "sla", "privacy"], "Reference applicable policy/compliance constraints (SLA, privacy, or approved policy).")
        add_if(["speed", "concise", "quick", "short"], "Set brevity target (concise/short response with clear next action).")
        add_if(["context", "customer", "issue"], "Provide customer context: issue type, urgency, and desired next step/escalation path.")
        add_if(["output format", "channel", "structure"], "Specify response channel/output type (email, chat reply, internal note, escalation note).")

    if mapped:
        return mapped

    # No issues at all → prompt is solid, no suggestions needed
    if not issues:
        return []

    # Issues exist but no keyword matched → return at most 2 general defaults
    # so the user has some guidance without being overwhelmed by irrelevant items
    return fallback[:2]
