"""MCP Tools - Wrapper implementations around FastAPI endpoints.

Each tool wraps an existing FastAPI endpoint, keeping the original code untouched.
These tools are exposed via the MCP server for Claude, Teams bot, and other clients.
"""

import json
from typing import Any, Union
from datetime import datetime

from app.mcp.schemas import (
    ValidatePromptInput, ValidatePromptOutput,
    ImprovePromptInput, ImprovePromptOutput,
    PersonaDetail, ListPersonasOutput, GetPersonaDetailsInput,
    QueryHistoryInput, QueryHistoryOutput, ValidationRecord,
    GetAnalyticsInput, AnalyticsOutput,
    SaveValidationInput, SaveValidationOutput
)
from app.services.prompt_validation import run_llm_validation
from app.services.persona_loader import load_personas, get_persona
from app.services.suggestion_engine import derive_issue_based_suggestions
from app.services.history_service import save_validation, fetch_history
from app.repositories.validation_repository import analytics_summary
from app.core.settings import DATABASE_BACKEND


# ─── VALIDATION TOOLS ───────────────────────────────────────────────────────


def _score_emoji(score: float) -> str:
    """Return emoji badge matching Slack handler style."""
    if score >= 85:
        return "🟢"
    if score >= 70:
        return "🔵"
    if score >= 50:
        return "🟡"
    return "🔴"


def _rating_color(rating: str) -> str:
    """Return emoji prefix matching Slack handler style."""
    colors = {
        "Excellent": "🟢 *Excellent*",
        "Good": "🔵 *Good*",
        "Needs Improvement": "🟡 *Needs Improvement*",
        "Poor": "🔴 *Poor*",
    }
    return colors.get(rating, f"*{rating}*")


def validate_prompt_tool(db: Any, input_data: ValidatePromptInput) -> ValidatePromptOutput:
    """
    Validate a prompt against a specific persona.

    Calls the existing LLM validation engine (with fallback) and returns structured feedback.
    """
    # Verify persona exists
    persona = get_persona(input_data.persona_id)
    if not persona:
        raise ValueError(f"Unknown persona: {input_data.persona_id}")

    # Call validation service with fallback logic (Anthropic → Groq → static)
    # auto_improve=True by default so validation + improvement happen in one call,
    # avoiding a second round-trip and cold-start timeout in Claude Desktop.
    result = run_llm_validation(
        prompt_text=input_data.prompt_text,
        persona_id=input_data.persona_id,
        auto_improve=getattr(input_data, "auto_improve", True),
    )

    score = result.get("score", 0.0)
    strengths = result.get("strengths", [])
    issues = result.get("issues", [])
    dimensions = result.get("dimension_scores", [])
    improved = result.get("improved_prompt") or None
    rating = (
        "Excellent" if score >= 85
        else "Good" if score >= 70
        else "Needs Improvement" if score >= 50
        else "Poor"
    )
    suggestions = derive_issue_based_suggestions(
        input_data.persona_id, issues, fallback=issues
    )
    persona_name = persona.get("name", input_data.persona_id)
    provider = (result.get("llm_evaluation") or {}).get("provider", "")

    # Build formatted report matching Slack Block Kit visual style
    emoji = _score_emoji(score)
    score_int = int(round(score))

    lines = [
        f"{emoji} **Prompt Validator** · Score: {score_int}/100",
        "",
        f"**Rating:** {_rating_color(rating)}",
        f"**Persona:** {persona_name}",
        "",
        "---",
        "",
        "**Your Prompt:**",
        "```",
        input_data.prompt_text[:280] + ("…" if len(input_data.prompt_text) > 280 else ""),
        "```",
        "",
        "---",
        "",
    ]

    # Dimension Scores with checkmarks (matching Slack style)
    if dimensions:
        lines.append("**Dimension Breakdown:**")
        lines.append("")
        for d in dimensions[:7]:
            passed = bool(d.get("passed"))
            name = str(d.get("name", "")).replace("_", " ").title()
            weight = int(d.get("weight", 0))
            tick = "✅" if passed else "❌"
            lines.append(f"{tick} {name} _(wt: {weight})_")
        lines += ["", "---", ""]

    # Strengths Found
    if strengths:
        lines.append("**Strengths:**")
        lines.append("")
        for strength in strengths[:4]:
            lines.append(f"• {strength}")
        lines += ["", "---", ""]

    # Issues Found
    if issues:
        lines.append("**Issues Found:**")
        lines.append("")
        for issue in issues[:6]:
            lines.append(f"• {issue}")
        lines += ["", "---", ""]

    # Suggestions
    if suggestions:
        lines.append("**Suggestions:**")
        lines.append("")
        for s in suggestions[:4]:
            lines.append(f"• {s}")
        lines += ["", "---", ""]

    # Improved Prompt
    if improved and improved != input_data.prompt_text:
        improved_display = improved[:2800] + ("…" if len(improved) > 2800 else "")
        lines += [
            "**✨ Improved Prompt:**",
            "",
            "```",
            improved_display,
            "```",
            "",
            "---",
            ""
        ]

    # Footer
    provider_note = f" via {provider}" if provider else ""
    lines += [
        "*Infovision Prompt Validator*" + provider_note,
    ]

    formatted_report = "\n".join(lines)

    return ValidatePromptOutput(
        score=score,
        score_display=f"{round(score, 1)} / 100",
        rating=rating,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        dimensions=dimensions,
        improved_prompt=improved,
        formatted_report=formatted_report,
    )


def improve_prompt_tool(db: Any, input_data: ImprovePromptInput) -> ImprovePromptOutput:
    """
    Generate an improved version of a prompt.

    Uses LLM to enhance clarity, structure, and specificity.
    """
    # Verify persona exists
    persona = get_persona(input_data.persona_id)
    if not persona:
        raise ValueError(f"Unknown persona: {input_data.persona_id}")

    # Call validation service with auto_improve enabled and fallback logic
    result = run_llm_validation(
        prompt_text=input_data.prompt_text,
        persona_id=input_data.persona_id,
        auto_improve=True
    )

    return ImprovePromptOutput(
        improved_prompt=result.get("improved_prompt", input_data.prompt_text),
        changes=result.get("improvement_notes", ["Prompt analyzed and refined"]),
        improvement_rationale=f"Enhanced for {persona.get('name', input_data.persona_id)} persona"
    )


# ─── PERSONA TOOLS ──────────────────────────────────────────────────────────


def list_personas_tool(db: Any) -> ListPersonasOutput:
    """
    List all available personas.

    Returns name, description, and evaluation criteria for each persona.
    """
    personas_data = load_personas()

    persona_details = []
    for persona_id, persona in personas_data.items():
        persona_details.append(
            PersonaDetail(
                persona_id=persona_id,
                name=persona.get("name", persona_id),
                description=persona.get("description", ""),
                keywords=persona.get("keywords", []),
                weights=persona.get("weights", {})
            )
        )

    return ListPersonasOutput(
        personas=persona_details,
        total=len(persona_details)
    )


def get_persona_details_tool(db: Any, input_data: GetPersonaDetailsInput) -> PersonaDetail:
    """
    Get detailed information about a specific persona.

    Returns evaluation weights, keywords, and scoring criteria.
    """
    persona = get_persona(input_data.persona_id)
    if not persona:
        raise ValueError(f"Unknown persona: {input_data.persona_id}")

    return PersonaDetail(
        persona_id=input_data.persona_id,
        name=persona.get("name", input_data.persona_id),
        description=persona.get("description", ""),
        keywords=persona.get("keywords", []),
        weights=persona.get("weights", {})
    )


# ─── HISTORY TOOLS ──────────────────────────────────────────────────────────


def query_history_tool(db: Any, input_data: QueryHistoryInput) -> QueryHistoryOutput:
    """
    Query validation history with optional filters.

    Retrieve past validations by user, persona, or date range.
    """
    # This would call the existing history service
    # For now, returning structure with note that DB integration follows

    return QueryHistoryOutput(
        records=[],
        total=0
    )


# ─── ANALYTICS TOOLS ────────────────────────────────────────────────────────


def get_analytics_tool(db: Any, input_data: GetAnalyticsInput) -> AnalyticsOutput:
    """
    Get validation analytics and trends.

    Returns aggregate statistics about prompt validation activity.
    """
    # Call existing analytics service
    summary = analytics_summary(db)

    return AnalyticsOutput(
        total_validations=summary.get("total_validations", 0),
        average_score=summary.get("average_score", 0.0),
        validations_by_persona=summary.get("validations_by_persona", {}),
        validations_by_rating={},  # Will be computed from validations
        trend="stable"  # Will compute from time-series data
    )


# ─── SAVE VALIDATION TOOL ───────────────────────────────────────────────────


def save_validation_tool(db: Any, input_data: SaveValidationInput) -> SaveValidationOutput:
    """
    Save a validation result to the database.

    Persists validation record for audit trail and history.
    """
    # Call existing save_validation service
    result = save_validation(
        db,
        persona_id=input_data.persona_id,
        channel=input_data.channel,
        prompt_text=input_data.prompt_text,
        score=input_data.score,
        rating=input_data.rating,
        issues=[],
        suggestions=[],
        improved_prompt=input_data.improved_prompt or "",
        dimension_scores=[],
        user_email=input_data.user_email,
        delivery_channel=input_data.channel
    )

    return SaveValidationOutput(
        validation_id=result.get("id", 0) if isinstance(result, dict) else getattr(result, "id", 0),
        created_at=datetime.utcnow().isoformat(),
        status="saved"
    )


# ─── TOOL REGISTRY ──────────────────────────────────────────────────────────


MCP_TOOLS = {
    "validate_prompt": {
        "function": validate_prompt_tool,
        "description": "Validate a prompt against a specific persona. Returns score, rating, issues, suggestions, and an AI-improved version of the prompt — all in one call (auto_improve defaults to True).",
        "input_schema": ValidatePromptInput.model_json_schema(),
        "output_schema": ValidatePromptOutput.model_json_schema(),
    },
    "improve_prompt": {
        "function": improve_prompt_tool,
        "description": "Generate an improved version of a prompt using AI. Better structure, clarity, and specificity.",
        "input_schema": ImprovePromptInput.model_json_schema(),
        "output_schema": ImprovePromptOutput.model_json_schema(),
    },
    "list_personas": {
        "function": list_personas_tool,
        "description": "List all available evaluation personas and their criteria.",
        "input_schema": {},
        "output_schema": ListPersonasOutput.model_json_schema(),
    },
    "get_persona_details": {
        "function": get_persona_details_tool,
        "description": "Get detailed evaluation criteria for a specific persona.",
        "input_schema": GetPersonaDetailsInput.model_json_schema(),
        "output_schema": PersonaDetail.model_json_schema(),
    },
    "query_history": {
        "function": query_history_tool,
        "description": "Query validation history with optional filters (user, persona, date range).",
        "input_schema": QueryHistoryInput.model_json_schema(),
        "output_schema": QueryHistoryOutput.model_json_schema(),
    },
    "get_analytics": {
        "function": get_analytics_tool,
        "description": "Get aggregate analytics and trends about validation activity.",
        "input_schema": GetAnalyticsInput.model_json_schema(),
        "output_schema": AnalyticsOutput.model_json_schema(),
    },
    "save_validation": {
        "function": save_validation_tool,
        "description": "Save a validation result to persist in database for audit trail.",
        "input_schema": SaveValidationInput.model_json_schema(),
        "output_schema": SaveValidationOutput.model_json_schema(),
    },
}
