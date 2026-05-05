"""
SSO Auth Middleware for WebUI Routes
Validates JWT tokens from MSAL.js and injects user context
"""

import logging
from typing import Callable, Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.integrations.oauth.provider import resolve_user_from_token
from app.core.settings import OAUTH_PROVIDER_NAME, ALLOW_MOCK_OAUTH


_log = logging.getLogger("prompt_validator.middleware.auth_sso")


class SSO_AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to protect WebUI routes with SSO auth.

    Protected routes: /assets/*, /api/v1/validate (via WebUI), etc.
    Exempted routes: /api/v1/auth/*, /api/v1/slack/*, /api/v1/teams/*, /api/v1/mcp/*
    """

    # Routes that DO NOT require SSO
    EXEMPT_PATHS = {
        # Static files — must be served freely so browser can load the app
        "/",
        "/assets",          # static file mount
        "/favicon.ico",

        # MCP protocol endpoints
        "/mcp",

        # Open API endpoints (no user context needed)
        "/api/v1/health",
        "/api/v1/validation-mode",
        "/api/v1/demo-samples",
        "/api/v1/personas",
        "/api/v1/guidelines",
        "/api/v1/compliance/",
        "/api/v1/auth/",    # OAuth endpoints themselves

        # Integration channels — have their own auth mechanisms
        "/api/v1/slack/",   # Slack HMAC-SHA256 signing
        "/api/v1/teams/",   # Teams bot credentials
        "/api/v1/mcp/",     # MCP uses API_KEY

        # Teams Bot Framework messaging endpoint (uses botframework token, not SSO)
        "/api/messages",

        # Admin — has own basic auth
        "/api/v1/admin/",
    }

    def __init__(self, app, protect_webui: bool = True):
        super().__init__(app)
        self.protect_webui = protect_webui

    def _is_exempt(self, path: str) -> bool:
        """Check if path is exempt from SSO.

        Rules:
        - Exact path "/" matches only the root (not every URL)
        - Paths ending with "/" (e.g. "/api/v1/auth/") → prefix match
        - All other entries → exact match OR prefix with a trailing slash
          (e.g. "/assets" matches "/assets" and "/assets/auth.js")
        """
        for exempt in self.EXEMPT_PATHS:
            if exempt == "/":
                if path == "/":
                    return True
            elif exempt.endswith("/"):
                # already a prefix — startswith is correct
                if path.startswith(exempt):
                    return True
            else:
                # exact OR sub-path (e.g. /assets/auth.js under /assets)
                if path == exempt or path.startswith(exempt + "/"):
                    return True
        return False

    def _get_token_from_request(self, request: Request) -> Optional[str]:
        """Extract Bearer token from Authorization header."""
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None

    async def dispatch(self, request: Request, call_next: Callable) -> None:
        """
        Check auth for protected routes.
        Add user context to request.state for downstream handlers.
        """
        path = request.url.path

        # Skip middleware if not protecting WebUI or path is exempt
        if not self.protect_webui or self._is_exempt(path):
            return await call_next(request)

        # Extract token
        token = self._get_token_from_request(request)
        if not token:
            _log.warning(f"No token for protected route: {path}")
            return JSONResponse(
                {"detail": "Missing or invalid Authorization header"},
                status_code=401,
            )

        # Validate token
        try:
            from app.db.database import get_db
            db_gen = get_db()
            db = next(db_gen)
            try:
                user_data = resolve_user_from_token(db, access_token=token)
            finally:
                try:
                    next(db_gen)
                except StopIteration:
                    pass

            request.state.user = user_data
            request.state.email = user_data.get("email")
            request.state.persona_id = user_data.get("persona_id")

            _log.info(f"SSO auth OK: {user_data.get('email')} on {path}")
        except HTTPException as exc:
            _log.warning(f"SSO auth failed for {path}: {exc.detail}")
            return JSONResponse(
                {"detail": str(exc.detail)},
                status_code=exc.status_code,
            )
        except Exception as exc:
            _log.error(f"SSO auth error: {exc}")
            return JSONResponse(
                {"detail": "Authentication failed"},
                status_code=401,
            )

        response = await call_next(request)
        return response
