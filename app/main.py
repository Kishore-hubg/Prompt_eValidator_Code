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


# Teams Bot Framework messaging endpoint (no /api/v1 prefix)
@app.post("/api/messages", include_in_schema=False)
async def teams_messages(request: Request):
    """Teams Bot Framework messaging endpoint.

    Azure Bot Service POSTs Activities here with:
    - Authorization header (bearer token from Azure)
    - JSON body with Activity schema
    """
    from fastapi.responses import JSONResponse
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
