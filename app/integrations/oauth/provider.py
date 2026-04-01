from __future__ import annotations

from typing import Any

import jwt
from fastapi import HTTPException

from app.auth.persona_mapping import resolve_persona_for_user, upsert_user
from app.core.settings import (
    ALLOW_MOCK_OAUTH,
    MICROSOFT_ALLOWED_AUDIENCES,
    MICROSOFT_CLIENT_ID,
    MICROSOFT_ISSUER,
    MICROSOFT_JWKS_URL,
    MICROSOFT_TENANT_ID,
    OAUTH_PROVIDER_NAME,
)

_jwk_client = jwt.PyJWKClient(MICROSOFT_JWKS_URL)


def _is_microsoft_provider() -> bool:
    return OAUTH_PROVIDER_NAME.strip().lower() in {
        "microsoft",
        "microsoft-entra-id",
        "azure-ad",
        "entra",
    }


def _extract_email(claims: dict[str, Any], email_hint: str | None) -> str:
    for field in ("email", "preferred_username", "upn", "unique_name"):
        value = claims.get(field)
        if isinstance(value, str) and "@" in value:
            return value.strip().lower()
    if email_hint and "@" in email_hint:
        return email_hint.strip().lower()
    raise HTTPException(
        status_code=400,
        detail="Could not resolve email from Microsoft token. Provide email_hint or include email/UPN claim.",
    )


def _resolve_user_from_microsoft_token(access_token: str, email_hint: str | None) -> dict[str, Any]:
    if not MICROSOFT_CLIENT_ID:
        raise HTTPException(status_code=500, detail="MICROSOFT_CLIENT_ID is not configured.")
    if not MICROSOFT_JWKS_URL:
        raise HTTPException(status_code=500, detail="MICROSOFT_JWKS_URL is not configured.")

    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(access_token)
        claims = jwt.decode(
            access_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=MICROSOFT_ALLOWED_AUDIENCES or MICROSOFT_CLIENT_ID,
            issuer=MICROSOFT_ISSUER,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Microsoft token: {exc}") from exc

    if MICROSOFT_TENANT_ID != "common":
        token_tid = claims.get("tid")
        if token_tid and str(token_tid).lower() != MICROSOFT_TENANT_ID.lower():
            raise HTTPException(status_code=401, detail="Token tenant does not match configured tenant.")

    email = _extract_email(claims, email_hint=email_hint)
    display_name = str(claims.get("name") or email.split("@")[0]).strip()
    return {"email": email, "display_name": display_name}


def resolve_user_from_token(db, *, access_token: str, email_hint: str | None = None) -> dict:
    if _is_microsoft_provider():
        identity = _resolve_user_from_microsoft_token(access_token, email_hint=email_hint)
        email = identity["email"]
        display_name = identity["display_name"]
    elif ALLOW_MOCK_OAUTH:
        # Backward-compatible mock mode for local/dev environments.
        if email_hint and "@" in email_hint:
            email = email_hint.strip().lower()
        else:
            token_stub = (access_token or "user").strip()[:8].lower() or "user"
            email = f"{token_stub}@infovision.local"
        display_name = email.split("@")[0].replace(".", " ").title()
    else:
        raise HTTPException(
            status_code=500,
            detail="OAuth provider is not configured. Set PROMPT_VALIDATOR_OAUTH_PROVIDER=microsoft.",
        )

    upsert_user(db, email=email, display_name=display_name)
    persona_id = resolve_persona_for_user(db, email=email)
    return {
        "email": email,
        "display_name": display_name,
        "provider": OAUTH_PROVIDER_NAME,
        "persona_id": persona_id,
    }
