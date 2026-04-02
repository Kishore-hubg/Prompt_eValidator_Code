"""
Run all sample persona prompts through the validator and print scores.
Usage: python run_sample_prompts.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Use auto-provider so GROQ is used when Anthropic key is not configured.
os.environ.setdefault("LLM_PROVIDER", "auto")

from app.engines.validator_engine import validate

PROMPTS = [
    # ─────────────── PERSONA 0: All Employees ───────────────
    {
        "label": "P0-GOOD-1",
        "persona": "persona_0",
        "quality": "GOOD",
        "text": (
            "Summarize the Q4-2025 revenue highlights from the attached earnings report "
            "into 5 bullet points for a leadership presentation. Keep it under 100 words, "
            "professional tone."
        ),
    },
    {
        "label": "P0-GOOD-2",
        "persona": "persona_0",
        "quality": "GOOD",
        "text": (
            "Draft a company-wide email announcing the new hybrid work policy effective May 1st. "
            "Tone: positive and informative. Format: greeting, 3 key changes as bullets, "
            "FAQ link, sign-off from HR."
        ),
    },
    {
        "label": "P0-GOOD-3",
        "persona": "persona_0",
        "quality": "GOOD",
        "text": (
            "Extract the top 3 action items from yesterday's all-hands meeting notes (attached). "
            "Format as a numbered list with owner name and due date for each."
        ),
    },
    {
        "label": "P0-BAD-1",
        "persona": "persona_0",
        "quality": "BAD",
        "text": "Tell me about the report.",
    },
    {
        "label": "P0-BAD-2",
        "persona": "persona_0",
        "quality": "BAD",
        "text": "Help with email.",
    },
    {
        "label": "P0-BAD-3",
        "persona": "persona_0",
        "quality": "BAD",
        "text": "What should we do?",
    },

    # ─────────────── PERSONA 1: Developer + QA ───────────────
    {
        "label": "P1-GOOD-1",
        "persona": "persona_1",
        "quality": "GOOD",
        "text": (
            "Write a Python 3.11 FastAPI endpoint that accepts a JSON payload with fields "
            "{user_id: str, amount: float} and validates amount > 0. Use Pydantic v2 for "
            "validation. Return 422 for invalid input. Include edge cases for null values "
            "and negative amounts."
        ),
    },
    {
        "label": "P1-GOOD-2",
        "persona": "persona_1",
        "quality": "GOOD",
        "text": (
            "Refactor this Express 4 middleware (Node.js 20, TypeScript 5.x) to handle JWT "
            "token expiration gracefully. Current code throws unhandled 500. In scope: auth "
            "middleware only. Out of scope: user session management. Follow OWASP token "
            "handling guidelines."
        ),
    },
    {
        "label": "P1-GOOD-3",
        "persona": "persona_1",
        "quality": "GOOD",
        "text": (
            "Generate test cases for US-234 (user login with MFA). Cover: happy path, wrong OTP, "
            "expired OTP, 3 failed attempts lockout, session timeout after 15 min. "
            "Format: TC-ID | Preconditions | Steps | Expected Result | Priority (P1-P3)."
        ),
    },
    {
        "label": "P1-BAD-1",
        "persona": "persona_1",
        "quality": "BAD",
        "text": "Write me an API.",
    },
    {
        "label": "P1-BAD-2",
        "persona": "persona_1",
        "quality": "BAD",
        "text": "Test the login page.",
    },
    {
        "label": "P1-BAD-3",
        "persona": "persona_1",
        "quality": "BAD",
        "text": "Fix the bug in production.",
    },

    # ─────────────── PERSONA 2: Technical PM / PM ───────────────
    {
        "label": "P2-GOOD-1",
        "persona": "persona_2",
        "quality": "GOOD",
        "text": (
            "Generate a sprint summary for Sprint 14 (Team Phoenix, March 18–31). "
            "Velocity baseline: 42 points. Planned: 45 pts, Completed: 38 pts. "
            "Audience: client executive. Format: status section, velocity trend, "
            "top 3 risks with likelihood/impact, and next sprint focus areas."
        ),
    },
    {
        "label": "P2-GOOD-2",
        "persona": "persona_2",
        "quality": "GOOD",
        "text": (
            "Create a risk log for the Ziply data migration project. Engagement model: "
            "fixed bid, $2.1M budget. Include columns: Risk ID, Description, Likelihood (H/M/L), "
            "Impact (H/M/L), Mitigation, Owner, Status. Pre-populate with 5 common data "
            "migration risks."
        ),
    },
    {
        "label": "P2-GOOD-3",
        "persona": "persona_2",
        "quality": "GOOD",
        "text": (
            "Compare these two estimates for the API integration epic. Team A: 89 points "
            "(3 sprints, velocity 32). Team B: 72 points (2 sprints, velocity 40). "
            "Reference stories: US-101 (13 pts, completed), US-089 (8 pts, completed). "
            "Provide a recommendation table with risk assessment for each. Audience: delivery leadership."
        ),
    },
    {
        "label": "P2-BAD-1",
        "persona": "persona_2",
        "quality": "BAD",
        "text": "Give me a project update.",
    },
    {
        "label": "P2-BAD-2",
        "persona": "persona_2",
        "quality": "BAD",
        "text": "How is the project going?",
    },
    {
        "label": "P2-BAD-3",
        "persona": "persona_2",
        "quality": "BAD",
        "text": "Write an estimate for the new feature.",
    },

    # ─────────────── PERSONA 3: BA + PO ───────────────
    {
        "label": "P3-GOOD-1",
        "persona": "persona_3",
        "quality": "GOOD",
        "text": (
            "From the 'Ziply Network Ops SRS v2.3' (Section 4.2 — Alarm Management), extract all "
            "functional requirements. List only explicitly stated requirements — do not infer. "
            "Format: Req-ID | Requirement Text | Source Section. Add citation for each row."
        ),
    },
    {
        "label": "P3-GOOD-2",
        "persona": "persona_3",
        "quality": "GOOD",
        "text": (
            "Convert these 3 business requirements from the BRD (Section 5 — User Registration) "
            "into user stories for the development team. Format: As a [role], I want [action], "
            "so that [benefit]. Include 3-5 testable acceptance criteria per story. "
            "Prioritize using MoSCoW."
        ),
    },
    {
        "label": "P3-GOOD-3",
        "persona": "persona_3",
        "quality": "GOOD",
        "text": (
            "Create a product roadmap table for Q3-2026 features. Audience: executive stakeholders. "
            "Columns: Feature Name, Business Value (H/M/L), Effort (S/M/L/XL), Priority (MoSCoW), "
            "Target Sprint, Dependencies. Include 8 features from the attached backlog."
        ),
    },
    {
        "label": "P3-BAD-1",
        "persona": "persona_3",
        "quality": "BAD",
        "text": "Get me the requirements.",
    },
    {
        "label": "P3-BAD-2",
        "persona": "persona_3",
        "quality": "BAD",
        "text": "Write user stories.",
    },
    {
        "label": "P3-BAD-3",
        "persona": "persona_3",
        "quality": "BAD",
        "text": "Analyze the competition.",
    },

    # ─────────────── PERSONA 4: Support Staff ───────────────
    {
        "label": "P4-GOOD-1",
        "persona": "persona_4",
        "quality": "GOOD",
        "text": (
            "Draft an empathetic email reply to a Tier-2 customer whose refund was delayed by "
            "10 business days. Reference our 30-day refund policy (Policy #RF-201). "
            "Tone: apologetic and reassuring. Include: apology, current refund status, "
            "expected resolution date, direct contact for escalation."
        ),
    },
    {
        "label": "P4-GOOD-2",
        "persona": "persona_4",
        "quality": "GOOD",
        "text": (
            "Write a live chat response for a customer asking why their SLA Tier-1 ticket "
            "(4-hour response SLA) has been open for 6 hours with no update. "
            "Tone: firm but empathetic. Keep under 80 words. Acknowledge the breach, "
            "provide next steps, include escalation path."
        ),
    },
    {
        "label": "P4-GOOD-3",
        "persona": "persona_4",
        "quality": "GOOD",
        "text": (
            "Create an internal escalation note for Ticket #INC-4892. Customer tier: Enterprise. "
            "Issue: recurring API timeout errors (5 incidents in 7 days). "
            "Format: Ticket ID, Customer Tier, Issue Summary, Timeline of Incidents, "
            "Impact Assessment, Recommended Action. Tone: professional and factual."
        ),
    },
    {
        "label": "P4-BAD-1",
        "persona": "persona_4",
        "quality": "BAD",
        "text": "Reply to the customer.",
    },
    {
        "label": "P4-BAD-2",
        "persona": "persona_4",
        "quality": "BAD",
        "text": "Handle the complaint.",
    },
    {
        "label": "P4-BAD-3",
        "persona": "persona_4",
        "quality": "BAD",
        "text": "Write something for the angry customer.",
    },
]

RATING_EMOJI = {
    "Excellent": "🟢",
    "Good": "🟡",
    "Needs Improvement": "🟠",
    "Poor": "🔴",
}

def rating_for_score(score: float) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Needs Improvement"
    return "Poor"


def run_all():
    print("\n" + "=" * 80)
    print("  PROMPT VALIDATOR — SAMPLE PROMPTS SCORING REPORT")
    print("  Model: Anthropic Claude (claude-sonnet-4-6)")
    print("=" * 80)

    current_persona = None
    results_summary = []

    for item in PROMPTS:
        persona = item["persona"]
        label = item["label"]
        quality = item["quality"]
        text = item["text"]

        persona_names = {
            "persona_0": "All Employees",
            "persona_1": "Developer + QA",
            "persona_2": "Technical PM / PM",
            "persona_3": "Business Analyst + PO",
            "persona_4": "Support Staff",
        }

        if persona != current_persona:
            current_persona = persona
            print(f"\n{'─' * 80}")
            print(f"  PERSONA: {persona_names.get(persona, persona).upper()}")
            print(f"{'─' * 80}")

        tag = "✅ GOOD" if quality == "GOOD" else "❌ BAD "
        print(f"\n[{label}] {tag}")
        print(f"  Prompt: \"{text[:100]}{'...' if len(text) > 100 else ''}\"")
        print("  Validating...", end="", flush=True)

        try:
            result = validate(text, persona, auto_improve=False)
            score = round(result.get("score", 0), 1)
            rating = rating_for_score(score)
            emoji = RATING_EMOJI.get(rating, "")

            issues = result.get("issues", [])[:2]
            strengths = result.get("strengths", [])[:2]

            print(f"\r  Score: {score}/100  {emoji} {rating}")
            if strengths:
                print(f"  Strengths : {strengths[0]}")
            if issues:
                print(f"  Issue     : {issues[0]}")

            results_summary.append({
                "label": label,
                "quality": quality,
                "score": score,
                "rating": rating,
            })

        except Exception as e:
            print(f"\r  ERROR: {e}")
            results_summary.append({
                "label": label,
                "quality": quality,
                "score": "ERR",
                "rating": "Error",
            })

    # ── Summary Table ──────────────────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("  SUMMARY TABLE")
    print("=" * 80)
    print(f"  {'Label':<14} {'Quality':<8} {'Score':>7}  {'Rating':<22}")
    print(f"  {'─' * 14} {'─' * 8} {'─' * 7}  {'─' * 22}")

    current_p = None
    for r in results_summary:
        p = r["label"].split("-")[0]
        if p != current_p:
            current_p = p
            pname = {
                "P0": "All Employees",
                "P1": "Developer + QA",
                "P2": "Technical PM",
                "P3": "BA + PO",
                "P4": "Support Staff",
            }.get(p, p)
            print(f"\n  ── {pname} ──")

        emoji = RATING_EMOJI.get(r["rating"], "")
        tag = "✅" if r["quality"] == "GOOD" else "❌"
        score_str = f"{r['score']}/100" if r["score"] != "ERR" else "ERROR"
        print(f"  {r['label']:<14} {tag} {r['quality']:<6} {score_str:>8}  {emoji} {r['rating']}")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    run_all()
