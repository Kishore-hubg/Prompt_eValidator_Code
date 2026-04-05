"""Teams Bot LangGraph Agent with MCP Integration.

This agent implements multi-step reasoning for the Teams bot using LangGraph.
It uses MCP tools to validate and improve prompts, then generates intelligent responses.

The agent can:
1. Validate a prompt against multiple personas
2. Identify issues and improvement areas
3. Generate an improved version
4. Provide personalized recommendations
"""

import json
import logging
from typing import Optional

_log = logging.getLogger("teams_bot.agent")


class PromptValidatorAgent:
    """
    LangGraph-based agent for Teams bot.

    Orchestrates multi-step prompt validation and improvement workflows.
    Uses MCP tools for validation logic while handling Teams-specific integration.
    """

    def __init__(self, mcp_client=None):
        """
        Initialize the agent.

        Args:
            mcp_client: Optional MCP client for calling validation tools.
                       If not provided, will use direct HTTP calls.
        """
        self.mcp_client = mcp_client
        self.mcp_endpoint = "http://localhost:8000/mcp"

    async def validate_prompt_workflow(
        self,
        prompt_text: str,
        persona_id: str = "persona_0",
        user_email: Optional[str] = None
    ) -> dict:
        """
        Multi-step workflow: Validate → Analyze → Suggest.

        Step 1: Validate prompt
        Step 2: Extract key issues
        Step 3: Provide personalized suggestions
        """
        try:
            # Step 1: Validate
            validation_result = await self.call_mcp_tool(
                "validate_prompt",
                {
                    "prompt_text": prompt_text,
                    "persona_id": persona_id,
                    "user_email": user_email,
                    "channel": "teams"
                }
            )

            if not validation_result or "error" in validation_result:
                return {
                    "status": "error",
                    "message": "Failed to validate prompt",
                    "error": validation_result.get("error", "Unknown error")
                }

            # Step 2: Extract insights
            score = validation_result.get("score", 0.0)
            rating = validation_result.get("rating", "Poor")
            issues = validation_result.get("issues", [])
            suggestions = validation_result.get("suggestions", [])

            # Step 3: Format response for Teams
            return {
                "status": "success",
                "score": score,
                "rating": rating,
                "issue_count": len(issues),
                "issues": issues[:3],  # Top 3 issues for Teams
                "suggestions": suggestions[:3],  # Top 3 suggestions
                "recommendation": self._generate_recommendation(score, rating)
            }

        except Exception as e:
            _log.error(f"Validation workflow error: {e}")
            return {"status": "error", "message": str(e)}

    async def improve_prompt_workflow(
        self,
        prompt_text: str,
        persona_id: str = "persona_0"
    ) -> dict:
        """
        Multi-step workflow: Validate → Improve → Compare.

        Step 1: Validate original prompt
        Step 2: Generate improvement
        Step 3: Compare before/after
        """
        try:
            # Step 1: Validate original
            original = await self.call_mcp_tool(
                "validate_prompt",
                {"prompt_text": prompt_text, "persona_id": persona_id, "channel": "teams"}
            )

            # Step 2: Improve
            improved_result = await self.call_mcp_tool(
                "improve_prompt",
                {"prompt_text": prompt_text, "persona_id": persona_id}
            )

            if not improved_result or "error" in improved_result:
                return {"status": "error", "message": "Failed to improve prompt"}

            # Step 3: Validate improved version
            improved_text = improved_result.get("improved_prompt", prompt_text)
            improved_validation = await self.call_mcp_tool(
                "validate_prompt",
                {"prompt_text": improved_text, "persona_id": persona_id, "channel": "teams"}
            )

            return {
                "status": "success",
                "original_score": original.get("score", 0),
                "improved_score": improved_validation.get("score", 0),
                "improvement": improved_validation.get("score", 0) - original.get("score", 0),
                "improved_prompt": improved_text,
                "changes": improved_result.get("changes", []),
                "rationale": improved_result.get("improvement_rationale", "")
            }

        except Exception as e:
            _log.error(f"Improve workflow error: {e}")
            return {"status": "error", "message": str(e)}

    async def get_personas_workflow(self) -> dict:
        """
        Get available personas for the user to choose from.
        """
        try:
            personas = await self.call_mcp_tool("list_personas", {})

            if "error" in personas:
                return {"status": "error", "message": "Failed to fetch personas"}

            persona_list = personas.get("personas", [])
            return {
                "status": "success",
                "personas": [
                    {
                        "id": p.get("persona_id"),
                        "name": p.get("name"),
                        "description": p.get("description")
                    }
                    for p in persona_list
                ],
                "count": len(persona_list)
            }

        except Exception as e:
            _log.error(f"Get personas error: {e}")
            return {"status": "error", "message": str(e)}

    async def analytics_workflow(self) -> dict:
        """
        Get validation analytics and trends.
        """
        try:
            analytics = await self.call_mcp_tool("get_analytics", {"time_period": "month"})

            if "error" in analytics:
                return {"status": "error", "message": "Failed to fetch analytics"}

            return {
                "status": "success",
                "total_validations": analytics.get("total_validations", 0),
                "average_score": analytics.get("average_score", 0),
                "trend": analytics.get("trend", "stable"),
                "by_persona": analytics.get("validations_by_persona", {})
            }

        except Exception as e:
            _log.error(f"Analytics workflow error: {e}")
            return {"status": "error", "message": str(e)}

    async def call_mcp_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        Call an MCP tool via HTTP endpoint or direct client.

        Handles both modes:
        - HTTP mode: POST /mcp/call-tool
        - Direct mode: Via MCP client library
        """
        try:
            if self.mcp_client:
                # Direct client mode (for agents with MCP library)
                return await self.mcp_client.call_tool(tool_name, arguments)
            else:
                # HTTP mode (standard)
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.mcp_endpoint}/call-tool",
                        json={"tool_name": tool_name, "arguments": arguments}
                    ) as resp:
                        data = await resp.json()
                        return data.get("result", {})

        except Exception as e:
            _log.error(f"MCP tool call error ({tool_name}): {e}")
            return {"error": str(e)}

    @staticmethod
    def _generate_recommendation(score: float, rating: str) -> str:
        """Generate a recommendation based on validation score."""
        if score >= 0.8:
            return "Excellent! Your prompt is well-structured and clear. Ready to use."
        elif score >= 0.6:
            return "Good prompt! Consider the suggestions above to make it even better."
        elif score >= 0.4:
            return "Your prompt needs improvement. Focus on clarity and specificity."
        else:
            return "This prompt needs significant revision. Use the improvement suggestion."

    def format_teams_response(self, workflow_result: dict, title: str) -> str:
        """
        Format agent output for Teams message.

        Converts structured result to Teams-friendly markdown.
        """
        if workflow_result.get("status") == "error":
            return f"❌ {title}: {workflow_result.get('message')}"

        lines = [f"**{title}**"]

        if "score" in workflow_result:
            score = workflow_result["score"]
            rating = workflow_result.get("rating", "")
            lines.append(f"\n📊 Score: **{score}** ({rating})")

        if "issues" in workflow_result and workflow_result["issues"]:
            lines.append(f"\n⚠️ Issues:")
            for issue in workflow_result["issues"][:3]:
                lines.append(f"  • {issue}")

        if "suggestions" in workflow_result and workflow_result["suggestions"]:
            lines.append(f"\n💡 Suggestions:")
            for suggestion in workflow_result["suggestions"][:3]:
                lines.append(f"  • {suggestion}")

        if "recommendation" in workflow_result:
            lines.append(f"\n✨ {workflow_result['recommendation']}")

        if "improvement" in workflow_result:
            improvement = workflow_result["improvement"]
            emoji = "📈" if improvement > 0 else "📉"
            lines.append(f"\n{emoji} Score change: {improvement:+.2f}")

        return "\n".join(lines)
