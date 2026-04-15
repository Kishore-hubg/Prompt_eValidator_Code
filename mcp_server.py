"""
Prompt Validator MCP Server — HTTP Proxy Bridge

Forwards Claude Desktop's stdio JSON-RPC stream to the deployed MCP endpoint.
The actual tool logic lives in the FastAPI backend at MCP_URL.

Claude Desktop Setup (claude_desktop_config.json)
==================================================
Option A — Direct HTTP (recommended, no local script needed):
    {
      "mcpServers": {
        "prompt-validator": {
          "url": "https://promptvalidatorcompleterepo.vercel.app/mcp"
        }
      }
    }

Option B — Stdio proxy (run this script locally):
    {
      "mcpServers": {
        "prompt-validator": {
          "command": "python",
          "args": ["D:\\\\prompt_validator_complete_repo\\\\mcp_server.py"]
        }
      }
    }

Available Tools (exposed by the backend)
=========================================
  validate_prompt       — Validate + score a prompt (auto-improves by default)
  improve_prompt        — Generate structured improved version
  list_personas         — List all 5 evaluation personas
  get_persona_details   — Criteria & weights for a specific persona
  query_history         — Retrieve past validation records
  get_analytics         — Aggregate stats and trends
  save_validation       — Persist a result for audit trail
"""

import asyncio
import json
import logging
import sys

import httpx

# ── Configuration ─────────────────────────────────────────────────────────────
MCP_URL = "https://promptvalidatorcompleterepo.vercel.app/mcp"
REQUEST_TIMEOUT = 30.0

# ── Logging (stderr only — keeps stdio channel clean) ─────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[MCP-proxy] %(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
_log = logging.getLogger(__name__)


# ── Stdio helpers ─────────────────────────────────────────────────────────────

def _send(obj: dict) -> None:
    """Write a JSON-RPC object to stdout and flush."""
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _send_raw(text: str) -> None:
    """Write a pre-encoded JSON response to stdout and flush."""
    sys.stdout.write(text.strip() + "\n")
    sys.stdout.flush()


# ── Main proxy loop ───────────────────────────────────────────────────────────

async def run_proxy() -> None:
    """
    Read JSON-RPC 2.0 messages from stdin line-by-line,
    forward each to MCP_URL via HTTP POST,
    and relay the response back on stdout.
    """
    _log.info("=" * 60)
    _log.info("PROMPT VALIDATOR MCP PROXY")
    _log.info("Backend : %s", MCP_URL)
    _log.info("Mode    : stdio → HTTP bridge")
    _log.info("=" * 60)

    loop = asyncio.get_event_loop()

    # Wrap raw stdin buffer in an async StreamReader
    stdin_reader = asyncio.StreamReader()
    transport, _ = await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(stdin_reader),
        sys.stdin.buffer,
    )

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            while True:
                line = await stdin_reader.readline()
                if not line:
                    _log.info("stdin closed — shutting down proxy.")
                    break

                line = line.strip()
                if not line:
                    continue

                # Decode incoming JSON-RPC message
                try:
                    request = json.loads(line)
                except json.JSONDecodeError as exc:
                    _send({
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {exc}"},
                    })
                    continue

                method = request.get("method", "?")
                msg_id = request.get("id")
                _log.info("→ %s (id=%s)", method, msg_id)

                # Forward to HTTP MCP endpoint
                try:
                    resp = await client.post(
                        MCP_URL,
                        json=request,
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                    )
                    resp.raise_for_status()

                    # HTTP 202 = notification acknowledged — no response body per spec
                    if resp.status_code == 202:
                        _log.debug("← 202 (notification ack, no body)")
                        continue

                    _log.info("← HTTP %s for %s", resp.status_code, method)
                    _send_raw(resp.text)

                except httpx.HTTPStatusError as exc:
                    _log.error("HTTP error %s for %s: %s", exc.response.status_code, method, exc.response.text[:200])
                    _send({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32603,
                            "message": f"Backend HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                        },
                    })

                except httpx.RequestError as exc:
                    _log.error("Connection error for %s: %s", method, exc)
                    _send({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32603,
                            "message": f"Cannot reach MCP backend: {exc}",
                        },
                    })

        finally:
            transport.close()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        asyncio.run(run_proxy())
    except KeyboardInterrupt:
        _log.info("MCP proxy stopped by user.")
    except Exception as exc:
        _log.critical("Fatal error: %s", exc)
        sys.exit(1)
