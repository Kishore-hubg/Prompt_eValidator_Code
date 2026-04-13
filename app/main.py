import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.mcp.server import PromptValidatorMCPServer
from app.mcp.jsonrpc_handler import handle_jsonrpc
from app.core.settings import DATABASE_BACKEND, FRONTEND_DIR
from app.db.database import initialize_schema
from app.middleware.request_logging import RequestLoggingMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)

_log = logging.getLogger("prompt_validator.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise DB connections on first request — NOT at import time.
    This prevents Vercel build failures caused by MongoDB connection attempts
    during the serverless cold-start import phase."""
    try:
        if DATABASE_BACKEND == "mongodb":
            from app.db.mongo_db import init_mongo_indexes
            init_mongo_indexes()
            _log.info("MongoDB indexes initialised.")
        else:
            initialize_schema()
            _log.info("SQLite schema initialised.")
    except Exception as exc:
        _log.warning("DB init skipped (non-fatal at startup): %s", exc)
    yield


app = FastAPI(
    title="Prompt Validator MVP",
    version="1.0.0",
    description="Persona-aware prompt validation engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(router)


# ---------------------------------------------------------------------------
# Conversation persona state (best-effort; resets on container recycle)
# ---------------------------------------------------------------------------
_teams_persona: dict[str, str] = {}

_TEAMS_HELP = (
    "**Prompt Validator Bot** 🤖\n\n"
    "**Commands:**\n"
    "• `help` — show this message\n"
    "• `/persona` — list available personas\n"
    "• `/set-persona <id>` — e.g. `/set-persona persona_1`\n\n"
    "**Validating:** just type or paste any prompt and send!\n\n"
    "**Personas:**\n"
    "• `persona_1` — 💻 Developer + QA\n"
    "• `persona_2` — 📋 Technical PM\n"
    "• `persona_3` — 📊 BA & PO\n"
    "• `persona_4` — 🎧 Support Staff\n"
    "• `persona_0` — 🏢 All Employees"
)

_PERSONA_MAP = {
    "persona_0": {"name": "All Employees",   "emoji": "🏢"},
    "persona_1": {"name": "Developer + QA",  "emoji": "💻"},
    "persona_2": {"name": "Technical PM",    "emoji": "📋"},
    "persona_3": {"name": "BA & PO",         "emoji": "📊"},
    "persona_4": {"name": "Support Staff",   "emoji": "🎧"},
}


async def _resolve_teams_user_email(
    service_url: str,
    conversation_id: str,
    user_id: str,
    app_id: str,
    app_password: str,
    tenant_id: str,
) -> str:
    """Look up the real email/UPN for a Teams user via the Bot Framework connector.

    Uses the same bot app credentials as _teams_send_reply — no extra permissions
    or user OAuth required.  Calls:
        GET {serviceUrl}/v3/conversations/{conversationId}/members/{userId}

    Args:
        service_url:     Teams service URL from the incoming activity.
        conversation_id: Conversation ID from the incoming activity.
        user_id:         AAD Object ID or Teams user ID (from_property.id).
        app_id:          BOT_APP_ID (Azure bot app registration client ID).
        app_password:    BOT_APP_PASSWORD.
        tenant_id:       BOT_APP_TENANT_ID.

    Returns:
        Lowercase email string if resolved, otherwise empty string.
    """
    import httpx

    try:
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        async with httpx.AsyncClient(timeout=10.0) as client:
            tok = await client.post(token_url, data={
                "grant_type": "client_credentials",
                "client_id": app_id,
                "client_secret": app_password,
                "scope": "https://api.botframework.com/.default",
            })
            tok.raise_for_status()
            bot_token = tok.json()["access_token"]

            members_url = (
                f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/members/{user_id}"
            )
            resp = await client.get(
                members_url,
                headers={"Authorization": f"Bearer {bot_token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                email = (data.get("email") or "").strip()
                if email and "@" in email:
                    return email.lower()
                upn = (data.get("userPrincipalName") or "").strip()
                if upn and "@" in upn:
                    return upn.lower()
    except Exception as exc:  # noqa: BLE001
        _log.warning("Teams member lookup failed for user %s: %s", user_id, exc)
    return ""


async def _teams_send_reply(
    service_url: str,
    conversation_id: str,
    activity_id: str,
    app_id: str,
    app_password: str,
    tenant_id: str,
    text: str | None = None,
    card: dict | None = None,
) -> None:
    """Acquire a Single-Tenant Bot Framework token and POST the reply activity."""
    import httpx

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        tok = await client.post(token_url, data={
            "grant_type": "client_credentials",
            "client_id": app_id,
            "client_secret": app_password,
            "scope": "https://api.botframework.com/.default",
        })
        tok.raise_for_status()
        access_token = tok.json()["access_token"]

        if card:
            activity = {
                "type": "message",
                "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}],
            }
        else:
            activity = {"type": "message", "text": text or ""}

        reply_url = (
            f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities/{activity_id}"
        )
        _log.info("Teams reply → %s", reply_url)
        resp = await client.post(
            reply_url,
            json=activity,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )
        _log.info("Teams reply status: %s", resp.status_code)
        resp.raise_for_status()


# Teams Bot Framework messaging endpoint (no /api/v1 prefix)
@app.post("/api/messages", include_in_schema=False)
async def teams_messages(request: Request):
    """Teams Bot Framework messaging endpoint — botbuilder-free implementation.

    Bypasses botbuilder's JWT validation (which has cryptography library
    compatibility issues with Single Tenant bots) and uses direct httpx calls
    to acquire tokens and send replies via the Bot Framework REST API.
    """
    import asyncio
    from fastapi.responses import JSONResponse
    from teams_bot.cards import _build_adaptive_card, _build_persona_list_card
    from teams_bot.config import TeamsBotSettings
    from app.integrations.teams.bot import handle_teams_message
    from app.db.database import get_db

    try:
        if "application/json" not in request.headers.get("Content-Type", ""):
            return JSONResponse({"error": "Content-Type must be application/json"}, status_code=415)

        body = await request.json()
        activity_type = body.get("type", "")

        # Only process message activities; ACK everything else silently
        if activity_type != "message":
            return JSONResponse({}, status_code=200)

        settings = TeamsBotSettings()
        if not settings.microsoft_app_tenant_id:
            _log.error("BOT_APP_TENANT_ID not set — cannot send replies")
            return JSONResponse({"error": "BOT_APP_TENANT_ID not configured"}, status_code=500)

        # Extract activity fields
        text = (body.get("text") or "").strip()
        # Strip @mention prefix Teams injects in channel conversations
        if "<at>" in text and "</at>" in text:
            text = text[text.index("</at>") + 5:].strip()

        value = body.get("value") or {}
        conversation_id = (body.get("conversation") or {}).get("id", "")
        activity_id = body.get("id", "")
        service_url = body.get("serviceUrl", "https://smba.trafficmanager.net/teams/")
        from_info = body.get("from") or {}
        teams_user_id = from_info.get("aadObjectId") or from_info.get("id") or ""

        # Resolve real email via Bot Framework connector (same bot credentials,
        # no user OAuth required). Falls back to UUID@teams.local if unavailable.
        user_email = ""
        if teams_user_id and settings.microsoft_app_id and settings.microsoft_app_password:
            user_email = await _resolve_teams_user_email(
                service_url=service_url,
                conversation_id=conversation_id,
                user_id=teams_user_id,
                app_id=settings.microsoft_app_id,
                app_password=settings.microsoft_app_password,
                tenant_id=settings.microsoft_app_tenant_id,
            )
        if not user_email:
            user_email = f"{teams_user_id}@teams.local" if teams_user_id else "teams-anon@teams.local"

        reply_text: str | None = None
        reply_card: dict | None = None

        # ── Adaptive Card button callbacks ──────────────────────────────────
        if isinstance(value, dict) and value.get("action"):
            action = value["action"]
            if action == "set_persona":
                pid = (value.get("persona_id") or "").strip()
                if pid in _PERSONA_MAP:
                    _teams_persona[conversation_id] = pid
                    p = _PERSONA_MAP[pid]
                    reply_text = f"✅ Persona set to **{p['emoji']} {p['name']}** (`{pid}`). Send any prompt to validate it."
                else:
                    reply_text = "Unknown persona. Use /persona to see options."
            elif action == "list_personas":
                reply_card = _build_persona_list_card()
            elif action == "copy_prompt":
                improved = value.get("text", "")
                reply_text = f"**Improved Prompt** (select all & copy):\n\n```\n{improved}\n```"
            else:
                reply_text = "Unknown action."

        # ── Text commands ───────────────────────────────────────────────────
        elif text:
            lower = text.lower()
            if lower in ("help", "/help"):
                reply_text = _TEAMS_HELP
            elif lower in ("/persona", "persona", "list personas", "/persona list"):
                reply_card = _build_persona_list_card()
            elif lower.startswith("/set-persona "):
                pid = text[13:].strip().lower()
                if pid in _PERSONA_MAP:
                    _teams_persona[conversation_id] = pid
                    p = _PERSONA_MAP[pid]
                    reply_text = f"✅ Persona set to **{p['emoji']} {p['name']}** (`{pid}`). Send any prompt to validate it."
                else:
                    valid = ", ".join(f"`{k}`" for k in _PERSONA_MAP)
                    reply_text = f"Unknown persona. Valid options: {valid}"
            else:
                # ── Validate the prompt in-process ──────────────────────────
                persona_id = _teams_persona.get(conversation_id)
                db_gen = get_db()
                db = next(db_gen)
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: handle_teams_message(
                            db,
                            user_email=user_email,
                            message_text=text,
                            persona_id=persona_id,
                        ),
                    )
                finally:
                    db_gen.close()
                reply_card = _build_adaptive_card(result)
        else:
            return JSONResponse({}, status_code=200)

        # ── Send reply ──────────────────────────────────────────────────────
        await _teams_send_reply(
            service_url=service_url,
            conversation_id=conversation_id,
            activity_id=activity_id,
            app_id=settings.microsoft_app_id,
            app_password=settings.microsoft_app_password,
            tenant_id=settings.microsoft_app_tenant_id,
            text=reply_text,
            card=reply_card,
        )
        return JSONResponse({}, status_code=201)

    except Exception as e:
        _log.error("Teams message processing error: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


# MCP (Model Context Protocol) endpoints
_mcp_server = PromptValidatorMCPServer()


@app.post("/mcp/list-tools", include_in_schema=False)
async def mcp_list_tools():
    """MCP: List all available tools.

    Called by Claude Code, Claude API, Teams bot to discover capabilities.
    """
    try:
        tools = await _mcp_server.list_tools()
        return JSONResponse({"tools": tools, "status": "ok"})
    except Exception as e:
        _log.error("MCP list_tools error: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/mcp/call-tool", include_in_schema=False)
async def mcp_call_tool(request: Request):
    """MCP: Execute a tool.

    POST body: {"tool_name": str, "arguments": dict}
    Response: {"result": dict, "status": "ok|failed"}
    """
    try:
        body = await request.json()
        tool_name = body.get("tool_name")
        arguments = body.get("arguments", {})

        if not tool_name:
            return JSONResponse(
                {"error": "Missing tool_name in request"},
                status_code=400
            )

        result = await _mcp_server.call_tool(tool_name, arguments)
        return JSONResponse({
            "result": result,
            "tool": tool_name,
            "status": "ok" if "error" not in result else "failed"
        })

    except Exception as e:
        _log.error("MCP call_tool error: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/mcp/resources", include_in_schema=False)
async def mcp_get_resources():
    """MCP: Get available resources (documentation, examples)."""
    try:
        resources = await _mcp_server.get_resources()
        return JSONResponse({"resources": resources, "status": "ok"})
    except Exception as e:
        _log.error("MCP get_resources error: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/mcp/capabilities", include_in_schema=False)
async def mcp_get_capabilities():
    """MCP: Get server capabilities and metadata."""
    return JSONResponse({
        "name": _mcp_server.name,
        "version": _mcp_server.version,
        "capabilities": {
            "tools": True,
            "resources": True,
            "prompts": False,
        },
        "endpoints": {
            "list_tools": "/mcp/list-tools",
            "call_tool": "/mcp/call-tool",
            "get_resources": "/mcp/resources",
        }
    })


# ---------------------------------------------------------------------------
# Standard MCP JSON-RPC 2.0 endpoint (claude mcp add --transport http)
# ---------------------------------------------------------------------------

@app.post("/mcp", include_in_schema=False)
async def mcp_jsonrpc(request: Request):
    """Standard MCP JSON-RPC 2.0 endpoint.

    This is the wire-protocol endpoint used by Claude Code, Claude Desktop,
    and any MCP-compatible client.

    Registration (one-time):
        claude mcp add --transport http prompt-validator \\
            https://promptvalidatorcompleterepo.vercel.app/mcp

    Claude Desktop (claude_desktop_config.json):
        {
          "mcpServers": {
            "prompt-validator": {
              "url": "https://promptvalidatorcompleterepo.vercel.app/mcp",
              "transport": "http"
            }
          }
        }

    The existing /mcp/list-tools and /mcp/call-tool endpoints are preserved
    for backward compatibility and direct REST demos.
    """
    # Parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None,
             "error": {"code": -32700, "message": "Parse error: invalid JSON"}},
            status_code=400,
        )

    # Batch request (JSON-RPC 2.0 spec §6)
    if isinstance(body, list):
        if not body:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32600, "message": "Invalid Request: empty batch"}},
                status_code=400,
            )
        responses = []
        for msg in body:
            resp = await handle_jsonrpc(msg, _mcp_server)
            if resp is not None:   # omit notification responses from batch
                responses.append(resp)
        # If every message was a notification, return 202 with no body
        if not responses:
            return Response(status_code=202)
        return JSONResponse(responses)

    # Single request
    response = await handle_jsonrpc(body, _mcp_server)
    if response is None:
        # Pure notification — no response body per spec
        return Response(status_code=202)
    return JSONResponse(response)


@app.get("/mcp", include_in_schema=False)
async def mcp_jsonrpc_get():
    """MCP GET — signals that SSE transport is not supported; use POST."""
    return JSONResponse(
        {"error": "Use POST for MCP JSON-RPC 2.0. SSE transport not supported on this server."},
        status_code=405,
    )


if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")

@app.get("/", include_in_schema=False)
def root():
    return FileResponse(FRONTEND_DIR / "index.html")
