"""MCP Tool schemas for Prompt Validator.

Defines input/output schemas for all MCP tools exposed by the validator.
Used by Claude Code, Claude API, Teams bot, and other MCP clients.

CRITICAL: ValidatePromptOutput MUST match Web UI API ValidateResponse structure
to ensure consistency across all channels (MCP, REST, Slack, Teams, Web UI).
"""

from typing import Any, Optional, List
from pydantic import BaseModel, Field

# Import Web UI schemas to ensure sync
from app.models.schemas import ScoreDimension, GuidelineEvaluation, LlmEvaluation


# ─── VALIDATION TOOLS ───────────────────────────────────────────────────────


class ValidatePromptInput(BaseModel):
    """Input schema for validate_prompt tool."""
    prompt_text: str = Field(..., description="The prompt text to validate")
    persona_id: str = Field(
        default="persona_0",
        description="Target persona: persona_0 (All), persona_1 (Dev), persona_2 (PM), persona_3 (BA), persona_4 (Support)"
    )
    auto_improve: bool = Field(
        default=True,
        description="Also return an improved version of the prompt in the same response"
    )
    user_email: Optional[str] = Field(default=None, description="User email for tracking")
    channel: str = Field(default="api", description="Channel: slack, teams, api")


class ValidatePromptOutput(BaseModel):
    """Output schema for validate_prompt tool.

    ✅ FULLY SYNCED WITH Web UI API ValidateResponse.
    Ensures consistent response structure across MCP, REST, Slack, Teams, Web UI.
    """
    # Persona context
    persona_id: str = Field(description="Persona ID used for validation (e.g., 'persona_1')")
    persona_name: str = Field(description="Human-readable persona name (e.g., 'Developer & QA')")

    # Core validation results
    score: float = Field(description="Validation score on a 0-100 scale")
    rating: str = Field(description="Rating: Excellent (≥85), Good (70-84), Needs Improvement (50-69), Poor (<50)")
    summary: str = Field(description="One-line summary of validation result")

    # Feedback
    strengths: List[str] = Field(description="List of prompt strengths identified")
    issues: List[str] = Field(description="List of identified issues")
    suggestions: List[str] = Field(description="Improvement suggestions")

    # Improvements
    improved_prompt: str = Field(description="AI-improved version of the prompt")

    # Detailed scoring (synced with Web UI)
    dimension_scores: List[ScoreDimension] = Field(description="Dimension-by-dimension breakdown")
    guideline_evaluation: GuidelineEvaluation = Field(description="Guideline compliance check results")
    llm_evaluation: Optional[LlmEvaluation] = Field(
        default=None,
        description="LLM scoring diagnostics (provider, model, source-of-truth info)"
    )

    # MCP-specific bonus fields (not in Web UI but helpful for MCP clients)
    score_display: str = Field(description="Human-readable score string, e.g., '78.5 / 100'")
    formatted_report: str = Field(
        description="Pre-rendered Markdown report for direct display in MCP clients (Claude Desktop, etc.)"
    )


class ImprovePromptInput(BaseModel):
    """Input schema for improve_prompt tool."""
    prompt_text: str = Field(..., description="The prompt to improve")
    persona_id: str = Field(default="persona_0", description="Target persona")
    strategy: str = Field(
        default="template",
        description="Rewrite strategy: template, clarify, expand, simplify"
    )


class ImprovePromptOutput(BaseModel):
    """Output schema for improve_prompt tool."""
    improved_prompt: str = Field(description="The improved prompt text")
    changes: list[str] = Field(description="List of changes made")
    improvement_rationale: str = Field(description="Why these changes improve the prompt")


# ─── PERSONA TOOLS ──────────────────────────────────────────────────────────


class PersonaDetail(BaseModel):
    """Details of a single persona."""
    persona_id: str = Field(description="Persona ID")
    name: str = Field(description="Human-readable name")
    description: str = Field(description="Description of who this persona represents")
    keywords: list[str] = Field(description="Keywords this persona values")
    weights: dict[str, float] = Field(description="Dimension weight mappings")


class ListPersonasOutput(BaseModel):
    """Output schema for list_personas tool."""
    personas: list[PersonaDetail] = Field(description="Available personas")
    total: int = Field(description="Total persona count")


class GetPersonaDetailsInput(BaseModel):
    """Input schema for get_persona_details tool."""
    persona_id: str = Field(..., description="The persona ID to fetch details for")


# ─── HISTORY & ANALYTICS TOOLS ──────────────────────────────────────────────


class ValidationRecord(BaseModel):
    """A single validation record from history."""
    id: int = Field(description="Record ID")
    prompt_text: str = Field(description="Original prompt")
    score: float = Field(description="Validation score")
    rating: str = Field(description="Rating")
    persona_id: str = Field(description="Persona used")
    created_at: str = Field(description="Timestamp")
    user_email: Optional[str] = Field(description="User who created it")
    improved_prompt: Optional[str] = Field(description="If improved, the improved version")


class QueryHistoryInput(BaseModel):
    """Input schema for query_history tool."""
    user_email: Optional[str] = Field(default=None, description="Filter by user email")
    persona_id: Optional[str] = Field(default=None, description="Filter by persona")
    limit: int = Field(default=10, ge=1, le=100, description="Max records to return")


class QueryHistoryOutput(BaseModel):
    """Output schema for query_history tool."""
    records: list[ValidationRecord] = Field(description="Validation records")
    total: int = Field(description="Total records matching filter")


class GetAnalyticsInput(BaseModel):
    """Input schema for get_analytics tool."""
    time_period: str = Field(
        default="all",
        description="Time period: today, week, month, all"
    )


class AnalyticsOutput(BaseModel):
    """Output schema for get_analytics tool."""
    total_validations: int = Field(description="Total validations run")
    average_score: float = Field(description="Average validation score")
    validations_by_persona: dict[str, int] = Field(description="Counts per persona")
    validations_by_rating: dict[str, int] = Field(description="Counts per rating")
    trend: str = Field(description="Trend: improving, stable, declining")


# ─── SAVE VALIDATION TOOL ───────────────────────────────────────────────────


class SaveValidationInput(BaseModel):
    """Input schema for save_validation tool."""
    prompt_text: str = Field(..., description="The prompt that was validated")
    score: float = Field(..., description="Validation score (0.0-1.0)")
    rating: str = Field(..., description="Rating: Excellent, Good, Fair, Poor")
    persona_id: str = Field(..., description="Persona used for validation")
    user_email: Optional[str] = Field(default=None, description="User email")
    improved_prompt: Optional[str] = Field(default=None, description="Improved version if available")
    channel: str = Field(default="mcp", description="Channel: slack, teams, mcp, api")


class SaveValidationOutput(BaseModel):
    """Output schema for save_validation tool."""
    validation_id: int = Field(description="ID of the saved validation")
    created_at: str = Field(description="Timestamp of creation")
    status: str = Field(description="Status: saved")
