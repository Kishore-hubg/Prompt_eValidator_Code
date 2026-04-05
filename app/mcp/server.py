"""MCP Server - Exposes Prompt Validator as Model Context Protocol.

This server implements the MCP protocol, allowing Claude Code, Claude API,
Teams bot, and other AI systems to call validation tools in a standardized way.

The server wraps existing FastAPI endpoints without modifying them.
Runs alongside FastAPI on port 8001 (or as Vercel function).
"""

import json
import logging
from typing import Any, Optional

from app.mcp.tools import MCP_TOOLS
from app.db.database import SessionLocal
from app.core.settings import DATABASE_BACKEND

_log = logging.getLogger("prompt_validator.mcp")


class PromptValidatorMCPServer:
    """MCP Server implementation for Prompt Validator."""

    def __init__(self):
        self.name = "prompt-validator"
        self.version = "1.0.0"
        self.tools = MCP_TOOLS

    async def get_db(self):
        """Get database connection (MongoDB or SQLite)."""
        if DATABASE_BACKEND == "mongodb":
            from app.db.mongo_db import get_mongo_database
            return get_mongo_database()
        db = SessionLocal()
        try:
            return db
        finally:
            pass  # Keep connection open for tool execution

    async def list_tools(self) -> list[dict]:
        """
        MCP: list_tools

        Returns list of all available tools with descriptions and schemas.
        Called by Claude Code, Claude API, or Teams bot to discover capabilities.
        """
        tools = []
        for tool_name, tool_config in self.tools.items():
            tools.append({
                "name": tool_name,
                "description": tool_config["description"],
                "inputSchema": {
                    "type": "object",
                    "properties": tool_config["input_schema"].get("properties", {}),
                    "required": tool_config["input_schema"].get("required", []),
                },
                "outputSchema": tool_config["output_schema"],
            })
        return tools

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        MCP: call_tool

        Execute a tool with given arguments.
        Returns result in standard JSON format.
        """
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        tool_config = self.tools[tool_name]
        tool_fn = tool_config["function"]

        try:
            db = await self.get_db()

            # Call the tool with database and arguments
            if tool_name in ["list_personas"]:
                # Tools that don't need parsed input
                result = await tool_fn(db) if hasattr(tool_fn, '__call__') else tool_fn(db)
            else:
                # Tools that need parsed input
                # Parse arguments into proper Pydantic model
                input_model = self._get_input_model(tool_name)
                if input_model:
                    parsed_input = input_model(**arguments)
                    result = await tool_fn(db, parsed_input)
                else:
                    result = await tool_fn(db, **arguments)

            # Convert result to dict
            if hasattr(result, "model_dump"):
                return result.model_dump(mode="json")
            return result

        except Exception as e:
            _log.error(f"Tool error in {tool_name}: {e}", exc_info=True)
            return {
                "error": str(e),
                "tool": tool_name,
                "status": "failed"
            }

    def _get_input_model(self, tool_name: str):
        """Get Pydantic input model for a tool."""
        models = {
            "validate_prompt": self._import_class("app.mcp.schemas.ValidatePromptInput"),
            "improve_prompt": self._import_class("app.mcp.schemas.ImprovePromptInput"),
            "get_persona_details": self._import_class("app.mcp.schemas.GetPersonaDetailsInput"),
            "query_history": self._import_class("app.mcp.schemas.QueryHistoryInput"),
            "get_analytics": self._import_class("app.mcp.schemas.GetAnalyticsInput"),
            "save_validation": self._import_class("app.mcp.schemas.SaveValidationInput"),
        }
        return models.get(tool_name)

    @staticmethod
    def _import_class(path: str):
        """Dynamically import a class from a module path."""
        parts = path.rsplit(".", 1)
        if len(parts) != 2:
            return None
        module_path, class_name = parts
        try:
            module = __import__(module_path, fromlist=[class_name])
            return getattr(module, class_name)
        except ImportError:
            return None

    async def get_resources(self) -> list[dict]:
        """
        MCP: get_resources (optional)

        Return available resources (e.g., documentation, samples).
        Useful for providing context to AI models.
        """
        return [
            {
                "uri": "prompt-validator://personas",
                "name": "Available Personas",
                "description": "List of evaluation personas: All, Developer, PM, BA, Support",
                "mimeType": "application/json",
            },
            {
                "uri": "prompt-validator://examples",
                "name": "Example Prompts",
                "description": "Example prompts and their validation results",
                "mimeType": "application/json",
            },
        ]

    async def read_resource(self, uri: str) -> str:
        """
        MCP: read_resource (optional)

        Read content of a resource by URI.
        """
        if uri == "prompt-validator://personas":
            tool_result = await self.call_tool("list_personas", {})
            return json.dumps(tool_result, indent=2)
        elif uri == "prompt-validator://examples":
            return json.dumps({
                "examples": [
                    {
                        "prompt": "Create a DevOps pipeline for microservices",
                        "personas_good_for": ["Developer", "PM"],
                        "areas_to_improve": ["Specificity", "Resource requirements"],
                    },
                    {
                        "prompt": "Implement an authentication system",
                        "personas_good_for": ["Developer"],
                        "areas_to_improve": ["Security requirements", "Compliance"],
                    },
                ]
            }, indent=2)
        return ""


# ─── STANDALONE SERVER (FOR LOCAL TESTING) ──────────────────────────────────


async def run_mcp_server():
    """
    Run MCP server standalone (for development/testing).

    Production: Use Vercel serverless function wrapper.
    Development: Use this for local testing.
    """
    server = PromptValidatorMCPServer()

    # Example: List tools
    tools = await server.list_tools()
    print(f"MCP Server initialized with {len(tools)} tools:")
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description']}")

    return server


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_mcp_server())
