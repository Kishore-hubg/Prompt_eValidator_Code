from app.auth.persona_mapping import resolve_persona_for_user
from app.services.persona_loader import get_persona
from app.services.prompt_validation import run_llm_validation
from app.services.history_service import save_validation
from app.services.data_strategy import (
    build_data_governance_payload,
    build_source_of_truth_payload,
    normalize_delivery_channel,
    to_validation_score_10,
)
from app.services.event_pipeline import capture_enriched_event, capture_raw_event


def run_mcp_validation(
    db,
    *,
    prompt_text: str,
    persona_id: str,
    user_email: str = "",
    auto_improve: bool = True,
    channel: str = "mcp",
) -> dict:
    resolved_persona = persona_id
    if user_email and persona_id == "persona_0":
        resolved_persona = resolve_persona_for_user(db, email=user_email)

    persona = get_persona(resolved_persona)
    validation = run_llm_validation(
        prompt_text,
        resolved_persona,
        auto_improve=auto_improve,
    )
    score = validation["score"]
    dimension_scores = validation["dimension_scores"]
    strengths = validation["strengths"]
    issues = validation["issues"]
    guideline_eval = validation["guideline_evaluation"]
    improved_prompt = validation["improved_prompt"]
    rating = "Excellent" if score >= 85 else "Good" if score >= 70 else "Needs Improvement" if score >= 50 else "Poor"
    delivery_channel = normalize_delivery_channel(channel)
    validation_score_10 = to_validation_score_10(score)
    source_of_truth = build_source_of_truth_payload()
    raw_capture = None
    try:
        raw_capture = capture_raw_event(
            db,
            user_id=user_email or "",
            persona_id=resolved_persona,
            delivery_channel=delivery_channel,
            original_prompt=prompt_text,
            source_of_truth=source_of_truth,
        )
    except Exception:
        raw_capture = None
    governance_payload = build_data_governance_payload(
        user_email=user_email or "",
        channel=channel,
        score_100=score,
        score_10=validation_score_10,
        llm_evaluation=validation.get("llm_evaluation"),
    )
    save_validation(
        db,
        persona_id=resolved_persona,
        channel=channel,
        prompt_text=prompt_text,
        score=score,
        rating=rating,
        issues=issues,
        suggestions=persona.get("suggestions", []),
        improved_prompt=improved_prompt,
        dimension_scores=dimension_scores,
        user_email=user_email or "",
        llm_evaluation=validation.get("llm_evaluation"),
        data_governance=governance_payload,
        source_of_truth=source_of_truth,
        delivery_channel=delivery_channel,
        validation_score_10=validation_score_10,
        rewrite_strategy=validation.get("rewrite_strategy", "template"),
        rewrite_metadata={
            "rewrite_applied_guidelines": (validation.get("llm_evaluation") or {}).get("rewrite_applied_guidelines"),
            "rewrite_unresolved_gaps": (validation.get("llm_evaluation") or {}).get("rewrite_unresolved_gaps"),
        },
    )
    try:
        capture_enriched_event(
            db,
            raw_event_id=(raw_capture.raw_event_id if raw_capture else None),
            event_id=(raw_capture.event_id if raw_capture else ""),
            user_id=user_email or "",
            persona_id=resolved_persona,
            team_id="",
            delivery_channel=delivery_channel,
            original_prompt=prompt_text,
            validation_score=score,
            suggestions=persona.get("suggestions", []),
            corrected_prompt=improved_prompt,
            autofix_improvement_points=[],
            llm_evaluation=validation.get("llm_evaluation"),
            data_governance=governance_payload,
            source_of_truth=source_of_truth,
        )
    except Exception:
        pass
    return {
        "persona_id": resolved_persona,
        "persona_name": persona["name"],
        "score": score,
        "rating": rating,
        "summary": f'{persona["name"]} prompt evaluated through {channel.upper()} with score {score}.',
        "strengths": strengths,
        "issues": issues,
        "suggestions": persona.get("suggestions", []),
        "improved_prompt": improved_prompt,
        "dimension_scores": dimension_scores,
        "guideline_evaluation": guideline_eval,
        "llm_evaluation": validation["llm_evaluation"],
    }
