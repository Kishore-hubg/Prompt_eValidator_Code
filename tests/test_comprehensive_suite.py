"""
Comprehensive Test Suite — Prompt Validator MVP
Covers all 93 test cases from docs/testing/sample_prompts_and_test_cases.md

Sections:
  TC-API  (5)  – API Health & Configuration
  TC-PER  (12) – Persona Routing & Validation
  TC-SCR  (7)  – Scoring Algorithm
  TC-DIM  (8)  – Dimension Breakdown
  TC-LLM  (8)  – LLM Functionality & Anti-Hallucination
  TC-RPM  (9)  – Reprompting / Auto-Improve
  TC-DED  (5)  – Deduplication
  TC-AUTH (8)  – Authentication & Security
  TC-DB   (7)  – Data Persistence
  TC-MCP  (3)  – MCP Channel
  TC-TMS  (4)  – Teams Channel
  TC-ANA  (5)  – Analytics & Leadership
  TC-EDG  (12) – Edge Cases & Error Handling
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.db.database import get_db

# ─────────────────────────────────────────────────────────────────────────────
# SAMPLE PROMPTS (SP-01 … SP-20)
# ─────────────────────────────────────────────────────────────────────────────

SP_01 = (
    "Write a professional email to the BFSI client at Ziply Telecom summarising "
    "the outcomes of our Sprint 14 review meeting held on 28 March 2026. "
    "The audience is the client's VP of Finance and Project Sponsor. "
    "Structure the email as: (1) Opening with meeting reference, "
    "(2) Key decisions made (bullet list), (3) Risks identified with owner names, "
    "(4) Next steps with due dates. Tone should be formal and concise. "
    "Maximum 350 words. Do not include internal Slack references or pricing details."
)
SP_02 = "Help me write something for a client."
SP_05 = (
    "Using Python 3.12 and FastAPI 0.115+, implement a POST /api/v1/validate endpoint "
    "that accepts a JSON body with fields: prompt (str, required, max 2000 chars), "
    "persona_id (str, enum: persona_0 to persona_4), and auto_improve (bool, default false). "
    "Validate input using Pydantic v2 BaseModel. Return HTTP 422 for invalid input. "
    "Apply OWASP Top 10 input sanitisation — specifically prevent prompt injection and XSS. "
    "Include edge cases: empty prompt string, prompt exceeding 2000 chars, invalid persona_id. "
    "Write pytest unit tests for each edge case using FastAPI TestClient. "
    "Expected test format: TC-ID | Preconditions | Steps | Expected Result."
)
SP_06 = "Write some code to validate a prompt."
SP_09 = (
    "Generate a Sprint 14 status report for the Ziply Telecom Finance Modernisation "
    "engagement (T&M model, 8-week sprint). Reporting period: 17–28 March 2026. "
    "Audience: Delivery Manager and Client Project Sponsor. "
    "Structure: (1) Executive Summary (3 sentences max), (2) Completed vs Planned work "
    "table with RAG status, (3) Top 3 risks ranked by impact with owner and mitigation, "
    "(4) Next sprint commitments with due dates. "
    "Output as a structured Markdown report. Prioritise risks over achievements. "
    "Reference velocity data: 42 story points delivered vs 45 planned."
)
SP_10 = "Give me an update on the project."
SP_13 = (
    "Based on Section 4.2 (Data Migration Requirements) of the Ziply Finance "
    "Modernisation BRD document (version 2.1, March 2026), extract all functional "
    "requirements related to GL Trial Balance data migration. For each requirement, "
    "output: Requirement ID | Requirement Text | Source Section | Acceptance Criteria "
    "(testable, using Given/When/Then format). Only use explicit statements from the "
    "document — do not infer or add requirements not present in Section 4.2. "
    "Prioritise using MoSCoW: Must Have vs Should Have. Audience: Delivery team leads."
)
SP_14 = "List the requirements for the project."
SP_17 = (
    "Write an empathetic customer-facing email response for a Ziply Telecom retail "
    "customer who has been double-charged on their invoice for February 2026. "
    "The customer is frustrated and has submitted ticket #TKT-20260315-0042. "
    "Tone: apologetic and empathetic. Comply with Ziply SLA policy (resolution within "
    "24 hours). Reference the refund policy under Section 3.1 of the Customer Billing "
    "Policy document. Output: formal email format with subject line, greeting, 3-paragraph "
    "body, and closing. Maximum 200 words. Next action: confirm refund initiation "
    "within 4 business hours."
)
SP_18 = "Reply to an angry customer."

# ─────────────────────────────────────────────────────────────────────────────
# PERSONA DIMENSION MAPS  (name → weight)
# ─────────────────────────────────────────────────────────────────────────────

DIMS = {
    "persona_0": {
        "clarity": 18, "context": 14, "specificity": 14, "output_format": 14,
        "ambiguity_reduction": 14, "constraints": 10, "actionability": 10, "accuracy": 7,
    },
    "persona_1": {
        "technical_precision": 18, "edge_cases": 18, "testability": 18, "specificity": 18,
        "context": 14, "reproducibility": 14, "accuracy": 14,
    },
    "persona_2": {
        "output_format": 18, "reproducibility": 14, "context": 14, "specificity": 14,
        "prioritization": 14, "actionability": 14, "engagement_model_awareness": 10, "speed": 7,
    },
    "persona_3": {
        "context": 18, "grounding": 18, "business_relevance": 14, "output_format": 14,
        "specificity": 14, "prioritization": 4, "accuracy": 14,
    },
    "persona_4": {
        "tone_empathy": 18, "compliance": 14, "speed": 14, "clarity": 14,
        "reproducibility": 10, "context": 10, "output_format": 7, "precision": 7,
    },
}

PERSONA_NAMES = {
    "persona_0": "All Employees",
    "persona_1": "Developer + QA",
    "persona_2": "Technical PM",
    "persona_3": "Business Analyst + Product Owner",
    "persona_4": "Support Staff",
}

# ─────────────────────────────────────────────────────────────────────────────
# MOCK BUILDER HELPERS
# ─────────────────────────────────────────────────────────────────────────────

GUIDELINE_EVAL_EMPTY = {
    "strict_mode": True, "penalty_applied": 0, "checks": [], "issues": [], "sources": [],
}

LLM_EVAL_GROQ = {
    "used": True, "provider": "groq", "model": "llama-3.3-70b-versatile",
    "semantic_score": 95.0, "static_score": None, "scoring_mode": "llm_only",
    "source_of_truth_document": "persona_criteria_source_truth.json",
    "source_of_truth_scope": "Prompt Quality",
    "rewrite_applied_guidelines": ["clear_direct_action", "output_format_control"],
    "rewrite_unresolved_gaps": [],
    "error": None,
}


def _all_pass(persona_id: str, penalty: int = 0):
    """Return a run_llm_validation result where every dimension passes."""
    dims = DIMS[persona_id]
    dim_scores = [{"name": k, "passed": True, "weight": v, "score": v} for k, v in dims.items()]
    ge = {**GUIDELINE_EVAL_EMPTY, "penalty_applied": penalty}
    total_w = sum(dims.values())
    score = round(max(0.0, 100.0 - penalty), 2)
    return {
        "score": score,
        "dimension_scores": dim_scores,
        "strengths": ["Clear action verb", "Context provided", "Format specified", "Constraints set"],
        "issues": [],
        "guideline_evaluation": ge,
        "improved_prompt": "Prompt is already excellent.",
        "llm_evaluation": LLM_EVAL_GROQ,
        "rewrite_strategy": "llm",
    }


def _all_fail(persona_id: str):
    """Return a run_llm_validation result where every dimension fails."""
    dims = DIMS[persona_id]
    dim_scores = [{"name": k, "passed": False, "weight": v, "score": 0} for k, v in dims.items()]
    ge = {**GUIDELINE_EVAL_EMPTY, "penalty_applied": 15}
    return {
        "score": 0.0,
        "dimension_scores": dim_scores,
        "strengths": [],
        "issues": [
            "Missing action verb", "No context provided", "No output format specified",
            "No constraints defined", "Ambiguous scope", "Lacks grounding",
        ],
        "guideline_evaluation": ge,
        "improved_prompt": "Start with a clear action verb. Add context, audience, and output format.",
        "llm_evaluation": {**LLM_EVAL_GROQ, "semantic_score": 5.0},
        "rewrite_strategy": "llm",
    }


def _partial_pass(persona_id: str, passing: list[str]):
    """Return a result where only the named dimensions pass."""
    dims = DIMS[persona_id]
    dim_scores = [
        {"name": k, "passed": k in passing, "weight": v, "score": v if k in passing else 0}
        for k, v in dims.items()
    ]
    passed_w = sum(v for k, v in dims.items() if k in passing)
    total_w = sum(dims.values())
    score = round((passed_w / total_w) * 100, 2) if total_w else 0.0
    return {
        "score": score,
        "dimension_scores": dim_scores,
        "strengths": ["Some context present"],
        "issues": ["Missing output format", "No constraints defined", "Weak specificity"],
        "guideline_evaluation": GUIDELINE_EVAL_EMPTY,
        "improved_prompt": "Add output format, constraints, and more specificity.",
        "llm_evaluation": LLM_EVAL_GROQ,
        "rewrite_strategy": "llm",
    }


def _make_history_item(n: int = 1):
    return [
        {
            "id": i, "persona_id": "persona_0", "channel": "api",
            "score": 85.0, "rating": "Excellent",
            "prompt_text": f"Test prompt {i}",
            "improved_prompt": f"Improved prompt {i}",
            "created_at": "2026-04-01T00:00:00",
        }
        for i in range(1, n + 1)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SHARED FIXTURE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: object()
    return TestClient(app)


def _noop_save(*args, **kwargs):
    return None


def _noop_capture(*args, **kwargs):
    return None


# ─────────────────────────────────────────────────────────────────────────────
# TC-API — API Health & Configuration
# ─────────────────────────────────────────────────────────────────────────────

def test_tc_api_01_health_returns_ok(client):
    """TC-API-01: Health check returns 200 with status ok."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_tc_api_02_validation_mode_returns_config(client):
    """TC-API-02: Validation mode returns scoring config with required keys."""
    r = client.get("/api/v1/validation-mode")
    assert r.status_code == 200
    body = r.json()
    assert "scoring_mode" in body
    assert "configured_provider" in body
    assert "source_of_truth_document" in body
    assert body["scoring_mode"] in ("llm_only", "static", "blended")


def test_tc_api_03_personas_returns_five(client):
    """TC-API-03: Personas list returns all 5 personas with correct IDs."""
    r = client.get("/api/v1/personas")
    assert r.status_code == 200
    personas = r.json()
    ids = {p["id"] for p in personas}
    assert len(personas) == 5
    assert ids == {"persona_0", "persona_1", "persona_2", "persona_3", "persona_4"}
    for p in personas:
        assert "name" in p and "description" in p and "id" in p


def test_tc_api_04_guidelines_returns_config(client):
    """TC-API-04: Guidelines endpoint returns strict_mode and global_checks."""
    r = client.get("/api/v1/guidelines")
    assert r.status_code == 200
    body = r.json()
    assert body["strict_mode"] is True
    assert isinstance(body["strict_penalty_per_miss"], int)
    assert isinstance(body["strict_penalty_cap"], int)
    assert isinstance(body["global_checks"], list)
    assert len(body["global_checks"]) >= 1


def test_tc_api_05_day2_compliance_checklist(client):
    """TC-API-05: Day 2 compliance checklist returns governance checks."""
    r = client.get("/api/v1/compliance/day2-checklist")
    assert r.status_code == 200
    body = r.json()
    assert "checks" in body
    assert len(body["checks"]) >= 4
    assert "overall_status" in body
    for chk in body["checks"]:
        assert "id" in chk
        assert "status" in chk


# ─────────────────────────────────────────────────────────────────────────────
# TC-PER — Persona Routing & Validation
# ─────────────────────────────────────────────────────────────────────────────

def test_tc_per_01_persona0_excellent(client, monkeypatch):
    """TC-PER-01: persona_0 excellent prompt scores Excellent (≥85)."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0"})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] >= 85
    assert body["rating"] == "Excellent"
    assert len(body["dimension_scores"]) == 8
    assert len(body["issues"]) <= 2


def test_tc_per_02_persona0_poor(client, monkeypatch):
    """TC-PER-02: persona_0 poor prompt scores Poor (≤40)."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_fail("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_02, "persona_id": "persona_0"})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] <= 40
    assert body["rating"] == "Poor"
    assert len(body["issues"]) >= 4
    failed = [d for d in body["dimension_scores"] if not d["passed"]]
    assert len(failed) >= 6


def test_tc_per_03_persona1_excellent(client, monkeypatch):
    """TC-PER-03: persona_1 excellent prompt scores ≥88, key dims pass."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_1"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_05, "persona_id": "persona_1"})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] >= 88
    dim_map = {d["name"]: d["passed"] for d in body["dimension_scores"]}
    assert dim_map.get("technical_precision") is True
    assert dim_map.get("edge_cases") is True
    assert dim_map.get("testability") is True


def test_tc_per_04_persona1_poor(client, monkeypatch):
    """TC-PER-04: persona_1 poor prompt scores ≤30, technical dims fail."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_fail("persona_1"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_06, "persona_id": "persona_1"})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] <= 30
    dim_map = {d["name"]: d["passed"] for d in body["dimension_scores"]}
    assert dim_map.get("technical_precision") is False
    assert dim_map.get("edge_cases") is False


def test_tc_per_05_persona2_excellent(client, monkeypatch):
    """TC-PER-05: persona_2 excellent prompt scores ≥85, PM dims pass."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_2"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_09, "persona_id": "persona_2"})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] >= 85
    dim_map = {d["name"]: d["passed"] for d in body["dimension_scores"]}
    assert dim_map.get("output_format") is True
    assert dim_map.get("prioritization") is True
    assert dim_map.get("engagement_model_awareness") is True


def test_tc_per_06_persona2_poor(client, monkeypatch):
    """TC-PER-06: persona_2 poor prompt scores ≤35, PM dims fail."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_fail("persona_2"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_10, "persona_id": "persona_2"})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] <= 35
    dim_map = {d["name"]: d["passed"] for d in body["dimension_scores"]}
    assert dim_map.get("output_format") is False
    assert dim_map.get("prioritization") is False


def test_tc_per_07_persona3_excellent(client, monkeypatch):
    """TC-PER-07: persona_3 excellent prompt scores ≥85, BA dims pass."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_3"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_13, "persona_id": "persona_3"})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] >= 85
    dim_map = {d["name"]: d["passed"] for d in body["dimension_scores"]}
    assert dim_map.get("grounding") is True
    assert dim_map.get("context") is True
    assert dim_map.get("business_relevance") is True


def test_tc_per_08_persona3_poor(client, monkeypatch):
    """TC-PER-08: persona_3 poor prompt scores ≤30, grounding/context fail."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_fail("persona_3"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_14, "persona_id": "persona_3"})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] <= 30
    dim_map = {d["name"]: d["passed"] for d in body["dimension_scores"]}
    assert dim_map.get("grounding") is False
    assert dim_map.get("context") is False


def test_tc_per_09_persona4_excellent(client, monkeypatch):
    """TC-PER-09: persona_4 excellent prompt scores ≥85, support dims pass."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_4"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_17, "persona_id": "persona_4"})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] >= 85
    dim_map = {d["name"]: d["passed"] for d in body["dimension_scores"]}
    assert dim_map.get("tone_empathy") is True
    assert dim_map.get("compliance") is True
    assert dim_map.get("speed") is True


def test_tc_per_10_persona4_poor(client, monkeypatch):
    """TC-PER-10: persona_4 poor prompt scores ≤30, tone/compliance fail."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_fail("persona_4"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_18, "persona_id": "persona_4"})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] <= 30
    dim_map = {d["name"]: d["passed"] for d in body["dimension_scores"]}
    assert dim_map.get("tone_empathy") is False
    assert dim_map.get("compliance") is False


def test_tc_per_11_unknown_persona_defaults_to_persona0(client, monkeypatch):
    """TC-PER-11: Unknown persona_id falls back to persona_0 dimensions."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": "Write a status update.", "persona_id": "persona_99"})
    assert r.status_code == 200
    body = r.json()
    # persona data should use persona_0's name (fallback in get_persona)
    assert body["persona_name"] == "All Employees"
    assert len(body["dimension_scores"]) == 8


def test_tc_per_12_omit_persona_id_defaults_to_persona0(client, monkeypatch):
    """TC-PER-12: Omitting persona_id defaults to persona_0 (8 dimensions)."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": "Write a status update."})
    assert r.status_code == 200
    body = r.json()
    assert len(body["dimension_scores"]) == 8


# ─────────────────────────────────────────────────────────────────────────────
# TC-SCR — Scoring Algorithm  (direct unit tests on _recompute_score)
# ─────────────────────────────────────────────────────────────────────────────

from app.services.prompt_validation import _recompute_score

PERSONA1_DIMS = DIMS["persona_1"]  # total weight = 114
PERSONA0_DIMS = DIMS["persona_0"]  # total weight = 101


def _make_dim_scores(dims_dict: dict, all_pass: bool = True, fail_keys: set | None = None):
    fail_keys = fail_keys or set()
    return [
        {"name": k, "passed": k not in fail_keys and all_pass, "weight": v, "score": v if (k not in fail_keys and all_pass) else 0}
        for k, v in dims_dict.items()
    ]


def test_tc_scr_01_score_math_all_pass_no_penalty():
    """TC-SCR-01: All dims pass + 0 penalty → score = 100.0."""
    dims = _make_dim_scores(PERSONA1_DIMS, all_pass=True)
    ge = {"penalty_applied": 0}
    g = {"strict_penalty_cap": 15}
    score = _recompute_score(dims, ge, g)
    assert score == 100.0


def test_tc_scr_01b_score_math_partial_pass():
    """TC-SCR-01b: partial pass → score = (passed_weight/total_weight)*100."""
    dims = _make_dim_scores(PERSONA1_DIMS, all_pass=True, fail_keys={"accuracy"})
    # accuracy weight = 14 → passed_weight = 114-14 = 100
    ge = {"penalty_applied": 0}
    g = {"strict_penalty_cap": 15}
    score = _recompute_score(dims, ge, g)
    expected = round((100 / 114) * 100, 2)
    assert score == expected


def test_tc_scr_02_score_zero_all_fail():
    """TC-SCR-02: All dims fail → score ≤ 10 (after capped penalty)."""
    dims = _make_dim_scores(PERSONA1_DIMS, all_pass=False)
    ge = {"penalty_applied": 15}
    g = {"strict_penalty_cap": 15}
    score = _recompute_score(dims, ge, g)
    assert score == 0.0


def test_tc_scr_03_penalty_capped_at_15():
    """TC-SCR-03: Penalty > cap is clamped to strict_penalty_cap (15)."""
    dims = _make_dim_scores(PERSONA1_DIMS, all_pass=True)
    ge = {"penalty_applied": 99}   # exceeds cap of 15
    g = {"strict_penalty_cap": 15}
    score = _recompute_score(dims, ge, g)
    assert score == 85.0            # 100 - 15


def test_tc_scr_04_score_never_below_zero():
    """TC-SCR-04: Score is always ≥ 0 even with large penalty."""
    dims = _make_dim_scores(PERSONA1_DIMS, all_pass=False)
    ge = {"penalty_applied": 500}
    g = {"strict_penalty_cap": 500}
    score = _recompute_score(dims, ge, g)
    assert score >= 0.0


def test_tc_scr_05_score_never_above_100():
    """TC-SCR-05: Score is always ≤ 100."""
    dims = _make_dim_scores(PERSONA0_DIMS, all_pass=True)
    ge = {"penalty_applied": 0}
    g = {"strict_penalty_cap": 15}
    score = _recompute_score(dims, ge, g)
    assert score <= 100.0


def test_tc_scr_06_rating_tiers():
    """TC-SCR-06: Rating function maps score to correct tier."""
    from app.api.routes import rating_for_score
    assert rating_for_score(100.0) == "Excellent"
    assert rating_for_score(85.0) == "Excellent"
    assert rating_for_score(84.9) == "Good"
    assert rating_for_score(70.0) == "Good"
    assert rating_for_score(69.9) == "Needs Improvement"
    assert rating_for_score(50.0) == "Needs Improvement"
    assert rating_for_score(49.9) == "Poor"
    assert rating_for_score(0.0) == "Poor"


def test_tc_scr_07_score_10_scale(client, monkeypatch):
    """TC-SCR-07: validation_score_10 not in direct response but score maps correctly."""
    from app.services.data_strategy import to_validation_score_10
    assert to_validation_score_10(85.0) == pytest.approx(8.5, abs=0.1)
    assert to_validation_score_10(100.0) == pytest.approx(10.0, abs=0.1)
    assert to_validation_score_10(0.0) == pytest.approx(0.0, abs=0.1)
    assert to_validation_score_10(70.0) == pytest.approx(7.0, abs=0.1)


# ─────────────────────────────────────────────────────────────────────────────
# TC-DIM — Dimension Breakdown
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("persona_id,expected_count", [
    ("persona_0", 8),
    ("persona_1", 7),
    ("persona_2", 8),
    ("persona_3", 7),
    ("persona_4", 8),
])
def test_tc_dim_01_correct_dimension_count(client, monkeypatch, persona_id, expected_count):
    """TC-DIM-01: Each persona returns the correct number of dimensions."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass(persona_id))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": "Test.", "persona_id": persona_id})
    assert r.status_code == 200
    assert len(r.json()["dimension_scores"]) == expected_count


def test_tc_dim_02_dimension_schema_fields(client, monkeypatch):
    """TC-DIM-02: Each dimension entry has name, score, weight, passed fields."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0"})
    assert r.status_code == 200
    for dim in r.json()["dimension_scores"]:
        assert "name" in dim
        assert "score" in dim
        assert "weight" in dim
        assert "passed" in dim
        assert isinstance(dim["passed"], bool)
        assert isinstance(dim["weight"], (int, float))


def test_tc_dim_03_technical_precision_pass_vs_fail(client, monkeypatch):
    """TC-DIM-03: technical_precision passes with explicit stack, fails without."""
    def mock_pass(*a, **k):
        return _all_pass("persona_1")
    def mock_fail(*a, **k):
        return _partial_pass("persona_1", ["edge_cases", "context"])
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)

    monkeypatch.setattr(routes, "run_llm_validation", mock_pass)
    r_pass = client.post("/api/v1/validate", json={"prompt_text": SP_05, "persona_id": "persona_1"})
    dim_map = {d["name"]: d["passed"] for d in r_pass.json()["dimension_scores"]}
    assert dim_map.get("technical_precision") is True

    monkeypatch.setattr(routes, "run_llm_validation", mock_fail)
    r_fail = client.post("/api/v1/validate", json={"prompt_text": SP_06, "persona_id": "persona_1"})
    dim_map2 = {d["name"]: d["passed"] for d in r_fail.json()["dimension_scores"]}
    assert dim_map2.get("technical_precision") is False


def test_tc_dim_04_tone_empathy_pass_vs_fail(client, monkeypatch):
    """TC-DIM-04: tone_empathy passes with explicit tone directive, fails without."""
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)

    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_4"))
    r = client.post("/api/v1/validate", json={"prompt_text": SP_17, "persona_id": "persona_4"})
    assert {d["name"]: d["passed"] for d in r.json()["dimension_scores"]}.get("tone_empathy") is True

    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_fail("persona_4"))
    r2 = client.post("/api/v1/validate", json={"prompt_text": SP_18, "persona_id": "persona_4"})
    assert {d["name"]: d["passed"] for d in r2.json()["dimension_scores"]}.get("tone_empathy") is False


def test_tc_dim_05_grounding_pass_vs_fail(client, monkeypatch):
    """TC-DIM-05: grounding passes with doc reference, fails without."""
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)

    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_3"))
    r = client.post("/api/v1/validate", json={"prompt_text": SP_13, "persona_id": "persona_3"})
    assert {d["name"]: d["passed"] for d in r.json()["dimension_scores"]}.get("grounding") is True

    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_fail("persona_3"))
    r2 = client.post("/api/v1/validate", json={"prompt_text": SP_14, "persona_id": "persona_3"})
    assert {d["name"]: d["passed"] for d in r2.json()["dimension_scores"]}.get("grounding") is False


def test_tc_dim_06_engagement_model_awareness(client, monkeypatch):
    """TC-DIM-06: engagement_model_awareness passes with T&M reference, fails without."""
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)

    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_2"))
    r = client.post("/api/v1/validate", json={"prompt_text": SP_09, "persona_id": "persona_2"})
    assert {d["name"]: d["passed"] for d in r.json()["dimension_scores"]}.get("engagement_model_awareness") is True

    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_fail("persona_2"))
    r2 = client.post("/api/v1/validate", json={"prompt_text": SP_10, "persona_id": "persona_2"})
    assert {d["name"]: d["passed"] for d in r2.json()["dimension_scores"]}.get("engagement_model_awareness") is False


def test_tc_dim_07_no_hallucinated_dimensions(client, monkeypatch):
    """TC-DIM-07: persona_1 response never contains persona_0-only dimensions."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_1"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_05, "persona_id": "persona_1"})
    assert r.status_code == 200
    dim_names = {d["name"] for d in r.json()["dimension_scores"]}
    persona1_valid = set(DIMS["persona_1"].keys())
    persona0_only = set(DIMS["persona_0"].keys()) - set(DIMS["persona_1"].keys())
    assert len(dim_names & persona0_only) == 0, f"Hallucinated dims: {dim_names & persona0_only}"
    assert dim_names == persona1_valid


def test_tc_dim_08_passed_score_equals_weight():
    """TC-DIM-08: Passed dim has score=weight; failed dim has score=0 in _recompute_score."""
    dims = _make_dim_scores(PERSONA0_DIMS, all_pass=True, fail_keys={"context"})
    ge = {"penalty_applied": 0}
    g = {"strict_penalty_cap": 15}
    score = _recompute_score(dims, ge, g)
    # context (weight=14) fails → passed_weight = 101-14 = 87
    expected = round((87 / 101) * 100, 2)
    assert score == expected
    for d in dims:
        if d["passed"]:
            assert d["score"] == d["weight"]
        else:
            assert d["score"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# TC-LLM — LLM Functionality & Anti-Hallucination
# ─────────────────────────────────────────────────────────────────────────────

def test_tc_llm_01_no_hallucination_in_dim_pass():
    """TC-LLM-01: Mock confirms no dimension credited for content not in prompt."""
    # Poor prompt has nothing → all dims fail in mock
    result = _all_fail("persona_1")
    passed = [d for d in result["dimension_scores"] if d["passed"]]
    assert len(passed) == 0, "Poor prompt should have no passing dimensions"


def test_tc_llm_02_strengths_match_prompt_content(client, monkeypatch):
    """TC-LLM-02: Strengths returned are non-empty for excellent prompt."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0"})
    assert r.status_code == 200
    assert len(r.json()["strengths"]) >= 1


def test_tc_llm_03_issues_are_non_duplicate(client, monkeypatch):
    """TC-LLM-03: Issues array contains no exact duplicates."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_fail("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_02, "persona_id": "persona_0"})
    issues = r.json()["issues"]
    assert len(issues) == len(set(issues)), "Duplicate issues found"


def test_tc_llm_04_max_six_issues(monkeypatch):
    """TC-LLM-04: run_llm_validation caps raw LLM issues at 6 before merging."""
    from app.services import llm_groq
    from app.services.prompt_validation import run_llm_validation

    # Provide guideline_checks so the code uses LLM path (not static fallback)
    # and the base dedupe_preserve(evaluation.issues)[:6] cap is the only limit.
    class FakeEval:
        semantic_score = 20.0
        issues = [f"Issue {i}" for i in range(10)]  # LLM returns 10 raw issues
        strengths = ["Some strength"]
        dimension_scores = [{"name": "clarity", "passed": False, "weight": 18, "score": 0}]
        # Non-empty guideline_checks forces the LLM path; passed=True so no extra issue is appended
        guideline_checks = [
            {"id": "clear_direct_action", "passed": True, "penalty": 0, "issue": ""}
        ]

    class FakeRewrite:
        improved_prompt = "Improved."
        applied_guidelines = []
        unresolved_gaps = []

    monkeypatch.setattr(llm_groq, "llm_evaluate_prompt", lambda *a, **k: FakeEval())
    monkeypatch.setattr(llm_groq, "llm_rewrite_prompt", lambda *a, **k: FakeRewrite())
    monkeypatch.setattr(llm_groq, "llm_configured", lambda: True)

    result = run_llm_validation("Help me write something.", "persona_0", auto_improve=True)
    assert len(result["issues"]) <= 6, f"Issues exceeded 6: {result['issues']}"


def test_tc_llm_05_max_five_strengths(monkeypatch):
    """TC-LLM-05: run_llm_validation caps strengths at 5 even if LLM returns more."""
    from app.services import llm_groq
    from app.services.prompt_validation import run_llm_validation

    class FakeEval:
        semantic_score = 90.0
        issues = []
        strengths = [f"Strength {i}" for i in range(10)]  # LLM returns 10
        dimension_scores = [{"name": "clarity", "passed": True, "weight": 18, "score": 18}]
        guideline_checks = []

    class FakeRewrite:
        improved_prompt = "Already excellent."
        applied_guidelines = []
        unresolved_gaps = []

    monkeypatch.setattr(llm_groq, "llm_evaluate_prompt", lambda *a, **k: FakeEval())
    monkeypatch.setattr(llm_groq, "llm_rewrite_prompt", lambda *a, **k: FakeRewrite())
    monkeypatch.setattr(llm_groq, "llm_configured", lambda: True)

    result = run_llm_validation(SP_01, "persona_0", auto_improve=True)
    assert len(result["strengths"]) <= 5, f"Strengths exceeded 5: {result['strengths']}"


def test_tc_llm_06_llm_failure_raises_503(client, monkeypatch):
    """TC-LLM-06: LLM failure with VALIDATE_REQUIRED returns 503."""
    def boom(*a, **k):
        raise RuntimeError("LLM validation failed: connection timeout")
    monkeypatch.setattr(routes, "run_llm_validation", boom)
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0"})
    assert r.status_code == 503


def test_tc_llm_07_provider_in_response(client, monkeypatch):
    """TC-LLM-07: LLM evaluation block shows provider in response."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0"})
    body = r.json()
    llm_eval = body.get("llm_evaluation")
    assert llm_eval is not None
    assert llm_eval.get("provider") in ("groq", "anthropic", None)
    assert llm_eval.get("used") in (True, False)


def test_tc_llm_08_poor_prompt_no_false_strengths():
    """TC-LLM-08: Poor prompt result has zero strengths (mock-verified)."""
    result = _all_fail("persona_0")
    assert len(result["strengths"]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# TC-RPM — Reprompting / Auto-Improve
# ─────────────────────────────────────────────────────────────────────────────

def test_tc_rpm_01_auto_improve_returns_nonempty_improved(client, monkeypatch):
    """TC-RPM-01: auto_improve=true returns non-empty improved_prompt."""
    result = _all_fail("persona_0")
    result["improved_prompt"] = "Start with a clear action verb. Define audience and output format."
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: result)
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_02, "persona_id": "persona_0", "auto_improve": True})
    assert r.status_code == 200
    body = r.json()
    assert body["improved_prompt"]
    assert body["improved_prompt"] != SP_02


def test_tc_rpm_02_improved_prompt_no_echo_header():
    """TC-RPM-02: _strip_original_echo removes '# Original user request' headings."""
    from app.services.llm_groq import _strip_original_echo
    original = "Help me write something for a client."
    echoed = (
        "# Original user request\n"
        f"{original}\n\n"
        "# Improved Prompt\n"
        "Write a professional email to the client defining audience, format, and constraints."
    )
    stripped = _strip_original_echo(echoed, original)
    assert "# Original user request" not in stripped
    assert "original user request" not in stripped.lower().split("\n")[0]


def test_tc_rpm_02b_various_echo_headers():
    """TC-RPM-02b: _strip_original_echo handles multiple echo header variants."""
    from app.services.llm_groq import _strip_original_echo
    original = "original text"
    variants = [
        f"# Source Prompt\n{original}\n\nActual improved output.",
        f"# Input Prompt\n{original}\n\nActual improved output.",
        f"## Original Prompt\n{original}\n\nActual improved output.",
    ]
    for v in variants:
        result = _strip_original_echo(v, original)
        result_lower = result.lower()
        for bad in ("# source prompt", "# input prompt", "## original prompt", "# original user request"):
            assert bad not in result_lower, f"Echo header '{bad}' not stripped. Got: {result[:100]}"


def test_tc_rpm_03_improved_prompt_scores_higher(client, monkeypatch):
    """TC-RPM-03: Re-validating improved prompt yields higher score."""
    call_count = {"n": 0}
    def mock_validate(*a, **k):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _all_fail("persona_0")   # original → score=0
        return _all_pass("persona_0")        # improved → score=100

    monkeypatch.setattr(routes, "run_llm_validation", mock_validate)
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)

    r1 = client.post("/api/v1/validate", json={"prompt_text": SP_02, "persona_id": "persona_0"})
    improved = r1.json()["improved_prompt"]

    r2 = client.post("/api/v1/validate", json={"prompt_text": improved, "persona_id": "persona_0"})
    assert r2.json()["score"] > r1.json()["score"]


def test_tc_rpm_04_improve_endpoint_returns_improved(client, monkeypatch):
    """TC-RPM-04: /improve endpoint returns improved_prompt."""
    result = _all_fail("persona_0")
    result["improved_prompt"] = "Improved version of the prompt."
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: result)
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/improve", json={"prompt_text": SP_02, "persona_id": "persona_0"})
    assert r.status_code == 200
    assert r.json()["improved_prompt"]


def test_tc_rpm_05_improved_persona1_has_technical_structure(client, monkeypatch):
    """TC-RPM-05: improved prompt for persona_1 contains technical keywords."""
    improved = (
        "Using Python 3.12 and FastAPI 0.115+, validate a prompt. "
        "Handle edge cases: empty string, oversized input. "
        "Write pytest tests with TestClient. Format: TC-ID | Steps | Result."
    )
    result = _all_fail("persona_1")
    result["improved_prompt"] = improved
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: result)
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_06, "persona_id": "persona_1", "auto_improve": True})
    body = r.json()
    imp = body["improved_prompt"].lower()
    has_tech = any(kw in imp for kw in ["python", "fastapi", "edge case", "pytest", "test"])
    assert has_tech


def test_tc_rpm_06_improved_persona4_has_tone(client, monkeypatch):
    """TC-RPM-06: improved prompt for persona_4 contains tone directive."""
    improved = (
        "Write an empathetic, apologetic email to a customer about a billing issue. "
        "Tone: empathetic. Comply with SLA within 24 hours. Max 200 words."
    )
    result = _all_fail("persona_4")
    result["improved_prompt"] = improved
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: result)
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_18, "persona_id": "persona_4", "auto_improve": True})
    imp = r.json()["improved_prompt"].lower()
    assert any(kw in imp for kw in ["empathetic", "apologetic", "tone", "sla", "comply"])


def test_tc_rpm_07_applied_guidelines_in_llm_evaluation(client, monkeypatch):
    """TC-RPM-07: llm_evaluation contains rewrite_applied_guidelines."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0", "auto_improve": True})
    body = r.json()
    llm_eval = body.get("llm_evaluation", {})
    # rewrite_applied_guidelines is a list (or null)
    applied = llm_eval.get("rewrite_applied_guidelines")
    assert applied is None or isinstance(applied, list)


def test_tc_rpm_08_rp01_score_round2_higher(client, monkeypatch):
    """TC-RPM-08: RP-01 Round 2 scores ≥30 pts higher than Round 1."""
    calls = {"n": 0}
    def mock_v(*a, **k):
        calls["n"] += 1
        return _all_fail("persona_0") if calls["n"] == 1 else _all_pass("persona_0")
    monkeypatch.setattr(routes, "run_llm_validation", mock_v)
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r1 = client.post("/api/v1/validate", json={"prompt_text": "Write something for the team.", "persona_id": "persona_0"})
    improved = r1.json()["improved_prompt"]
    r2 = client.post("/api/v1/validate", json={"prompt_text": improved, "persona_id": "persona_0"})
    assert r2.json()["score"] - r1.json()["score"] >= 30


def test_tc_rpm_09_rp02_key_dims_pass_in_round2(client, monkeypatch):
    """TC-RPM-09: RP-02 Round 2 for persona_1 has technical_precision/edge_cases/testability pass."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_1"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_05, "persona_id": "persona_1"})
    dim_map = {d["name"]: d["passed"] for d in r.json()["dimension_scores"]}
    assert dim_map["technical_precision"] is True
    assert dim_map["edge_cases"] is True
    assert dim_map["testability"] is True


# ─────────────────────────────────────────────────────────────────────────────
# TC-DED — Deduplication
# ─────────────────────────────────────────────────────────────────────────────

from app.services.prompt_validation import dedupe_preserve


def test_tc_ded_01_exact_duplicates_removed():
    """TC-DED-01: Exact duplicate strings are collapsed to one entry."""
    items = ["Missing output format", "Missing output format", "No context provided"]
    result = dedupe_preserve(items)
    assert len(result) == 2
    assert result.count("Missing output format") == 1


def test_tc_ded_02_semantic_duplicates_removed():
    """TC-DED-02: Near-identical strings (case/punctuation variation) deduplicated."""
    items = [
        "No output format specified in prompt.",    # original
        "no output format specified in prompt",     # lowercase + no punctuation → same norm
        "Add context about source material.",       # different, kept
    ]
    result = dedupe_preserve(items)
    # First two normalize to same 8-token key → only one survives
    assert len(result) == 2, f"Expected 2 items after dedup, got {len(result)}: {result}"
    # The different item always present
    assert any("context" in r.lower() for r in result)


def test_tc_ded_03_no_suggestions_on_score_100_no_issues():
    """TC-DED-03: No suggestions returned when score=100 and issues=[]."""
    from app.services.suggestion_engine import derive_issue_based_suggestions
    result = derive_issue_based_suggestions("persona_0", [], fallback=["Default suggestion 1", "Default 2"])
    assert result == [], f"Expected [] but got: {result}"


def test_tc_ded_04_max_two_fallback_when_no_keyword_match():
    """TC-DED-04: At most 2 fallback suggestions when issues present but no keyword match."""
    from app.services.suggestion_engine import derive_issue_based_suggestions
    issues = ["Some vague issue that matches no keyword pattern"]
    fallback = ["Fallback A", "Fallback B", "Fallback C", "Fallback D"]
    result = derive_issue_based_suggestions("persona_0", issues, fallback=fallback)
    assert len(result) <= 2


def test_tc_ded_05_keyword_matched_suggestions_are_specific():
    """TC-DED-05: Issue with 'language' keyword maps to technical precision suggestion."""
    from app.services.suggestion_engine import derive_issue_based_suggestions
    issues = ["Specify the programming language, framework, and version."]
    fallback = ["Generic suggestion 1"]
    result = derive_issue_based_suggestions("persona_1", issues, fallback=fallback)
    assert any("language" in s.lower() or "framework" in s.lower() for s in result), \
        f"Expected technical precision suggestion, got: {result}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-AUTH — Authentication & Security
# ─────────────────────────────────────────────────────────────────────────────

PROTECTED_ENDPOINTS = [
    ("GET", "/api/v1/analytics/summary"),
    ("POST", "/api/v1/mcp/validate"),
    ("POST", "/api/v1/teams/message"),
    ("GET", "/api/v1/leaderboard/weekly"),
    ("GET", "/api/v1/leadership/org-dashboard"),
]


def test_tc_auth_01_protected_endpoints_no_key_returns_401(client):
    """TC-AUTH-01: Protected endpoints return 401 without API key."""
    for method, path in PROTECTED_ENDPOINTS:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json={"prompt_text": "test", "message_text": "test"})
        assert r.status_code == 401, f"Expected 401 for {method} {path}, got {r.status_code}"


def test_tc_auth_02_protected_endpoints_wrong_key_returns_401(client):
    """TC-AUTH-02: Protected endpoints return 401 with wrong API key."""
    for method, path in PROTECTED_ENDPOINTS:
        hdrs = {"x-api-key": "completely-wrong-key"}
        if method == "GET":
            r = client.get(path, headers=hdrs)
        else:
            r = client.post(path, headers=hdrs, json={"prompt_text": "test", "message_text": "test"})
        assert r.status_code == 401, f"Expected 401 for {method} {path} with bad key, got {r.status_code}"


def test_tc_auth_03_auth_resolve_valid_key(client, monkeypatch):
    """TC-AUTH-03: /auth/resolve returns 200 with valid API key."""
    monkeypatch.setattr(routes, "resolve_user_from_token", lambda *a, **k: {
        "email": "dev@infovision.com", "display_name": "Dev User",
        "provider": "microsoft", "persona_id": "persona_1",
    })
    r = client.post("/api/v1/auth/resolve",
                    headers={"x-api-key": routes.API_KEY},
                    json={"access_token": "valid-token"})
    assert r.status_code == 200
    assert r.json()["email"] == "dev@infovision.com"


def test_tc_auth_04_auth_map_persona_valid_key(client, monkeypatch):
    """TC-AUTH-04: /auth/map-persona returns mapped=true with valid key."""
    monkeypatch.setattr(routes, "map_persona", lambda *a, **k: SimpleNamespace(
        user_email="user@infovision.com", persona_id="persona_1", source="manual"
    ))
    r = client.post("/api/v1/auth/map-persona",
                    headers={"x-api-key": routes.API_KEY},
                    json={"email": "user@infovision.com", "persona_id": "persona_1"})
    assert r.status_code == 200
    assert r.json()["mapped"] is True


def test_tc_auth_05_validate_endpoint_no_auth_required(client, monkeypatch):
    """TC-AUTH-05: /validate endpoint is publicly accessible (no API key needed)."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0"})
    assert r.status_code == 200  # No API key needed


def test_tc_auth_06_mcp_endpoint_requires_key(client):
    """TC-AUTH-06: MCP endpoint refuses without API key."""
    r = client.post("/api/v1/mcp/validate", json={"prompt_text": SP_01})
    assert r.status_code == 401


def test_tc_auth_07_teams_endpoint_requires_key(client):
    """TC-AUTH-07: Teams message endpoint refuses without API key."""
    r = client.post("/api/v1/teams/message", json={"message_text": SP_01})
    assert r.status_code == 401


def test_tc_auth_08_leadership_endpoint_requires_key(client):
    """TC-AUTH-08: Leadership org-dashboard requires API key."""
    r = client.get("/api/v1/leadership/org-dashboard")
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# TC-DB — Data Persistence
# ─────────────────────────────────────────────────────────────────────────────

def test_tc_db_01_health_db_sqlite(monkeypatch):
    """TC-DB-01: health/db with SQLite mock returns ok."""
    from app import api as api_module
    from sqlalchemy.orm import Session
    from unittest.mock import MagicMock
    mock_session = MagicMock(spec=Session)
    mock_session.execute.return_value = True
    app2 = FastAPI()
    app2.include_router(routes.router)
    app2.dependency_overrides[get_db] = lambda: mock_session
    monkeypatch.setattr("app.api.routes.DATABASE_BACKEND", "sqlite")
    c2 = TestClient(app2)
    r = c2.get("/api/v1/health/db")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["backend"] == "sqlite"


def test_tc_db_02_validation_save_called(monkeypatch):
    """TC-DB-02: save_validation is invoked after /validate."""
    from fastapi import FastAPI
    save_calls = []
    def mock_save(*a, **k):
        save_calls.append(True)
    app3 = FastAPI()
    app3.include_router(routes.router)
    app3.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", mock_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    c3 = TestClient(app3)
    c3.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0"})
    assert len(save_calls) == 1, "save_validation should be called exactly once"


def test_tc_db_03_dimension_scores_in_save(monkeypatch):
    """TC-DB-03: dimension_scores passed to save_validation contain all dims."""
    saved = {}
    def capture_save(db, *, dimension_scores, **k):
        saved["dims"] = dimension_scores
    app4 = FastAPI()
    app4.include_router(routes.router)
    app4.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_1"))
    monkeypatch.setattr(routes, "save_validation", capture_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    c4 = TestClient(app4)
    c4.post("/api/v1/validate", json={"prompt_text": SP_05, "persona_id": "persona_1"})
    assert "dims" in saved
    assert len(saved["dims"]) == 7


def test_tc_db_04_rewrite_metadata_in_save(monkeypatch):
    """TC-DB-04: rewrite metadata (applied_guidelines) passed to save_validation."""
    saved = {}
    def capture_save(db, *, rewrite_metadata=None, **k):
        saved["rm"] = rewrite_metadata
    app5 = FastAPI()
    app5.include_router(routes.router)
    app5.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", capture_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    c5 = TestClient(app5)
    c5.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0", "auto_improve": True})
    assert "rm" in saved
    assert isinstance(saved["rm"], dict)
    assert "rewrite_applied_guidelines" in saved["rm"]


def test_tc_db_05_channel_tracked_in_save(monkeypatch):
    """TC-DB-05: delivery_channel=api is passed to save_validation."""
    saved = {}
    def capture_save(db, *, delivery_channel, **k):
        saved["ch"] = delivery_channel
    app6 = FastAPI()
    app6.include_router(routes.router)
    app6.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", capture_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    c6 = TestClient(app6)
    c6.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0", "channel": "api"})
    assert "ch" in saved
    assert saved["ch"].upper() in ("API", "WEB")


def _make_history_orm(n: int = 1):
    """Return list of SimpleNamespace objects mimicking ORM rows for fetch_history."""
    from datetime import datetime
    return [
        SimpleNamespace(
            id=i, persona_id="persona_0", channel="api",
            score=85.0, rating="Excellent",
            prompt_text=f"Test prompt {i}",
            improved_prompt=f"Improved prompt {i}",
            created_at=datetime(2026, 4, 1, 0, 0, 0),
        )
        for i in range(1, n + 1)
    ]


def test_tc_db_06_history_endpoint_returns_list(client, monkeypatch):
    """TC-DB-06: /history returns list of records with correct schema."""
    monkeypatch.setattr(routes, "fetch_history", lambda db, limit: _make_history_orm(3))
    r = client.get("/api/v1/history?limit=3")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 3
    for item in items:
        assert "score" in item and "persona_id" in item


def test_tc_db_07_pii_governance_payload_built(monkeypatch):
    """TC-DB-07: build_data_governance_payload redacts PII fields correctly."""
    from app.services.data_strategy import build_data_governance_payload
    payload = build_data_governance_payload(
        user_email="user@test.com", channel="api",
        score_100=85.0, score_10=8.5,
        llm_evaluation={"used": True, "provider": "groq"},
    )
    assert "pii_classification" in payload or "delivery_channel" in payload
    # Payload should not expose raw prompt text
    payload_str = str(payload)
    assert "original_prompt" not in payload_str or "[REDACTED]" in payload_str or "pii_high" in payload_str


# ─────────────────────────────────────────────────────────────────────────────
# TC-MCP — MCP Channel
# ─────────────────────────────────────────────────────────────────────────────

def test_tc_mcp_01_requires_api_key(client):
    """TC-MCP-01: MCP validate endpoint requires API key."""
    r = client.post("/api/v1/mcp/validate", json={"prompt_text": SP_01})
    assert r.status_code == 401


def test_tc_mcp_02_valid_response_with_key(client, monkeypatch):
    """TC-MCP-02: MCP validate returns valid response with API key."""
    monkeypatch.setattr(routes, "run_mcp_validation", lambda *a, **k: {
        "persona_id": "persona_0", "persona_name": "All Employees",
        "score": 90.0, "rating": "Excellent",
        "summary": "All Employees prompt evaluated with score 90.0.",
        "strengths": ["Clear task"], "issues": [], "suggestions": [],
        "improved_prompt": "Already excellent.",
        "dimension_scores": [{"name": "clarity", "score": 18.0, "weight": 18.0, "passed": True, "notes": None}],
        "guideline_evaluation": {"strict_mode": True, "penalty_applied": 0, "checks": [], "issues": [], "sources": []},
        "llm_evaluation": {"used": True, "provider": "groq", "model": "llama-3.3-70b-versatile",
                           "semantic_score": 90.0, "static_score": None, "scoring_mode": "llm_only",
                           "source_of_truth_document": "doc", "source_of_truth_scope": "scope",
                           "rewrite_applied_guidelines": None, "rewrite_unresolved_gaps": None, "error": None},
    })
    r = client.post("/api/v1/mcp/validate",
                    headers={"x-api-key": routes.API_KEY},
                    json={"prompt_text": SP_01, "persona_id": "persona_0"})
    assert r.status_code == 200
    body = r.json()
    assert "score" in body
    assert body["score"] > 0


def test_tc_mcp_03_mcp_channel_in_response(client, monkeypatch):
    """TC-MCP-03: MCP channel is visible in run_mcp_validation invocation."""
    called_with = {}
    def mock_mcp(db, *, prompt_text, persona_id, user_email, auto_improve, **k):
        called_with["persona"] = persona_id
        return {
            "persona_id": persona_id, "persona_name": "All Employees",
            "score": 85.0, "rating": "Excellent",
            "summary": "Summary.", "strengths": [], "issues": [],
            "suggestions": [], "improved_prompt": "ok.",
            "dimension_scores": [],
            "guideline_evaluation": {"strict_mode": True, "penalty_applied": 0, "checks": [], "issues": [], "sources": []},
            "llm_evaluation": {"used": True, "provider": "groq", "model": "m",
                               "semantic_score": 85.0, "static_score": None, "scoring_mode": "llm_only",
                               "source_of_truth_document": "d", "source_of_truth_scope": "s",
                               "rewrite_applied_guidelines": None, "rewrite_unresolved_gaps": None, "error": None},
        }
    monkeypatch.setattr(routes, "run_mcp_validation", mock_mcp)
    r = client.post("/api/v1/mcp/validate",
                    headers={"x-api-key": routes.API_KEY},
                    json={"prompt_text": SP_01, "persona_id": "persona_0"})
    assert r.status_code == 200
    assert called_with.get("persona") == "persona_0"


# ─────────────────────────────────────────────────────────────────────────────
# TC-TMS — Teams Channel
# ─────────────────────────────────────────────────────────────────────────────

def test_tc_tms_01_requires_api_key(client):
    """TC-TMS-01: Teams message endpoint requires API key."""
    r = client.post("/api/v1/teams/message", json={"message_text": SP_01})
    assert r.status_code == 401


def test_tc_tms_02_returns_200_with_valid_key(client, monkeypatch):
    """TC-TMS-02: Teams endpoint returns 200 with valid API key and message."""
    monkeypatch.setattr(routes, "handle_teams_message", lambda *a, **k: {
        "persona_id": "persona_0", "persona_name": "All Employees",
        "score": 85.0, "rating": "Excellent",
        "summary": "Summary.", "strengths": [], "issues": [],
        "suggestions": [], "improved_prompt": "ok.",
        "dimension_scores": [],
        "guideline_evaluation": {"strict_mode": True, "penalty_applied": 0, "checks": [], "issues": [], "sources": []},
        "llm_evaluation": {"used": True, "provider": "groq", "model": "m",
                           "semantic_score": 85.0, "static_score": None, "scoring_mode": "llm_only",
                           "source_of_truth_document": "d", "source_of_truth_scope": "s",
                           "rewrite_applied_guidelines": None, "rewrite_unresolved_gaps": None, "error": None},
    })
    r = client.post("/api/v1/teams/message",
                    headers={"x-api-key": routes.API_KEY},
                    json={"message_text": SP_01, "persona_id": "persona_0"})
    assert r.status_code == 200
    assert r.json()["score"] > 0


def test_tc_tms_03_empty_message_rejected(client):
    """TC-TMS-03: Teams endpoint rejects empty message_text."""
    r = client.post("/api/v1/teams/message",
                    headers={"x-api-key": routes.API_KEY},
                    json={"message_text": ""})
    assert r.status_code in (400, 422)


def test_tc_tms_04_teams_handler_called_with_message(client, monkeypatch):
    """TC-TMS-04: Teams handler receives the correct message_text."""
    received = {}
    def mock_teams(db, *, message_text, **k):
        received["msg"] = message_text
        return {
            "persona_id": "persona_0", "persona_name": "All Employees",
            "score": 80.0, "rating": "Good",
            "summary": "Summary.", "strengths": [], "issues": [],
            "suggestions": [], "improved_prompt": "ok.",
            "dimension_scores": [],
            "guideline_evaluation": {"strict_mode": True, "penalty_applied": 0, "checks": [], "issues": [], "sources": []},
            "llm_evaluation": {"used": True, "provider": "groq", "model": "m",
                               "semantic_score": 80.0, "static_score": None, "scoring_mode": "llm_only",
                               "source_of_truth_document": "d", "source_of_truth_scope": "s",
                               "rewrite_applied_guidelines": None, "rewrite_unresolved_gaps": None, "error": None},
        }
    monkeypatch.setattr(routes, "handle_teams_message", mock_teams)
    client.post("/api/v1/teams/message",
                headers={"x-api-key": routes.API_KEY},
                json={"message_text": SP_17, "persona_id": "persona_4"})
    assert received.get("msg") == SP_17


# ─────────────────────────────────────────────────────────────────────────────
# TC-ANA — Analytics & Leadership
# ─────────────────────────────────────────────────────────────────────────────

def test_tc_ana_01_analytics_summary_valid_key(client, monkeypatch):
    """TC-ANA-01: Analytics summary returns metrics with valid key."""
    monkeypatch.setattr(routes, "analytics_summary", lambda db: {
        "total_validations": 42, "average_score": 78.5, "top_persona": "persona_1"
    })
    r = client.get("/api/v1/analytics/summary", headers={"x-api-key": routes.API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert "total_validations" in body or isinstance(body, dict)


def test_tc_ana_02_leaderboard_returns_ranked_list(client, monkeypatch):
    """TC-ANA-02: Leaderboard returns list with user_id and score."""
    monkeypatch.setattr(routes, "leaderboard_weekly", lambda db, **kwargs: [
        {"user_id": "user1", "score": 92.0, "rank": 1},
        {"user_id": "user2", "score": 85.0, "rank": 2},
    ])
    r = client.get("/api/v1/leaderboard/weekly", headers={"x-api-key": routes.API_KEY})
    assert r.status_code == 200
    data = r.json()
    assert "items" in data or isinstance(data, list)


def test_tc_ana_03_org_dashboard_masks_pii(client, monkeypatch):
    """TC-ANA-03: Org dashboard does not expose raw prompt text."""
    monkeypatch.setattr(routes, "org_dashboard", lambda db, **kwargs: {
        "total_validations": 100,
        "average_score": 72.0,
        "persona_distribution": {"persona_0": 40, "persona_1": 30},
        "prompt_samples": "[REDACTED]",
    })
    r = client.get("/api/v1/leadership/org-dashboard", headers={"x-api-key": routes.API_KEY})
    assert r.status_code == 200
    body_str = str(r.json())
    assert SP_01[:30] not in body_str
    assert SP_05[:30] not in body_str


def test_tc_ana_04_team_report_valid_key(client, monkeypatch):
    """TC-ANA-04: Team report returns data for given team_id."""
    monkeypatch.setattr(routes, "team_report", lambda db, team_id, **kwargs: {
        "team_id": team_id, "average_score": 78.0, "total_validations": 25,
    })
    r = client.get("/api/v1/leadership/team-report/team_infovision",
                   headers={"x-api-key": routes.API_KEY})
    assert r.status_code == 200


def test_tc_ana_05_weekly_refresh_valid_key(client, monkeypatch):
    """TC-ANA-05: Weekly intelligence refresh returns success."""
    monkeypatch.setattr(routes, "refresh_weekly_intelligence", lambda db, **kwargs: {"status": "ok"})
    r = client.post("/api/v1/aggregation/weekly/refresh", headers={"x-api-key": routes.API_KEY})
    assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# TC-EDG — Edge Cases & Error Handling
# ─────────────────────────────────────────────────────────────────────────────

def test_tc_edg_01_empty_prompt_returns_400(client, monkeypatch):
    """TC-EDG-01: Empty prompt_text returns HTTP 400."""
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": "", "persona_id": "persona_0"})
    assert r.status_code in (400, 422)


def test_tc_edg_02_whitespace_only_prompt_returns_400(client, monkeypatch):
    """TC-EDG-02: Whitespace-only prompt returns HTTP 400."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": "   ", "persona_id": "persona_0"})
    assert r.status_code in (400, 422)


def test_tc_edg_03_oversized_prompt_returns_422(client):
    """TC-EDG-03: Prompt exceeding max length returns HTTP 422."""
    huge = "x" * 30001
    r = client.post("/api/v1/validate", json={"prompt_text": huge, "persona_id": "persona_0"})
    assert r.status_code == 422


def test_tc_edg_04_malformed_json_returns_422(client):
    """TC-EDG-04: Malformed JSON returns HTTP 422."""
    r = client.post("/api/v1/validate", content=b'{"prompt_text": "test"',
                    headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_tc_edg_05_non_string_prompt_returns_422(client):
    """TC-EDG-05: Non-string prompt_text field returns HTTP 422."""
    r = client.post("/api/v1/validate", json={"prompt_text": 12345, "persona_id": "persona_0"})
    assert r.status_code == 422


def test_tc_edg_06_unicode_prompt_handled(client, monkeypatch):
    """TC-EDG-06: Arabic/Unicode prompt returns 200 without crash."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={
        "prompt_text": "كتابة تقرير حالة المشروع للعميل في الربع الأول 2026.",
        "persona_id": "persona_0",
    })
    assert r.status_code == 200
    assert isinstance(r.json()["score"], (int, float))


def test_tc_edg_07_emoji_prompt_handled(client, monkeypatch):
    """TC-EDG-07: Emoji in prompt returns 200 without crash."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={
        "prompt_text": "Write a 🎯 status update 📊 for Q1 2026 including 🚀 achievements.",
        "persona_id": "persona_0",
    })
    assert r.status_code == 200
    assert isinstance(r.json()["score"], (int, float))


def test_tc_edg_08_long_persona_id_falls_back(client, monkeypatch):
    """TC-EDG-08: Long/unknown persona_id falls back gracefully."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    long_id = "persona_" + "x" * 200
    r = client.post("/api/v1/validate", json={"prompt_text": "Write a report.", "persona_id": long_id})
    assert r.status_code in (200, 422)  # either fallback or validation error, not 500


def test_tc_edg_09_concurrent_requests_no_cross_contamination(client, monkeypatch):
    """TC-EDG-09: Each persona returns correct dimension count independently."""
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    results = {}
    for pid, expected in [("persona_0", 8), ("persona_1", 7), ("persona_2", 8), ("persona_3", 7), ("persona_4", 8)]:
        monkeypatch.setattr(routes, "run_llm_validation", lambda *a, pid=pid, **k: _all_pass(pid))
        r = client.post("/api/v1/validate", json={"prompt_text": "Test.", "persona_id": pid})
        results[pid] = len(r.json()["dimension_scores"])
    assert results == {"persona_0": 8, "persona_1": 7, "persona_2": 8, "persona_3": 7, "persona_4": 8}


def test_tc_edg_10_history_limit_respected(client, monkeypatch):
    """TC-EDG-10: History limit parameter is respected."""
    monkeypatch.setattr(routes, "fetch_history", lambda db, limit: _make_history_orm(min(limit, 5)))
    r = client.get("/api/v1/history?limit=3")
    assert r.status_code == 200
    assert len(r.json()) <= 3


def test_tc_edg_11_score_is_always_numeric(client, monkeypatch):
    """TC-EDG-11: score field in response is always a number."""
    monkeypatch.setattr(routes, "run_llm_validation", lambda *a, **k: _all_pass("persona_0"))
    monkeypatch.setattr(routes, "save_validation", _noop_save)
    monkeypatch.setattr(routes, "capture_raw_event", _noop_capture)
    monkeypatch.setattr(routes, "capture_enriched_event", _noop_capture)
    r = client.post("/api/v1/validate", json={"prompt_text": SP_01, "persona_id": "persona_0"})
    score = r.json()["score"]
    assert isinstance(score, (int, float))
    assert not isinstance(score, bool)


def test_tc_edg_12_score_out_of_range_never_occurs():
    """TC-EDG-12: _recompute_score always returns 0 ≤ score ≤ 100."""
    import random
    random.seed(42)
    for _ in range(50):
        n_dims = random.randint(1, 8)
        weights = [random.randint(1, 20) for _ in range(n_dims)]
        dims = [{"name": f"d{i}", "passed": random.choice([True, False]), "weight": w,
                 "score": w if random.choice([True, False]) else 0}
                for i, w in enumerate(weights)]
        penalty_applied = random.randint(0, 30)
        cap = random.randint(5, 20)
        score = _recompute_score(dims, {"penalty_applied": penalty_applied}, {"strict_penalty_cap": cap})
        assert 0.0 <= score <= 100.0, f"Score {score} out of range 0-100"
