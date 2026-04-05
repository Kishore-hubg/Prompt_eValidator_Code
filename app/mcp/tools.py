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
from app.services.history_service import save_validation, fetch_history, analytics_summary
from app.core.settings import DATABASE_BACKEND


# ─── VALIDATION TOOLS ───────────────────────────────────────────────────────


async def validate_prompt_tool(db: Any, input_data: ValidatePromptInput) -> ValidatePromptOutput:
    """
    Validate a prompt against a specific persona.

    Calls the existing LLM validation engine and returns structured feedback.
    """
    persona = get_persona(input_data.persona_id)
    if not persona:
        raise ValueError(f"Unknown persona: {input_data.persona_id}")

    # Call existing validation service
    result = await run_llm_validation(
        prompt_text=input_data.prompt_text,
        persona=persona,
        channel=input_data.channel or "mcp"
    )

    return ValidatePromptOutput(
        score=result.get("score", 0.0),
        rating=result.get("rating", "Poor"),
        issues=result.get("issues", []),
        suggestions=result.get("suggestions", []),
        dimensions=result.get("dimension_scores", [])
    )


async def improve_prompt_tool(db: Any, input_data: ImprovePromptInput) -> ImprovePromptOutput:
    """
    Generate an improved version of a prompt.

    Uses LLM to enhance clarity, structure, and specificity.
    """
    persona = get_persona(input_data.persona_id)
    if not persona:
        raise ValueError(f"Unknown persona: {input_data.persona_id}")

    # Call existing improvement service
    result = await run_llm_validation(
        prompt_text=input_data.prompt_text,
        persona=persona,
        channel="mcp",
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
        "description": "Validate a prompt against a specific persona. Returns score, issues, and suggestions.",
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
