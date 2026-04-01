"""
tests/test_rewrite_edge_cases.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Unit tests covering all 15 rewrite edge cases (EC-01 through EC-15).

Strategy
--------
- Mock `app.services.llm_groq._chat_completion` so no real LLM call is made.
- Simulate CORRECT LLM responses that follow the 3-step system prompt.
- Assert that `llm_rewrite_prompt()` produces the right output structure.
- Also test that the SYSTEM PROMPT itself contains all required rules,
  so a regression in the prompt text is caught immediately.

EC-01  Language substitution kept       Java stays Java in improved_prompt
EC-02  Version hallucination blocked    [Not specified] used when version absent
EC-03  Ticket/ID fabrication blocked    unresolved_gaps flagged when no ticket
EC-04  Scope fabrication blocked        [Not specified] used when scope absent
EC-05  "latest" not resolved            Ambiguity flagged in unresolved_gaps
EC-06  Framework/language conflict      Contradiction flagged (Spring Boot + Python)
EC-07  Conflicting output formats       Contradiction flagged in unresolved_gaps
EC-08  Conflicting scope                Contradiction flagged in unresolved_gaps
EC-09  Terse prompt — Missing flagged   unresolved_gaps has Missing: entries
EC-10  Implicit requirements blocked    Role stays [Not specified] when absent
EC-11  Role hallucination blocked       No invented role title
EC-12  Non-stated error codes blocked   Only stated codes appear
EC-13  Response schema invention        No invented field names
EC-14  High score → structure rewrite   [Not specified] used, not invented content
EC-15  Original echo stripped           _strip_original_echo removes echo heading

SYSTEM-PROMPT tests (SP-01 to SP-15) verify rule presence in the prompt string.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.services.llm_groq import LlmRewriteResult, _strip_original_echo, llm_rewrite_prompt

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

PERSONA_1 = {
    "id": "persona_1",
    "name": "Developer & QA",
    "weights": {"technical_precision": 18},
    "suggestions": ["Be specific about language and framework"],
    "validator_checks": [],
    "keyword_checks": {},
    "penalty_triggers": [],
}

PERSONA_0 = {
    "id": "persona_0",
    "name": "All Employees",
    "weights": {"clarity": 15},
    "suggestions": ["Keep it clear"],
    "validator_checks": [],
    "keyword_checks": {},
    "penalty_triggers": [],
}

GUIDELINES: dict = {
    "global_checks": [
        {"id": "clear_direct_action", "description": "Prompt has a clear action", "keywords": [], "issue_if_missing": "No action"}
    ],
    "claude_curated_priorities": ["clarity", "context", "output_format"],
    "strict_penalty_per_miss": 3,
    "strict_penalty_cap": 15,
    "strict_mode": True,
}


def _make_llm_response(
    improved: str,
    applied: list[str] | None = None,
    gaps: list[str] | None = None,
) -> str:
    """Build a JSON string the mocked _chat_completion would return."""
    return json.dumps({
        "improved_prompt": improved,
        "applied_guidelines": applied or ["clarity", "output_format"],
        "unresolved_gaps": gaps or [],
    })


def _call_rewrite(prompt_text: str, persona=None, issues=None, mock_response: str = "") -> LlmRewriteResult:
    """Call llm_rewrite_prompt with _chat_completion fully mocked."""
    # Side effect accepts **kwargs so the new `model` parameter doesn't break the mock.
    def _fake(*args, **kwargs):
        return mock_response

    with patch("app.services.llm_groq._chat_completion", side_effect=_fake):
        return llm_rewrite_prompt(
            prompt_text,
            persona=persona or PERSONA_1,
            guidelines=GUIDELINES,
            issues=issues or [],
        )


# ===========================================================================
# SYSTEM-PROMPT content tests (SP-*) — verify rules exist in the prompt text
# ===========================================================================

def _capture_system_prompt(prompt_text: str, persona=None, issues=None) -> str:
    """Capture the system message string passed to _chat_completion."""
    captured = {}

    def fake_chat(messages, *, json_mode, model=None):
        captured["system"] = messages[0]["content"]
        captured["user"] = messages[1]["content"]
        return _make_llm_response("## Role\ntest\n## Task\ntest")

    with patch("app.services.llm_groq._chat_completion", side_effect=fake_chat):
        llm_rewrite_prompt(
            prompt_text,
            persona=persona or PERSONA_1,
            guidelines=GUIDELINES,
            issues=issues or [],
        )
    return captured.get("system", "")


def test_sp_01_system_prompt_has_step1_fact_extraction():
    sp = _capture_system_prompt("create an api")
    assert "STEP 1" in sp
    assert "IMMUTABLE FACTS" in sp


def test_sp_02_system_prompt_has_step2_contradiction_detection():
    sp = _capture_system_prompt("create an api")
    assert "STEP 2" in sp
    assert "DETECT" in sp and "CONTRADICTION" in sp


def test_sp_03_system_prompt_has_step3_write_section():
    sp = _capture_system_prompt("create an api")
    assert "STEP 3" in sp


def test_sp_04_system_prompt_has_framework_language_table():
    sp = _capture_system_prompt("create an api")
    assert "FastAPI → Python" in sp
    assert "Spring Boot → Java" in sp
    assert "Express.js → Node.js" in sp
    assert "Laravel → PHP" in sp
    assert "Ruby on Rails → Ruby" in sp


def test_sp_05_system_prompt_has_h1_language_rule():
    sp = _capture_system_prompt("create an api")
    assert "H1" in sp
    assert "NEVER change" in sp or "never change" in sp.lower()


def test_sp_06_system_prompt_has_h2_version_rule():
    sp = _capture_system_prompt("create an api")
    assert "H2" in sp
    assert "version not specified" in sp


def test_sp_07_system_prompt_has_h3_ticket_rule():
    sp = _capture_system_prompt("create an api")
    assert "H3" in sp
    assert "ticket IDs" in sp or "NEVER invent ticket" in sp


def test_sp_08_system_prompt_has_h4_scope_rule():
    sp = _capture_system_prompt("create an api")
    assert "H4" in sp
    assert "scope items" in sp or "NEVER invent scope" in sp


def test_sp_09_system_prompt_has_c1_framework_mismatch():
    sp = _capture_system_prompt("create an api")
    assert "C1" in sp
    assert "FRAMEWORK" in sp and "LANGUAGE MISMATCH" in sp


def test_sp_10_system_prompt_has_c4_latest_version():
    sp = _capture_system_prompt("create an api")
    assert "C4" in sp
    assert "LATEST VERSION" in sp or "latest version" in sp.lower()


def test_sp_11_system_prompt_has_not_specified_placeholder():
    sp = _capture_system_prompt("create an api")
    assert "Not specified in original" in sp


def test_sp_12_system_prompt_has_h6_implicit_requirements_rule():
    sp = _capture_system_prompt("create an api")
    assert "H6" in sp
    assert "implicit" in sp.lower()


def test_sp_13_system_prompt_persona1_sections_correct():
    sp = _capture_system_prompt("create an api", persona=PERSONA_1)
    assert "## Role" in sp
    assert "## Task" in sp
    assert "## Codebase Context" in sp
    assert "## Acceptance Criteria" in sp
    assert "## Edge Cases" in sp
    assert "## Output Format" in sp


def test_sp_14_system_prompt_user_block_has_anchor():
    """User message must remind the LLM to carry facts unchanged."""
    captured = {}

    def fake_chat(messages, *, json_mode, model=None):
        captured["user"] = messages[1]["content"]
        return _make_llm_response("## Role\ntest")

    with patch("app.services.llm_groq._chat_completion", side_effect=fake_chat):
        llm_rewrite_prompt("build api", persona=PERSONA_1, guidelines=GUIDELINES, issues=[])

    assert "ANCHOR" in captured["user"]


def test_sp_15_system_prompt_has_h7_role_hallucination_rule():
    sp = _capture_system_prompt("create an api")
    assert "H7" in sp
    assert "role" in sp.lower()


# ===========================================================================
# EC-01 — Language substitution: Java must be preserved
# ===========================================================================

def test_ec_01_java_preserved_in_improved_prompt():
    """LLM returns Java; improved_prompt must keep Java unchanged."""
    improved = (
        "## Role\nBackend developer.\n"
        "## Task\nGenerate a FastAPI endpoint in Java for POST /users "
        "using Pydantic validation and SQLAlchemy.\n"
        "## Codebase Context\nLanguage: Java. Framework: FastAPI.\n"
        "## Acceptance Criteria\nHandle missing fields, duplicate email, empty payload.\n"
        "## Edge Cases\nMissing fields | Duplicate email | Empty payload.\n"
        "## Output Format\nReturn as separate code blocks: model, route, tests."
    )
    gaps = [
        "Contradiction: FastAPI is a Python-only framework but the prompt specifies Java. "
        "Clarify whether the intended language is Python (use FastAPI) or Java "
        "(use Spring Boot / Micronaut / Quarkus)."
    ]
    result = _call_rewrite(
        "Generate a FastAPI endpoint in Java for POST /users",
        issues=[],
        mock_response=_make_llm_response(improved, gaps=gaps),
    )
    assert "Java" in result.improved_prompt
    assert any("Contradiction" in g and "Java" in g for g in result.unresolved_gaps)


# ===========================================================================
# EC-02 — Version hallucination: [Not specified] used when version is absent
# ===========================================================================

def test_ec_02_no_version_in_original_gets_not_specified():
    """When original has no version number, improved prompt must not invent one."""
    improved = (
        "## Role\n[Not specified in original — add before using]\n"
        "## Task\nCreate a FastAPI endpoint for user registration.\n"
        "## Codebase Context\nLanguage: Python (version not specified). Framework: FastAPI.\n"
        "## Acceptance Criteria\nPass all unit tests.\n"
        "## Edge Cases\nMissing fields | Duplicate email.\n"
        "## Output Format\nReturn as code blocks."
    )
    result = _call_rewrite(
        "Create a FastAPI endpoint for user registration",
        issues=[],
        mock_response=_make_llm_response(improved),
    )
    assert "version not specified" in result.improved_prompt.lower()
    # Fabricated version numbers must NOT appear
    assert "3.9" not in result.improved_prompt
    assert "0.92" not in result.improved_prompt


# ===========================================================================
# EC-03 — Ticket/ID fabrication: no ticket in original → none in output
# ===========================================================================

def test_ec_03_no_ticket_in_original_not_in_output():
    """Ticket IDs never present in original must not appear in improved_prompt."""
    improved = (
        "## Role\n[Not specified in original — add before using]\n"
        "## Task\nCreate POST /users endpoint.\n"
        "## Codebase Context\n[Not specified in original — add before using]\n"
        "## Acceptance Criteria\nHandle missing fields and duplicate email.\n"
        "## Edge Cases\nMissing fields | Duplicate email.\n"
        "## Output Format\nReturn code blocks."
    )
    result = _call_rewrite(
        "Create POST /users endpoint with error handling",
        issues=[],
        mock_response=_make_llm_response(improved),
    )
    assert "US-" not in result.improved_prompt
    assert "AC-" not in result.improved_prompt
    assert "AC2" not in result.improved_prompt


# ===========================================================================
# EC-04 — Scope fabrication: no scope in original → [Not specified]
# ===========================================================================

def test_ec_04_no_scope_in_original_not_fabricated():
    """Scope items not in original must not appear in Codebase Context."""
    improved = (
        "## Role\n[Not specified in original — add before using]\n"
        "## Task\nBuild POST /users endpoint.\n"
        "## Codebase Context\n[Not specified in original — add before using]\n"
        "## Acceptance Criteria\nHandle edge cases.\n"
        "## Edge Cases\nMissing fields | Empty payload.\n"
        "## Output Format\nCode blocks."
    )
    result = _call_rewrite(
        "Build POST /users endpoint",
        issues=[],
        mock_response=_make_llm_response(improved),
    )
    assert "payment" not in result.improved_prompt.lower()
    assert "authentication" not in result.improved_prompt.lower()


# ===========================================================================
# EC-05 — "latest version" must not be resolved to a specific number
# ===========================================================================

def test_ec_05_latest_version_preserved_not_pinned():
    """'latest version' in original must stay as 'latest stable', not a specific number."""
    improved = (
        "## Role\nBackend developer.\n"
        "## Task\nCreate REST API using Django (version not pinned — use latest stable).\n"
        "## Codebase Context\nFramework: Django (version not pinned — use latest stable).\n"
        "## Acceptance Criteria\nPass all tests.\n"
        "## Edge Cases\nNetwork timeout.\n"
        "## Output Format\nCode blocks."
    )
    gaps = ["Ambiguity: version not pinned for Django — pin a specific version for reproducible results."]
    result = _call_rewrite(
        "Create REST API using latest version of Django",
        issues=[],
        mock_response=_make_llm_response(improved, gaps=gaps),
    )
    assert any("Ambiguity" in g and "version" in g for g in result.unresolved_gaps)
    assert "3.2" not in result.improved_prompt
    assert "4.0" not in result.improved_prompt


# ===========================================================================
# EC-06 — Framework/language conflict: Spring Boot + Python → contradiction
# ===========================================================================

def test_ec_06_spring_boot_python_contradiction_flagged():
    improved = (
        "## Role\nBackend developer.\n"
        "## Task\nCreate Spring Boot application in Python for user management.\n"
        "## Codebase Context\nLanguage: Python. Framework: Spring Boot.\n"
        "## Acceptance Criteria\nPass all tests.\n"
        "## Edge Cases\nMissing fields.\n"
        "## Output Format\nCode blocks."
    )
    gaps = [
        "Contradiction: Spring Boot is a Java framework but the prompt specifies Python. "
        "Clarify whether the intended language is Java (use Spring Boot) or Python (use Django/FastAPI)."
    ]
    result = _call_rewrite(
        "Create Spring Boot application in Python",
        issues=[],
        mock_response=_make_llm_response(improved, gaps=gaps),
    )
    assert any("Contradiction" in g and "Spring Boot" in g for g in result.unresolved_gaps)
    assert "Spring Boot" in result.improved_prompt  # value kept, not silently fixed


# ===========================================================================
# EC-07 — Conflicting output formats
# ===========================================================================

def test_ec_07_conflicting_output_formats_flagged():
    improved = (
        "## Role\nAnalyst.\n"
        "## Task\nGenerate report.\n"
        "## Codebase Context\n[Not specified in original — add before using]\n"
        "## Acceptance Criteria\nReport must be complete.\n"
        "## Edge Cases\nNo data available.\n"
        "## Output Format\nReturn JSON AND a Markdown table."
    )
    gaps = ["Contradiction: conflicting output formats requested — clarify which is primary."]
    result = _call_rewrite(
        "Return results as JSON AND a Markdown table",
        issues=[],
        mock_response=_make_llm_response(improved, gaps=gaps),
    )
    assert any("Contradiction" in g and "output format" in g.lower() for g in result.unresolved_gaps)


# ===========================================================================
# EC-08 — Conflicting scope
# ===========================================================================

def test_ec_08_conflicting_scope_flagged():
    improved = (
        "## Role\nBackend developer.\n"
        "## Task\nCreate user API. Include authentication. Authentication is out-of-scope.\n"
        "## Codebase Context\nIn-scope: authentication. Out-of-scope: authentication.\n"
        "## Acceptance Criteria\nPass tests.\n"
        "## Edge Cases\nUnauthorised access.\n"
        "## Output Format\nCode blocks."
    )
    gaps = ["Contradiction: authentication listed as both in-scope and out-of-scope — clarify."]
    result = _call_rewrite(
        "Create user API. Include authentication. Authentication is out-of-scope.",
        issues=[],
        mock_response=_make_llm_response(improved, gaps=gaps),
    )
    assert any("Contradiction" in g and "scope" in g.lower() for g in result.unresolved_gaps)


# ===========================================================================
# EC-09 — Terse prompt: missing sections flagged, not fabricated
# ===========================================================================

def test_ec_09_terse_prompt_uses_not_specified_placeholder():
    improved = (
        "## Role\n[Not specified in original — add before using]\n"
        "## Task\nCreate API.\n"
        "## Codebase Context\n[Not specified in original — add before using]\n"
        "## Acceptance Criteria\n[Not specified in original — add before using]\n"
        "## Edge Cases\n[Not specified in original — add before using]\n"
        "## Output Format\n[Not specified in original — add before using]"
    )
    gaps = [
        "Missing: Role not specified in original.",
        "Missing: Codebase Context not specified in original.",
        "Missing: Acceptance Criteria not specified in original.",
    ]
    result = _call_rewrite(
        "create api",
        issues=["No role specified", "No output format specified"],
        mock_response=_make_llm_response(improved, gaps=gaps),
    )
    assert "Not specified in original" in result.improved_prompt
    assert len([g for g in result.unresolved_gaps if "Missing" in g]) >= 1


# ===========================================================================
# EC-10 — Implicit requirements must not be injected
# ===========================================================================

def test_ec_10_no_implicit_auth_added_to_user_endpoint():
    """'POST /users' does not imply auth should be added."""
    improved = (
        "## Role\nBackend developer.\n"
        "## Task\nCreate POST /users endpoint with error handling.\n"
        "## Codebase Context\n[Not specified in original — add before using]\n"
        "## Acceptance Criteria\nHandle missing fields and duplicate email.\n"
        "## Edge Cases\nMissing fields | Duplicate email | Empty payload.\n"
        "## Output Format\nCode blocks for model, route, tests."
    )
    result = _call_rewrite(
        "Create POST /users endpoint with error handling",
        issues=[],
        mock_response=_make_llm_response(improved),
    )
    # auth and RBAC were never in the original — must not appear
    assert "rbac" not in result.improved_prompt.lower()
    assert "jwt" not in result.improved_prompt.lower()
    assert "bearer" not in result.improved_prompt.lower()


# ===========================================================================
# EC-11 — Role hallucination: no role in original → [Not specified]
# ===========================================================================

def test_ec_11_no_role_in_original_gets_placeholder():
    improved = (
        "## Role\n[Not specified in original — add before using]\n"
        "## Task\nGenerate SQL query.\n"
        "## Codebase Context\n[Not specified in original — add before using]\n"
        "## Acceptance Criteria\nQuery must return correct results.\n"
        "## Edge Cases\nEmpty table.\n"
        "## Output Format\nSQL code block."
    )
    result = _call_rewrite(
        "Generate SQL query to fetch all orders",
        issues=[],
        mock_response=_make_llm_response(improved),
    )
    assert "Not specified in original" in result.improved_prompt
    # Should NOT have invented a specific job title
    assert "senior data engineer" not in result.improved_prompt.lower()
    assert "database administrator" not in result.improved_prompt.lower()


# ===========================================================================
# EC-12 — Non-stated error codes must not appear
# ===========================================================================

def test_ec_12_no_invented_http_codes():
    improved = (
        "## Role\n[Not specified in original — add before using]\n"
        "## Task\nCreate endpoint.\n"
        "## Codebase Context\n[Not specified in original — add before using]\n"
        "## Acceptance Criteria\nReturn 400 for missing fields. Return 409 for duplicate email.\n"
        "## Edge Cases\nMissing fields | Duplicate email.\n"
        "## Output Format\nCode blocks."
    )
    result = _call_rewrite(
        "Create endpoint. Return 400 for missing fields. Return 409 for duplicate email.",
        issues=[],
        mock_response=_make_llm_response(improved),
    )
    # 500, 422, 404 were never in the original
    assert "500" not in result.improved_prompt
    assert "422" not in result.improved_prompt
    assert " 404" not in result.improved_prompt


# ===========================================================================
# EC-13 — Response schema invention: only stated fields appear
# ===========================================================================

def test_ec_13_no_invented_response_schema_fields():
    improved = (
        "## Role\n[Not specified in original — add before using]\n"
        "## Task\nCreate user registration endpoint accepting name, email, password.\n"
        "## Codebase Context\nFields: name, email, password.\n"
        "## Acceptance Criteria\nValidate all fields.\n"
        "## Edge Cases\nMissing fields.\n"
        "## Output Format\nCode blocks."
    )
    result = _call_rewrite(
        "Create user endpoint accepting name, email, password",
        issues=[],
        mock_response=_make_llm_response(improved),
    )
    # Fields like created_at, id, token were never in the original
    assert "created_at" not in result.improved_prompt
    assert '"id"' not in result.improved_prompt
    assert "access_token" not in result.improved_prompt


# ===========================================================================
# EC-14 — High score (no issues): structured output, not prose rewrite
# ===========================================================================

def test_ec_14_high_score_no_issues_still_produces_structured_sections():
    """Even with issues=[], improved_prompt must use ## section headings."""
    improved = (
        "## Role\nSenior Python engineer.\n"
        "## Task\nCreate a FastAPI POST /register endpoint using Python 3.10, "
        "SQLAlchemy 1.4, Pydantic 1.9. Handle missing fields, duplicate email, empty payload.\n"
        "## Codebase Context\nLanguage: Python 3.10. Framework: FastAPI. "
        "ORM: SQLAlchemy 1.4. Validation: Pydantic 1.9.\n"
        "## Acceptance Criteria\nAll edge cases pass unit tests.\n"
        "## Edge Cases\nMissing fields | Duplicate email | Empty payload.\n"
        "## Output Format\nThree separate code blocks: model, route, tests."
    )
    result = _call_rewrite(
        "Create FastAPI POST /register endpoint using Python 3.10, SQLAlchemy 1.4, "
        "Pydantic 1.9. Handle missing fields, duplicate email, empty payload. "
        "Return model, route, and tests as code blocks.",
        issues=[],  # no issues — high score scenario
        mock_response=_make_llm_response(improved),
    )
    # Must have ## sections, not prose
    for heading in ["## Role", "## Task", "## Output Format"]:
        assert heading in result.improved_prompt, f"Missing section: {heading}"


# ===========================================================================
# EC-15 — Original echo is stripped by _strip_original_echo
# ===========================================================================

def test_ec_15_original_echo_stripped():
    """The echo HEADING and verbatim tail are stripped, but legitimate ## Task
    content that re-uses the original phrasing is preserved."""
    original = "Generate SQL query to fetch all orders"
    improved_with_echo = (
        "## Role\nData analyst.\n"
        "## Task\nGenerate SQL query to fetch all orders from the orders table.\n"
        "## Output Format\nSQL code block.\n\n"
        "# Original user request\n"
        "Generate SQL query to fetch all orders"
    )
    result = _strip_original_echo(improved_with_echo, original)
    # Echo heading must be gone
    assert "# Original user request" not in result
    # Structured sections must still be present
    assert "## Role" in result
    assert "## Task" in result
    assert "## Output Format" in result


def test_ec_15b_echo_not_stripped_when_absent():
    original = "Generate SQL query"
    improved_clean = "## Role\nData analyst.\n## Task\nGenerate a clean SQL query for order data."
    result = _strip_original_echo(improved_clean, original)
    assert "## Role" in result
    assert "## Task" in result


# ===========================================================================
# Integration: end-to-end EC-01 + EC-06 combined (Java + Spring Boot)
# ===========================================================================

def test_integration_java_spring_boot_both_flagged():
    """Original says 'Spring Boot in Java' — no contradiction, should be clean."""
    improved = (
        "## Role\nJava backend developer.\n"
        "## Task\nCreate a Spring Boot REST endpoint in Java for POST /users.\n"
        "## Codebase Context\nLanguage: Java. Framework: Spring Boot.\n"
        "## Acceptance Criteria\nHandle missing fields.\n"
        "## Edge Cases\nMissing fields | Duplicate email.\n"
        "## Output Format\nJava code blocks: entity, controller, tests."
    )
    result = _call_rewrite(
        "Create a Spring Boot REST endpoint in Java for POST /users",
        issues=[],
        mock_response=_make_llm_response(improved, gaps=[]),
    )
    assert "Java" in result.improved_prompt
    assert "Spring Boot" in result.improved_prompt
    # No contradiction when framework and language are consistent
    assert not any("Contradiction" in g for g in result.unresolved_gaps)


def test_integration_fastapi_java_both_preserved_and_flagged():
    """Original says 'FastAPI in Java' — both values must be in improved_prompt + contradiction in gaps."""
    improved = (
        "## Role\nBackend developer.\n"
        "## Task\nGenerate a FastAPI endpoint in Java for POST /users.\n"
        "## Codebase Context\nLanguage: Java. Framework: FastAPI.\n"
        "## Acceptance Criteria\nHandle missing fields.\n"
        "## Edge Cases\nMissing fields.\n"
        "## Output Format\nCode blocks."
    )
    gaps = [
        "Contradiction: FastAPI is a Python-only framework but the prompt specifies Java. "
        "Clarify whether the intended language is Python (use FastAPI) or Java "
        "(use Spring Boot / Micronaut / Quarkus)."
    ]
    result = _call_rewrite(
        "Generate a FastAPI endpoint in Java for POST /users",
        issues=[],
        mock_response=_make_llm_response(improved, gaps=gaps),
    )
    assert "FastAPI" in result.improved_prompt
    assert "Java" in result.improved_prompt
    contradiction_found = any(
        "Contradiction" in g and "FastAPI" in g and "Java" in g
        for g in result.unresolved_gaps
    )
    assert contradiction_found, f"Expected FastAPI/Java contradiction in gaps, got: {result.unresolved_gaps}"
