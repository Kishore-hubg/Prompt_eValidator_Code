from app.services import prompt_validation


class _DummyEval:
    def __init__(self):
        self.semantic_score = 88.0
        self.issues = ["Add constraints."]
        self.strengths = ["Clear objective."]


class _DummyRewrite:
    def __init__(self):
        self.improved_prompt = "Summarize the report in 5 bullets for executives."
        self.applied_guidelines = ["clear_direct_action", "output_format_control"]
        self.unresolved_gaps = []


def test_prefers_groq_in_auto_when_both_configured(monkeypatch):
    monkeypatch.setattr(prompt_validation, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(prompt_validation.llm_groq, "llm_configured", lambda: True)
    monkeypatch.setattr(prompt_validation.llm_anthropic, "llm_configured", lambda: True)
    monkeypatch.setattr(prompt_validation.llm_groq, "llm_evaluate_prompt", lambda *args, **kwargs: _DummyEval())
    monkeypatch.setattr(prompt_validation.llm_groq, "llm_rewrite_prompt", lambda *args, **kwargs: _DummyRewrite())

    result = prompt_validation.run_llm_validation(
        "Summarize this for leadership.",
        "persona_0",
        auto_improve=True,
    )
    assert result["llm_evaluation"]["used"] is True
    assert result["llm_evaluation"]["provider"] == "groq"
    assert result["llm_evaluation"]["rewrite_applied_guidelines"] == [
        "clear_direct_action",
        "output_format_control",
    ]


def test_uses_anthropic_when_forced_and_configured(monkeypatch):
    monkeypatch.setattr(prompt_validation, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(prompt_validation.llm_anthropic, "llm_configured", lambda: True)
    monkeypatch.setattr(prompt_validation.llm_anthropic, "llm_evaluate_prompt", lambda *args, **kwargs: _DummyEval())
    monkeypatch.setattr(prompt_validation.llm_anthropic, "llm_rewrite_prompt", lambda *args, **kwargs: _DummyRewrite())

    result = prompt_validation.run_llm_validation(
        "Create a status report.",
        "persona_2",
        auto_improve=True,
    )
    assert result["llm_evaluation"]["used"] is True
    assert result["llm_evaluation"]["provider"] == "anthropic"
    assert result["improved_prompt"] == "Summarize the report in 5 bullets for executives."


def test_strict_validate_required_raises_when_no_provider(monkeypatch):
    monkeypatch.setattr(prompt_validation, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(prompt_validation, "LLM_VALIDATE_REQUIRED", True)
    monkeypatch.setattr(prompt_validation.llm_groq, "llm_configured", lambda: False)
    monkeypatch.setattr(prompt_validation.llm_anthropic, "llm_configured", lambda: False)
    try:
        prompt_validation.run_llm_validation(
            "Summarize this.",
            "persona_0",
            auto_improve=False,
        )
        assert False, "Expected RuntimeError when strict validate is required"
    except RuntimeError as exc:
        assert "required" in str(exc).lower()
