from app.api.routes import _derive_issue_based_suggestions
from app.services.rules_engine import evaluate_prompt


def test_issue_based_suggestions_for_persona_1_are_not_static():
    issues = [
        "Specify the programming language, framework, and version.",
        "Start with a stronger action verb so the task is unmistakable.",
    ]
    suggestions = _derive_issue_based_suggestions("persona_1", issues, fallback=["fallback-1", "fallback-2"])
    joined = " ".join(suggestions).lower()
    assert "language" in joined
    assert "action verb" in joined
    assert "fallback-1" not in suggestions


def test_persona_1_technical_precision_accepts_explicit_stack_without_keywords():
    # Previously this could fail because keyword checks expected literal words
    # like language/framework/version, even when stack was explicit.
    prompt = (
        "Implement login API using Python 3.12 and FastAPI with Pydantic v2. "
        "Return code and tests."
    )
    score, dimensions, _strengths, issues, _guidelines = evaluate_prompt(prompt, "persona_1")
    assert score >= 0
    assert "Specify the programming language, framework, and version." not in issues
    precision = next((d for d in dimensions if d["name"] == "technical_precision"), None)
    assert precision is not None
    assert precision["passed"] is True


def test_issue_based_suggestions_apply_for_persona_3():
    issues = [
        "Reference the source document, section, transcript, or business context explicitly.",
        "For analysis/extraction tasks, require grounded output with source references.",
    ]
    suggestions = _derive_issue_based_suggestions("persona_3", issues, fallback=["fallback-a"])
    joined = " ".join(suggestions).lower()
    assert "source" in joined
    assert "citation" in joined or "traceability" in joined
    assert "fallback-a" not in suggestions


def test_issue_based_suggestions_apply_for_persona_4():
    issues = [
        "No tone guidance specified.",
        "No compliance cue present.",
        "Add customer issue context and the desired next step or escalation path.",
    ]
    suggestions = _derive_issue_based_suggestions("persona_4", issues, fallback=["fallback-b"])
    joined = " ".join(suggestions).lower()
    assert "tone" in joined
    assert "policy" in joined or "compliance" in joined
    assert "customer context" in joined or "issue" in joined
    assert "fallback-b" not in suggestions
