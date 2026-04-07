from fastapi import HTTPException

from app.auth.persona_mapping import resolve_persona_for_user
from app.integrations.mcp.server import run_mcp_validation
from app.integrations.oauth.provider import resolve_user_from_token


def handle_teams_message(
    db,
    *,
    user_email: str | None,
    message_text: str,
    persona_id: str | None = None,
    access_token: str | None = None,
    email_hint: str | None = None,
    teams_user_id: str | None = None,
) -> dict:
    email = (user_email or "").strip().lower()
    if not email and access_token:
        try:
            identity = resolve_user_from_token(db, access_token=access_token, email_hint=email_hint)
            email = identity["email"]
        except Exception:
            pass
    # Graceful fallback for dev/POC environments without OAuth configured:
    # synthesise a stable identifier from the Teams AAD object ID or a generic placeholder.
    if not email:
        if teams_user_id:
            email = f"{teams_user_id.lower().replace(' ', '-')}@teams.local"
        else:
            email = "teams-anonymous@teams.local"

    resolved_persona = persona_id or resolve_persona_for_user(db, email=email)
    result = run_mcp_validation(
        db,
        prompt_text=message_text,
        persona_id=resolved_persona,
        user_email=email,
        auto_improve=True,
        channel="teams",
    )
    return {
        "channel": "teams",
        "user_email": email,
        "persona_id": result["persona_id"],
        "persona_name": result.get("persona_name", result["persona_id"]),
        "score": result["score"],
        "rating": result["rating"],
        "issues": result["issues"],
        "suggestions": result["suggestions"],
        "improved_prompt": result["improved_prompt"],
        "dimension_scores": result.get("dimension_scores") or [],
        "message": (
            f"[Teams Bot] Score {result['score']} ({result['rating']}) for {result['persona_name']}. "
            "Use improved_prompt for best output."
        ),
    }
