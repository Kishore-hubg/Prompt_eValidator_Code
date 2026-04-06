"""Standard MCP JSON-RPC 2.0 handler.

Implements the Model Context Protocol wire format so that Claude Code,
Claude Desktop, and any MCP-compatible client can connect via:

    claude mcp add --transport http prompt-validator \\
        https://promptvalidatorcompleterepo.vercel.app/mcp

Protocol reference: https://spec.modelcontextprotocol.io/specification/
Transport:          Streamable HTTP (stateless, POST-only, no SSE)
JSON-RPC version:   2.0
MCP protocol ver:   2024-11-05
"""
from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger("prompt_validator.mcp.jsonrpc")

# MCP protocol version advertised during initialize handshake
MCP_PROTOCOL_VERSION = "2024-11-05"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def handle_jsonrpc(
    body: dict,
    mcp_server,  # PromptValidatorMCPServer — avoid circular import
) -> dict | None:
    """Dispatch one JSON-RPC 2.0 message.

    Returns:
        A JSON-RPC response dict, or ``None`` for notifications
        (which must not receive a response per the spec).
    """
    jsonrpc = body.get("jsonrpc")
    method: str = body.get("method", "")
    params: dict = body.get("params") or {}
    # Notifications have no "id" key at all (distinct from id=null)
    is_notification = "id" not in body
    msg_id = body.get("id")

    if jsonrpc != "2.0":
        if is_notification:
            return None
        return _error(msg_id, -32600, "Invalid Request: jsonrpc must be '2.0'")

    try:
        result = await _dispatch(method, params, mcp_server)
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    except _MethodNotFound as exc:
        if is_notification:
            return None
        return _error(msg_id, -32601, str(exc))

    except (ValueError, KeyError) as exc:
        if is_notification:
            return None
        return _error(msg_id, -32602, f"Invalid params: {exc}")

    except Exception as exc:  # noqa: BLE001
        _log.error("JSON-RPC internal error [%s]: %s", method, exc, exc_info=True)
        if is_notification:
            return None
        return _error(msg_id, -32603, f"Internal error: {exc}")


# ---------------------------------------------------------------------------
# Method dispatcher
# ---------------------------------------------------------------------------

class _MethodNotFound(Exception):
    pass


async def _dispatch(method: str, params: dict, mcp_server) -> Any:
    """Route JSON-RPC method to the appropriate handler."""

    # ── Lifecycle ──────────────────────────────────────────────────────────
    if method == "initialize":
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
            },
            "serverInfo": {
                "name": mcp_server.name,
                "version": mcp_server.version,
            },
        }

    if method in ("ping", "notifications/initialized", "notifications/cancelled"):
        # Notifications + ping return empty result
        return {}

    # ── Tools ──────────────────────────────────────────────────────────────
    if method == "tools/list":
        raw_tools = await mcp_server.list_tools()
        mcp_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t.get("inputSchema", {"type": "object", "properties": {}}),
            }
            for t in raw_tools
        ]
        return {"tools": mcp_tools}

    if method == "tools/call":
        tool_name: str = params.get("name", "")
        arguments: dict = params.get("arguments") or {}
        if not tool_name:
            raise ValueError("Missing required param 'name'")

        result = await mcp_server.call_tool(tool_name, arguments)

        # Wrap result in MCP content array format
        if isinstance(result, dict) and "error" in result:
            return {
                "content": [
                    {"type": "text", "text": f"❌ Tool error: {result['error']}"}
                ],
                "isError": True,
            }

        result_text = json.dumps(result, indent=2, default=str)
        return {
            "content": [{"type": "text", "text": result_text}],
            "isError": False,
        }

    # ── Resources ──────────────────────────────────────────────────────────
    if method == "resources/list":
        resources = await mcp_server.get_resources()
        return {"resources": resources}

    if method == "resources/read":
        uri: str = params.get("uri", "")
        if not uri:
            raise ValueError("Missing required param 'uri'")
        content = await mcp_server.read_resource(uri)
        return {
            "contents": [
                {"uri": uri, "mimeType": "application/json", "text": content}
            ]
        }

    # ── Unknown method ─────────────────────────────────────────────────────
    raise _MethodNotFound(f"Method not found: {method}")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _error(msg_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }
