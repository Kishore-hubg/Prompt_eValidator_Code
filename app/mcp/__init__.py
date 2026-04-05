"""MCP (Model Context Protocol) integration for Prompt Validator.

Exposes validation tools via MCP, enabling:
- Claude Code integration (call tools from prompts)
- Claude API integration (agents using tools)
- Teams bot integration (LangGraph agents with tool calling)
- External AI systems (any client supporting MCP)

Implementation:
- server.py: MCP server implementation
- tools.py: Tool wrappers around FastAPI endpoints
- schemas.py: Pydantic schemas for input/output validation
"""

from app.mcp.server import PromptValidatorMCPServer

__all__ = ["PromptValidatorMCPServer"]
