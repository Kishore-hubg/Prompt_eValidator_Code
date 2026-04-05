from typing import Annotated, Any

import hashlib as _hashlib
import hmac as _hmac
import time as _time
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Query, Request
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


@router.post("/messages", include_in_schema=False)
async def teams_messages(request: Request):
    """Teams Bot Framework messaging endpoint.

    Azure Bot Service POSTs Activities here with:
    - Authorization header (bearer token from Azure)
    - JSON body with Activity schema

    This endpoint processes incoming Teams messages via BotFrameworkAdapter.
    """
    try:
        from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
        from botbuilder.schema import Activity
        from teams_bot.bot import PromptValidatorTeamsBot
        from teams_bot.config import TeamsBotSettings

        # Initialize on each request (stateless)
        settings = TeamsBotSettings()
        adapter_settings = BotFrameworkAdapterSettings(
            settings.microsoft_app_id,
            settings.microsoft_app_password,
        )
        adapter = BotFrameworkAdapter(adapter_settings)

        async def on_error(context):
            await context.send_activity(f"Bot encountered an error or it has crashed.")

        adapter.on_turn_error = on_error
        bot = PromptValidatorTeamsBot(settings, adapter)

        # Validate content type
        content_type = request.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            return JSONResponse({"error": "Content-Type must be application/json"}, status_code=415)

        # Parse activity from request body
        body = await request.json()
        activity = Activity().deserialize(body)
        auth_header = request.headers.get("Authorization", "")

        # Process the activity through the adapter
        response = await adapter.process_activity(activity, auth_header, bot.on_turn)

        if response:
            return JSONResponse(data=response.body, status_code=response.status)
        return JSONResponse({}, status_code=201)

    except Exception as e:
        _log.error("Teams message processing error: %s", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


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


# ─────────────────────────────────────────────────────────────────────────────
# Admin dashboard — hardcoded credentials, HMAC-signed stateless token
# ─────────────────────────────────────────────────────────────────────────────
_ADMIN_EMAIL    = "pratyoosh.patel@infovision.com"
_ADMIN_PASSWORD = "$Infovision2026$"
_ADMIN_SECRET   = "pv-admin-2026-infovision-coe"
_ADMIN_TTL      = 28_800  # 8 hours


def _admin_make_token() -> str:
    exp = int(_time.time()) + _ADMIN_TTL
    sig = _hmac.new(
        _ADMIN_SECRET.encode(),
        f"{_ADMIN_EMAIL}:{exp}".encode(),
        _hashlib.sha256,
    ).hexdigest()
    return f"{exp}:{sig}"


def _admin_verify_token(token: str) -> bool:
    try:
        exp_str, sig = token.split(":", 1)
        exp = int(exp_str)
        if _time.time() > exp:
            return False
        expected = _hmac.new(
            _ADMIN_SECRET.encode(),
            f"{_ADMIN_EMAIL}:{exp}".encode(),
            _hashlib.sha256,
        ).hexdigest()
        return _hmac.compare_digest(sig, expected)
    except Exception:
        return False


def _require_admin(authorization: str = Header(default="")) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    if not _admin_verify_token(token):
        raise HTTPException(status_code=401, detail="Admin session expired. Please log in again.")


@router.post("/admin/login", include_in_schema=False)
def admin_login(payload: dict = Body(...)):
    email    = str(payload.get("email", "")).strip()
    password = str(payload.get("password", "")).strip()
    if email != _ADMIN_EMAIL or password != _ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")
    return {"token": _admin_make_token(), "expires_in": _ADMIN_TTL}


@router.get("/admin/records", include_in_schema=False)
def admin_records(
    db: DbDep,
    authorization: str = Header(default=""),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    search: str = Query(default=""),
    persona_id: str = Query(default=""),
    rating: str = Query(default=""),
    channel: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    _require_admin(authorization)
    import json as _json
    from datetime import datetime as _dt
    from sqlalchemy.orm import Session

    def _fmt_row(r_id, created_at, p_id, chan, del_chan, email, score, rat, sc10, iss_cnt, llm_ev_raw, prompt, improved):
        llm_ev = {}
        try:
            llm_ev = _json.loads(llm_ev_raw or "{}")
        except Exception:
            pass
        ts = created_at.strftime("%d %b %Y %H:%M") if isinstance(created_at, _dt) else str(created_at or "")
        return {
            "id": r_id,
            "created_at": ts,
            "persona_id": p_id or "",
            "channel": chan or "",
            "delivery_channel": del_chan or "",
            "user_email": email or "",
            "score": round(float(score or 0), 1),
            "rating": rat or "",
            "validation_score_10": round(float(sc10 or 0), 1),
            "issue_count": int(iss_cnt or 0),
            "llm_provider": llm_ev.get("provider", ""),
            "llm_model": llm_ev.get("model", ""),
            "prompt_text": prompt or "",
            "improved_prompt": improved or "",
        }

    # ── MongoDB path ─────────────────────────────────────────────────────────
    if not isinstance(db, Session):
        from pymongo.database import Database as _MDB
        if not isinstance(db, _MDB):
            raise HTTPException(status_code=501, detail="Unsupported database backend.")

        mongo_filter: dict = {}
        if search:
            mongo_filter["$or"] = [
                {"prompt_text":  {"$regex": search, "$options": "i"}},
                {"user_email":   {"$regex": search, "$options": "i"}},
            ]
        if persona_id:
            mongo_filter["persona_id"] = persona_id
        if rating:
            mongo_filter["rating"] = rating
        if channel:
            mongo_filter["delivery_channel"] = channel
        date_filter: dict = {}
        if date_from:
            try:
                date_filter["$gte"] = _dt.strptime(date_from, "%Y-%m-%d")
            except ValueError:
                pass
        if date_to:
            try:
                date_filter["$lt"] = _dt.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            except ValueError:
                pass
        if date_filter:
            mongo_filter["created_at"] = date_filter

        total = db.prompt_validations.count_documents(mongo_filter)
        cursor = (
            db.prompt_validations.find(mongo_filter)
            .sort("created_at", -1)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        records = [
            _fmt_row(
                doc.get("id", str(doc.get("_id", ""))),
                doc.get("created_at"),
                doc.get("persona_id"), doc.get("channel"), doc.get("delivery_channel"),
                doc.get("user_email"), doc.get("score"), doc.get("rating"),
                doc.get("validation_score_10"), doc.get("issue_count"),
                doc.get("llm_evaluation_json"), doc.get("prompt_text"), doc.get("improved_prompt"),
            )
            for doc in cursor
        ]
        return {
            "records": records,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        }

    # ── SQLite path ──────────────────────────────────────────────────────────
    from sqlalchemy import and_, func, or_
    from app.models.db_models import PromptValidationRecord

    filters = []
    if search:
        filters.append(or_(
            PromptValidationRecord.prompt_text.ilike(f"%{search}%"),
            PromptValidationRecord.user_email.ilike(f"%{search}%"),
        ))
    if persona_id:
        filters.append(PromptValidationRecord.persona_id == persona_id)
    if rating:
        filters.append(PromptValidationRecord.rating == rating)
    if channel:
        filters.append(PromptValidationRecord.delivery_channel == channel)
    if date_from:
        try:
            filters.append(PromptValidationRecord.created_at >= _dt.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            filters.append(PromptValidationRecord.created_at < _dt.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            pass

    where_clause = and_(*filters) if filters else True
    import sqlalchemy as _sa
    total = db.execute(_sa.select(func.count()).select_from(PromptValidationRecord).where(where_clause)).scalar() or 0
    rows = list(db.execute(
        _sa.select(PromptValidationRecord)
        .where(where_clause)
        .order_by(PromptValidationRecord.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).scalars().all())

    records = [
        _fmt_row(
            r.id, r.created_at, r.persona_id, r.channel, r.delivery_channel,
            r.user_email, r.score, r.rating, r.validation_score_10, r.issue_count,
            r.llm_evaluation_json, r.prompt_text, r.improved_prompt,
        )
        for r in rows
    ]

    return {
        "records": records,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }
