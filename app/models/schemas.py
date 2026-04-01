from typing import List, Optional
from pydantic import BaseModel, Field

class ValidateRequest(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=30000)
    persona_id: str = Field(default="persona_0")
    channel: str = Field(default="web")
    user_email: Optional[str] = None
    audience: Optional[str] = None
    auto_improve: bool = True

class ScoreDimension(BaseModel):
    name: str
    score: float
    weight: float
    passed: bool
    notes: Optional[str] = None


class GuidelineCheckResult(BaseModel):
    id: str
    description: str
    passed: bool
    status: str
    message: str


class GuidelineSource(BaseModel):
    file_name: str
    file_path: str


class GuidelineEvaluation(BaseModel):
    strict_mode: bool
    penalty_applied: int
    checks: List[GuidelineCheckResult]
    issues: List[str]
    sources: List[GuidelineSource]


class LlmEvaluation(BaseModel):
    used: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    semantic_score: Optional[float] = None
    static_score: Optional[float] = None
    scoring_mode: Optional[str] = None
    source_of_truth_document: Optional[str] = None
    source_of_truth_scope: Optional[str] = None
    rewrite_applied_guidelines: Optional[List[str]] = None
    rewrite_unresolved_gaps: Optional[List[str]] = None
    error: Optional[str] = None


class ValidateResponse(BaseModel):
    persona_id: str
    persona_name: str
    score: float
    rating: str
    summary: str
    strengths: List[str]
    issues: List[str]
    suggestions: List[str]
    improved_prompt: str
    dimension_scores: List[ScoreDimension]
    guideline_evaluation: GuidelineEvaluation
    llm_evaluation: Optional[LlmEvaluation] = None

class PersonaSummary(BaseModel):
    id: str
    name: str
    description: str

class HistoryItem(BaseModel):
    id: int
    persona_id: str
    channel: str
    score: float
    rating: str
    prompt_text: str
    improved_prompt: str
    created_at: str


class PromptGuidelinesResponse(BaseModel):
    strict_mode: bool
    strict_penalty_per_miss: int
    strict_penalty_cap: int
    claude_friendly_mode: bool = True
    frontier_model_applicability: dict
    claude_curated_priorities: List[str]
    sources: List[GuidelineSource]
    global_checks: List[dict]


class PersonaMappingRequest(BaseModel):
    email: str
    persona_id: str
    source: str = "manual"


class PersonaMappingResponse(BaseModel):
    email: str
    persona_id: str
    source: str
    mapped: bool


class OAuthResolveRequest(BaseModel):
    access_token: str
    email_hint: Optional[str] = None


class OAuthResolveResponse(BaseModel):
    email: str
    display_name: str
    provider: str
    persona_id: str


class MCPValidateRequest(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=30000)
    persona_id: str = Field(default="persona_0")
    user_email: Optional[str] = None
    auto_improve: bool = True


class TeamsMessageRequest(BaseModel):
    user_email: Optional[str] = None
    message_text: str = Field(min_length=1, max_length=30000)
    persona_id: Optional[str] = None
    access_token: Optional[str] = None
    email_hint: Optional[str] = None
    teams_user_id: Optional[str] = None
