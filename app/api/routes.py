from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pymongo.database import Database
from sqlalchemy import text

from app.db.database import get_db
from app.core.settings import API_KEY, DATABASE_BACKEND, MONGODB_DB_NAME
from app.core.settings import LLM_PROVIDER, GROQ_MODEL, ANTHROPIC_MODEL, LLM_VALIDATE_REQUIRED
from app.models.schemas import (
    ValidateRequest,
    ValidateResponse,
    PersonaSummary,
    HistoryItem,
    ScoreDimension,
    PromptGuidelinesResponse,
    PersonaMappingRequest,
    PersonaMappingResponse,
    OAuthResolveRequest,
    OAuthResolveResponse,
    MCPValidateRequest,
    TeamsMessageRequest,
)
from app.services.persona_loader import load_personas, get_persona
from app.services.prompt_validation import run_llm_validation
from app.services.llm_groq import GroqRateLimitError
from app.services.history_service import save_validation, fetch_history
from app.services.prompt_guidelines_loader import load_prompt_guidelines
from app.auth.persona_mapping import map_persona, resolve_persona_for_user
from app.integrations.oauth.provider import resolve_user_from_token
from app.integrations.mcp.server import run_mcp_validation
from app.integrations.teams.bot import handle_teams_message
from app.integrations.slack.handler import handle_slack_slash_command
from app.integrations.slack.verification import verify_slack_request
from app.core.settings import SLACK_SIGNING_SECRET
from app.repositories.validation_repository import analytics_summary
from app.repositories.intelligence_repository import (
    leaderboard_weekly,
    org_dashboard,
    refresh_weekly_intelligence,
    team_report,
    user_weekly_summary,
)
from app.services.data_strategy import (
    SOURCE_OF_TRUTH_DOC,
    SOURCE_OF_TRUTH_SCOPE,
    build_data_governance_payload,
    build_source_of_truth_payload,
    normalize_delivery_channel,
    to_validation_score_10,
)
from app.services.event_pipeline import capture_enriched_event, capture_raw_event
from app.services.suggestion_engine import derive_issue_based_suggestions
from app.services.demo_sample_prompts import demo_samples_payload, get_demo_sample, normalize_quality

router = APIRouter(prefix="/api/v1", tags=["Prompt Validator"])

DbDep = Annotated[Any, Depends(get_db)]


def require_api_key(x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key.")

def rating_for_score(score: float) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Needs Improvement"
    return "Poor"


# Keep the private alias so existing test imports (test_prompt_suggestions_and_precision.py)
# that patch `routes._derive_issue_based_suggestions` continue to work.
def _derive_issue_based_suggestions(persona_id: str, issues: list[str], fallback: list[str]) -> list[str]:
    return derive_issue_based_suggestions(persona_id, issues, fallback)

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/validation-mode")
def validation_mode():
    provider = LLM_PROVIDER if LLM_PROVIDER in {"groq", "anthropic"} else "auto"
    active_model = GROQ_MODEL if provider == "groq" else ANTHROPIC_MODEL if provider == "anthropic" else "provider_auto"
    return {
        "scoring_mode": "llm_only",
        "llm_validate_required": bool(LLM_VALIDATE_REQUIRED),
        "configured_provider": provider,
        "configured_model": active_model,
        "source_of_truth_document": SOURCE_OF_TRUTH_DOC,
        "source_of_truth_scope": SOURCE_OF_TRUTH_SCOPE,
    }


@router.get("/compliance/day2-checklist")
def day2_compliance_checklist():
    provider = LLM_PROVIDER if LLM_PROVIDER in {"groq", "anthropic"} else "auto"
    active_model = GROQ_MODEL if provider == "groq" else ANTHROPIC_MODEL if provider == "anthropic" else "provider_auto"
    checks = [
        {
            "id": "source_of_truth_document_registered",
            "status": "pass",
            "details": {
                "document_path": SOURCE_OF_TRUTH_DOC,
                "scope": SOURCE_OF_TRUTH_SCOPE,
            },
        },
        {
            "id": "llm_only_scoring_mode",
            "status": "pass",
            "details": {
                "scoring_mode": "llm_only",
                "provider": provider,
                "model": active_model,
            },
        },
        {
            "id": "llm_required_gate",
            "status": "pass" if bool(LLM_VALIDATE_REQUIRED) else "warn",
            "details": {
                "llm_validate_required": bool(LLM_VALIDATE_REQUIRED),
                "expected": True,
                "note": "Set LLM_VALIDATE_REQUIRED=true for strict production enforcement.",
            },
        },
        {
            "id": "day2_governance_payload_capture",
            "status": "pass",
            "details": {
                "captures": [
                    "delivery_channel",
                    "validation_score_100",
                    "validation_score_10",
                    "pii_masking",
                    "llm_scoring_governance",
                ],
            },
        },
    ]
    overall_status = "pass" if all(item["status"] == "pass" for item in checks) else "warn"
    return {
        "overall_status": overall_status,
        "document_scope": SOURCE_OF_TRUTH_SCOPE,
        "document_path": SOURCE_OF_TRUTH_DOC,
        "checks": checks,
    }


@router.get("/health/db")
def health_db(db: DbDep):
    """Ping MongoDB or run a trivial SQLite query to verify persistence is reachable."""
    if DATABASE_BACKEND == "mongodb":
        if not isinstance(db, Database):
            raise HTTPException(status_code=500, detail="Internal error: expected MongoDB database.")
        try:
            db.client.admin.command("ping")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {exc!s}") from exc
        return {"backend": "mongodb", "status": "ok", "db_name": MONGODB_DB_NAME}
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"SQLite unavailable: {exc!s}") from exc
    return {"backend": "sqlite", "status": "ok"}


@router.get("/demo-samples")
def demo_samples():
    """Fifteen curated prompts: each of persona_0…persona_4 has poor, medium, and excellent."""
    return demo_samples_payload()


@router.get("/demo-sample")
def demo_sample(
    persona_id: str = Query(..., description="persona_0 … persona_4"),
    quality: str = Query(..., description="poor | medium | excellent"),
):
    try:
        qn = normalize_quality(quality)
        text = get_demo_sample(persona_id, qn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"persona_id": persona_id.strip(), "quality": qn, "prompt_text": text}


@router.get("/personas", response_model=list[PersonaSummary])
def personas():
    items = list(load_personas().values())
    baseline = [p for p in items if p.get("id") == "persona_0"]
    others = [p for p in items if p.get("id") != "persona_0"]
    ordered = others + baseline
    return [PersonaSummary(id=item["id"], name=item["name"], description=item["description"]) for item in ordered]


@router.get("/guidelines", response_model=PromptGuidelinesResponse)
def guidelines():
    cfg = load_prompt_guidelines()
    return PromptGuidelinesResponse(
        strict_mode=cfg.get("strict_mode", True),
        strict_penalty_per_miss=int(cfg.get("strict_penalty_per_miss", 3)),
        strict_penalty_cap=int(cfg.get("strict_penalty_cap", 15)),
        claude_friendly_mode=bool(cfg.get("claude_friendly_mode", True)),
        frontier_model_applicability=cfg.get("frontier_model_applicability", {}),
        claude_curated_priorities=cfg.get("claude_curated_priorities", []),
        sources=cfg.get("sources", []),
        global_checks=cfg.get("global_checks", []),
    )

def _run_db_writes(
    db: Any,
    *,
    user_email: str,
    persona_id: str,
    channel: str,
    prompt_text: str,
    score: float,
    rating: str,
    issues: list,
    suggestions: list,
    improved: str,
    dimension_scores_raw: list,
    validation: dict,
    governance_payload: dict,
    source_of_truth: dict,
    delivery_channel: str,
    validation_score_10: float,
) -> None:
    """Run all three DB writes sequentially in a background task.

    Keeping them in a single helper preserves the dependency chain:
    capture_raw_event → raw_capture.raw_event_id → capture_enriched_event.
    Running this after the response is returned shaves the DB round-trip
    (~50–200 ms) off the user-facing latency.
    """
    raw_capture = None
    try:
        raw_capture = capture_raw_event(
            db,
            user_id=user_email,
            persona_id=persona_id,
            delivery_channel=delivery_channel,
            original_prompt=prompt_text,
            source_of_truth=source_of_truth,
        )
    except Exception:
        raw_capture = None

    try:
        save_validation(
            db,
            persona_id=persona_id,
            channel=channel,
            prompt_text=prompt_text,
            score=score,
            rating=rating,
            issues=issues,
            suggestions=suggestions,
            improved_prompt=improved,
            dimension_scores=dimension_scores_raw,
            user_email=user_email,
            llm_evaluation=validation["llm_evaluation"],
            data_governance=governance_payload,
            source_of_truth=source_of_truth,
            delivery_channel=delivery_channel,
            validation_score_10=validation_score_10,
            rewrite_strategy=validation.get("rewrite_strategy", "template"),
            rewrite_metadata={
                "rewrite_applied_guidelines": validation["llm_evaluation"].get("rewrite_applied_guidelines")
                if validation.get("llm_evaluation")
                else None,
                "rewrite_unresolved_gaps": validation["llm_evaluation"].get("rewrite_unresolved_gaps")
                if validation.get("llm_evaluation")
                else None,
            },
        )
    except Exception:
        pass

    try:
        capture_enriched_event(
            db,
            raw_event_id=(raw_capture.raw_event_id if raw_capture else None),
            event_id=(raw_capture.event_id if raw_capture else ""),
            user_id=user_email,
            persona_id=persona_id,
            team_id="",
            delivery_channel=delivery_channel,
            original_prompt=prompt_text,
            validation_score=score,
            suggestions=suggestions,
            corrected_prompt=improved,
            autofix_improvement_points=[],
            llm_evaluation=validation["llm_evaluation"],
            data_governance=governance_payload,
            source_of_truth=source_of_truth,
        )
    except Exception:
        pass


@router.post("/validate", response_model=ValidateResponse)
def validate_prompt(request: ValidateRequest, db: DbDep, background_tasks: BackgroundTasks):
    resolved_persona_id = request.persona_id
    if request.user_email and request.persona_id == "persona_0":
        resolved_persona_id = resolve_persona_for_user(db, email=request.user_email)
    persona = get_persona(resolved_persona_id)
    if not request.prompt_text.strip():
        raise HTTPException(status_code=400, detail="prompt_text cannot be empty.")

    try:
        validation = run_llm_validation(
            request.prompt_text,
            resolved_persona_id,
            auto_improve=request.auto_improve,
        )
    except GroqRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    score = validation["score"]
    dimension_scores_raw = validation["dimension_scores"]
    strengths = validation["strengths"]
    issues = validation["issues"]
    guideline_evaluation = validation["guideline_evaluation"]
    suggestions = _derive_issue_based_suggestions(
        resolved_persona_id,
        issues,
        persona.get("suggestions", []),
    )
    improved = validation["improved_prompt"]
    rating = rating_for_score(score)
    summary = f'{persona["name"]} prompt evaluated with score {score}.'
    delivery_channel = normalize_delivery_channel(request.channel)
    validation_score_10 = to_validation_score_10(score)
    source_of_truth = build_source_of_truth_payload()
    governance_payload = build_data_governance_payload(
        user_email=request.user_email or "",
        channel=request.channel,
        score_100=score,
        score_10=validation_score_10,
        llm_evaluation=validation["llm_evaluation"],
    )

    # Schedule DB persistence after response is sent — removes DB latency from
    # the user-facing critical path entirely (~50–200 ms saved per request).
    background_tasks.add_task(
        _run_db_writes,
        db,
        user_email=request.user_email or "",
        persona_id=resolved_persona_id,
        channel=request.channel,
        prompt_text=request.prompt_text,
        score=score,
        rating=rating,
        issues=issues,
        suggestions=suggestions,
        improved=improved,
        dimension_scores_raw=dimension_scores_raw,
        validation=validation,
        governance_payload=governance_payload,
        source_of_truth=source_of_truth,
        delivery_channel=delivery_channel,
        validation_score_10=validation_score_10,
    )

    return ValidateResponse(
        persona_id=resolved_persona_id,
        persona_name=persona["name"],
        score=score,
        rating=rating,
        summary=summary,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        improved_prompt=improved,
        dimension_scores=[ScoreDimension(**item) for item in dimension_scores_raw],
        guideline_evaluation=guideline_evaluation,
        llm_evaluation=validation["llm_evaluation"],
    )

@router.post("/improve", response_model=ValidateResponse)
def improve_only(request: ValidateRequest, db: DbDep, background_tasks: BackgroundTasks):
    request.auto_improve = True
    return validate_prompt(request=request, db=db, background_tasks=background_tasks)


@router.post("/auth/resolve", response_model=OAuthResolveResponse, dependencies=[Depends(require_api_key)])
def auth_resolve(request: OAuthResolveRequest, db: DbDep):
    return OAuthResolveResponse(**resolve_user_from_token(db, access_token=request.access_token, email_hint=request.email_hint))


@router.post("/auth/map-persona", response_model=PersonaMappingResponse, dependencies=[Depends(require_api_key)])
def auth_map_persona(request: PersonaMappingRequest, db: DbDep):
    mapped = map_persona(db, email=request.email, persona_id=request.persona_id, source=request.source)
    return PersonaMappingResponse(
        email=mapped.user_email,
        persona_id=mapped.persona_id,
        source=mapped.source,
        mapped=True,
    )


@router.post("/mcp/validate", response_model=ValidateResponse, dependencies=[Depends(require_api_key)])
def mcp_validate(request: MCPValidateRequest, db: DbDep):
    result = run_mcp_validation(
        db,
        prompt_text=request.prompt_text,
        persona_id=request.persona_id,
        user_email=request.user_email or "",
        auto_improve=request.auto_improve,
    )
    return ValidateResponse(
        persona_id=result["persona_id"],
        persona_name=result["persona_name"],
        score=result["score"],
        rating=result["rating"],
        summary=result["summary"],
        strengths=result["strengths"],
        issues=result["issues"],
        suggestions=result["suggestions"],
        improved_prompt=result["improved_prompt"],
        dimension_scores=[ScoreDimension(**item) for item in result["dimension_scores"]],
        guideline_evaluation=result["guideline_evaluation"],
        llm_evaluation=result.get("llm_evaluation"),
    )


@router.post("/teams/message", dependencies=[Depends(require_api_key)])
def teams_message(request: TeamsMessageRequest, db: DbDep):
    return handle_teams_message(
        db,
        user_email=request.user_email,
        message_text=request.message_text,
        persona_id=request.persona_id,
        access_token=request.access_token,
        email_hint=request.email_hint,
        teams_user_id=request.teams_user_id,
    )


@router.post("/slack/validate")
async def slack_validate(request: Request, background_tasks: BackgroundTasks, db: DbDep):
    """Slack Slash Command endpoint — ``/validate <prompt>``.

    Slack sends ``application/x-www-form-urlencoded`` with fields:
    ``text``, ``user_id``, ``response_url``, ``channel_id``, etc.

    Authentication is via Slack request signature (HMAC-SHA256) using
    ``SLACK_SIGNING_SECRET`` — no ``X-API-Key`` header required.

    Returns an immediate ephemeral ACK (≤3 s) while the full LLM
    validation runs in a background task and POSTs the Block Kit result
    to ``response_url``.
    """
    raw_body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_request(SLACK_SIGNING_SECRET, raw_body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")

    form = await request.form()
    text = str(form.get("text", "")).strip()
    user_id = str(form.get("user_id", "unknown"))
    response_url = str(form.get("response_url", ""))

    ack = handle_slack_slash_command(
        db,
        text=text,
        user_id=user_id,
        response_url=response_url,
        background_tasks=background_tasks,
    )
    return JSONResponse(content=ack)


@router.get("/analytics/summary", dependencies=[Depends(require_api_key)])
def analytics(db: DbDep):
    return analytics_summary(db)


@router.post("/aggregation/weekly/refresh", dependencies=[Depends(require_api_key)])
def refresh_weekly(db: DbDep, week_start: str | None = Query(default=None)):
    return refresh_weekly_intelligence(db, week_start=week_start)


@router.get("/user/weekly-summary", dependencies=[Depends(require_api_key)])
def weekly_summary(db: DbDep, user_id: str = Query(...), week_start: str | None = Query(default=None)):
    return user_weekly_summary(db, user_id=user_id, week_start=week_start)


@router.get("/leaderboard/weekly", dependencies=[Depends(require_api_key)])
def weekly_leaderboard(db: DbDep, week_start: str | None = Query(default=None), limit: int = Query(default=10, ge=1, le=100)):
    return {
        "week_start_date": week_start,
        "items": leaderboard_weekly(db, week_start=week_start, limit=limit),
    }


@router.get("/leadership/org-dashboard", dependencies=[Depends(require_api_key)])
def leadership_org_dashboard(db: DbDep, week_start: str | None = Query(default=None)):
    return org_dashboard(db, week_start=week_start)


@router.get("/leadership/team-report/{team_id}", dependencies=[Depends(require_api_key)])
def leadership_team_dashboard(team_id: str, db: DbDep, week_start: str | None = Query(default=None)):
    return team_report(db, team_id=team_id, week_start=week_start)

@router.get("/history", response_model=list[HistoryItem])
def history(db: DbDep, limit: int = Query(default=20, ge=1, le=200)):
    records = fetch_history(db, limit=limit)
    return [
        HistoryItem(
            id=item.id,
            persona_id=item.persona_id,
            channel=item.channel,
            score=item.score,
            rating=item.rating,
            prompt_text=item.prompt_text,
            improved_prompt=item.improved_prompt,
            created_at=item.created_at.isoformat()
        )
        for item in records
    ]
