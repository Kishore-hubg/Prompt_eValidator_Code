"""
Demo sample prompts for the web UI: 5 personas × 3 quality tiers = 15 prompts.

UI tier → target score band (Option C — aligns with ``rating_for_score`` in ``routes``):

- **poor** → score < 50 → rating **Poor**
- **medium** → score 50–69 → rating **Needs Improvement**
- **excellent** → score ≥ 85 → rating **Excellent**

The **Good** band (70–84) is not represented by a sample tier. LLM variance means
scores are not guaranteed to fall inside these bands for every run.
"""

from __future__ import annotations

from typing import Any

# Aliases aligned with UI labels (lowercase keys).
QUALITY_POOR = "poor"
QUALITY_MEDIUM = "medium"
QUALITY_EXCELLENT = "excellent"

_VALID_QUALITIES = frozenset({QUALITY_POOR, QUALITY_MEDIUM, QUALITY_EXCELLENT})
_VALID_PERSONAS = frozenset({f"persona_{i}" for i in range(5)})

# Option C: medium prompts are intentionally incomplete vs. excellent (missing tests,
# grounding, SLA/policy cites, structure) but more actionable than poor one-liners.

TIER_SCORE_BANDS: dict[str, Any] = {
    QUALITY_POOR: {
        "score_max_exclusive": 50,
        "rating": "Poor",
        "summary": "Target band: score below 50",
    },
    QUALITY_MEDIUM: {
        "score_min_inclusive": 50,
        "score_max_inclusive": 69,
        "rating": "Needs Improvement",
        "summary": "Target band: score 50–69",
    },
    QUALITY_EXCELLENT: {
        "score_min_inclusive": 85,
        "rating": "Excellent",
        "summary": "Target band: score 85 or above",
    },
    "uncovered_band_note": (
        "Ratings in the Good band (scores 70–84) are not mapped to a sample tier."
    ),
}

_DEMO_SAMPLES: dict[str, dict[str, str]] = {
    "persona_0": {
        QUALITY_EXCELLENT: (
            "Write a professional email to the BFSI client at Ziply Telecom summarising "
            "the outcomes of our Sprint 14 review meeting held on 28 March 2026. "
            "The audience is the client's VP of Finance and Project Sponsor. "
            "Structure the email as: (1) Opening with meeting reference, "
            "(2) Key decisions made (bullet list), (3) Risks identified with owner names, "
            "(4) Next steps with due dates. Tone should be formal and concise. "
            "Maximum 350 words. Do not include internal Slack references or pricing details."
        ),
        QUALITY_MEDIUM: (
            "Summarize the Q4-2025 revenue highlights from the earnings report in bullet points "
            "for leadership. Use a professional tone. "
            "Include at least one figure or trend if mentioned in the source."
        ),
        QUALITY_POOR: "Help me write something for a client.",
    },
    "persona_1": {
        QUALITY_EXCELLENT: (
            "Using Python 3.12 and FastAPI 0.115+, implement a POST /api/v1/validate endpoint "
            "that accepts a JSON body with fields: prompt (str, required, max 2000 chars), "
            "persona_id (str, enum: persona_0 to persona_4), and auto_improve (bool, default false). "
            "Validate input using Pydantic v2 BaseModel. Return HTTP 422 for invalid input. "
            "Apply OWASP Top 10 input sanitisation — specifically prevent prompt injection and XSS. "
            "Include edge cases: empty prompt string, prompt exceeding 2000 chars, invalid persona_id. "
            "Write pytest unit tests for each edge case using FastAPI TestClient. "
            "Expected test format: TC-ID | Preconditions | Steps | Expected Result."
        ),
        QUALITY_MEDIUM: (
            "Using FastAPI and Pydantic v2, add a POST /api/v1/validate route that accepts "
            "JSON with prompt, persona_id, and auto_improve. Return 422 on bad input. "
            "Show the route and Pydantic model in one code block."
        ),
        QUALITY_POOR: "Write some code to validate a prompt.",
    },
    "persona_2": {
        QUALITY_EXCELLENT: (
            "Generate a Sprint 14 status report for the Ziply Telecom Finance Modernisation "
            "engagement (T&M model, 8-week sprint). Reporting period: 17–28 March 2026. "
            "Audience: Delivery Manager and Client Project Sponsor. "
            "Structure: (1) Executive Summary (3 sentences max), (2) Completed vs Planned work "
            "table with RAG status, (3) Top 3 risks ranked by impact with owner and mitigation, "
            "(4) Next sprint commitments with due dates. "
            "Output as a structured Markdown report. Prioritise risks over achievements. "
            "Reference velocity data: 42 story points delivered vs 45 planned."
        ),
        QUALITY_MEDIUM: (
            "Write a Sprint 14 status update for the Ziply Finance project for the client "
            "sponsor. Cover what the team finished, the main risks, and what happens next. "
            "Use Markdown headings."
        ),
        QUALITY_POOR: "Give me an update on the project.",
    },
    "persona_3": {
        QUALITY_EXCELLENT: (
            "Based on Section 4.2 (Data Migration Requirements) of the Ziply Finance "
            "Modernisation BRD document (version 2.1, March 2026), extract all functional "
            "requirements related to GL Trial Balance data migration. For each requirement, "
            "output: Requirement ID | Requirement Text | Source Section | Acceptance Criteria "
            "(testable, using Given/When/Then format). Only use explicit statements from the "
            "document — do not infer or add requirements not present in Section 4.2. "
            "Prioritise using MoSCoW: Must Have vs Should Have. Audience: Delivery team leads."
        ),
        QUALITY_MEDIUM: (
            "Review the Ziply Finance Modernisation BRD and produce a bullet list of "
            "functional requirements related to GL Trial Balance migration. "
            "Add requirement IDs where you can. Audience: delivery team."
        ),
        QUALITY_POOR: "List the requirements for the project.",
    },
    "persona_4": {
        QUALITY_EXCELLENT: (
            "Write an empathetic customer-facing email response for a Ziply Telecom retail "
            "customer who has been double-charged on their invoice for February 2026. "
            "The customer is frustrated and has submitted ticket #TKT-20260315-0042. "
            "Tone: apologetic and empathetic. Comply with Ziply SLA policy (resolution within "
            "24 hours). Reference the refund policy under Section 3.1 of the Customer Billing "
            "Policy document. Output: formal email format with subject line, greeting, 3-paragraph "
            "body, and closing. Maximum 200 words. Next action: confirm refund initiation "
            "within 4 business hours."
        ),
        QUALITY_MEDIUM: (
            "Draft an email to a Ziply customer who was double-charged on their February invoice. "
            "Reference ticket #TKT-20260315-0042. Apologize and outline refund next steps in a "
            "professional tone. Aim for under 200 words."
        ),
        QUALITY_POOR: "Reply to an angry customer.",
    },
}


def normalize_quality(quality: str) -> str:
    q = (quality or "").strip().lower()
    if q in _VALID_QUALITIES:
        return q
    raise ValueError(f"Invalid quality: {quality!r}; expected one of {sorted(_VALID_QUALITIES)}")


def get_demo_sample(persona_id: str, quality: str) -> str:
    """Return prompt text for persona + quality tier."""
    pid = (persona_id or "").strip()
    if pid not in _VALID_PERSONAS:
        raise ValueError(f"Invalid persona_id: {persona_id!r}")
    q = normalize_quality(quality)
    return _DEMO_SAMPLES[pid][q]


def demo_samples_payload() -> dict[str, Any]:
    """Response body for GET /api/v1/demo-samples."""
    return {
        "qualities": [QUALITY_POOR, QUALITY_MEDIUM, QUALITY_EXCELLENT],
        "samples": {pid: dict(tiers) for pid, tiers in _DEMO_SAMPLES.items()},
        "count": len(_DEMO_SAMPLES) * len(_VALID_QUALITIES),
        "tier_score_bands": {
            QUALITY_POOR: TIER_SCORE_BANDS[QUALITY_POOR],
            QUALITY_MEDIUM: TIER_SCORE_BANDS[QUALITY_MEDIUM],
            QUALITY_EXCELLENT: TIER_SCORE_BANDS[QUALITY_EXCELLENT],
            "uncovered_band_note": TIER_SCORE_BANDS["uncovered_band_note"],
        },
    }
