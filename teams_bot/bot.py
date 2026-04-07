from __future__ import annotations

import os
import sys
import json
from typing import Any

import httpx
from botbuilder.core import BotFrameworkAdapter, TurnContext
from botbuilder.core.teams import TeamsActivityHandler
from botbuilder.schema import Activity, ActivityTypes

# Allow `python path/to/teams_bot/bot.py` execution by ensuring the repo root
# (the parent of the `teams_bot/` package) is on `sys.path`.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from teams_bot.config import TeamsBotSettings

# ---------------------------------------------------------------------------
# Persona catalogue (kept in-sync with persona_criteria_source_truth.json)
# ---------------------------------------------------------------------------
PERSONAS: list[dict[str, str]] = [
    {"id": "persona_1", "name": "Developer & QA",      "emoji": "💻"},
    {"id": "persona_2", "name": "Technical PM",         "emoji": "📋"},
    {"id": "persona_3", "name": "BA & PO",              "emoji": "📊"},
    {"id": "persona_4", "name": "Support Staff",        "emoji": "🎧"},
    {"id": "persona_0", "name": "All Employees",        "emoji": "🏢"},
]

PERSONA_BY_ID: dict[str, dict[str, str]] = {p["id"]: p for p in PERSONAS}

# Per-conversation state: stores the persona the user has selected.
# Key = conversation_id, Value = persona_id string.
_conversation_persona: dict[str, str] = {}

# Last validation result per conversation — used by /last-score command.
# Key = conversation_id, Value = result dict from the validator API.
_conversation_last_result: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------
_HELP_TEXT = (
    "**Prompt Validator Bot** — validate & improve your prompts before sending them to an LLM.\n\n"
    "**Commands:**\n"
    "• `/help` — show this message\n"
    "• `/persona` — list available personas\n"
    "• `/set-persona <id>` — e.g. `/set-persona persona_1`\n"
    "• `/my-persona` — show your currently active persona\n"
    "• `/last-score` — show your last validation score\n\n"
    "**Validating a prompt:** just type or paste it and send — no command needed.\n\n"
    "**Personas:**\n"
    + "\n".join(f"• `{p['id']}` — {p['emoji']} {p['name']}" for p in PERSONAS)
)

# ---------------------------------------------------------------------------
# Adaptive Card builder
# ---------------------------------------------------------------------------

def _score_color(score: float | int) -> str:
    """Map score to an Adaptive Card accent colour."""
    if score >= 85:
        return "good"       # green
    if score >= 70:
        return "accent"     # blue
    if score >= 50:
        return "warning"    # amber
    return "attention"      # red


def _build_adaptive_card(result: dict[str, Any]) -> dict[str, Any]:
    """Return a full Adaptive Card JSON body for a validation result."""
    score: float = result.get("score", 0)
    rating: str = result.get("rating", "N/A")
    persona_name: str = result.get("persona_name", result.get("persona_id", "Unknown"))
    issues: list[str] = (result.get("issues") or [])[:6]
    suggestions: list[str] = (result.get("suggestions") or [])[:5]
    improved: str = (result.get("improved_prompt") or "").strip()
    dimensions: list[dict[str, Any]] = result.get("dimension_scores") or []

    color = _score_color(score)

    # --- Header block ---
    header_block = {
        "type": "Container",
        "style": "emphasis",
        "items": [
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {"type": "TextBlock", "text": "Prompt Validator", "weight": "Bolder",
                             "size": "Medium", "color": "Accent"},
                            {"type": "TextBlock", "text": f"Persona: {persona_name}",
                             "size": "Small", "isSubtle": True, "spacing": "None"},
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {"type": "TextBlock", "text": str(int(score)),
                             "weight": "Bolder", "size": "ExtraLarge", "color": color},
                            {"type": "TextBlock", "text": rating, "size": "Small",
                             "color": color, "spacing": "None", "horizontalAlignment": "Center"},
                        ],
                    },
                ],
            }
        ],
    }

    body: list[dict[str, Any]] = [header_block]

    # --- Dimension breakdown (compact) ---
    if dimensions:
        dim_cols: list[dict[str, Any]] = []
        for d in dimensions[:6]:
            passed = bool(d.get("passed"))
            label = str(d.get("name", "")).replace("_", " ").title()
            dim_cols.append({
                "type": "Column",
                "width": "stretch",
                "items": [
                    {"type": "TextBlock", "text": "✅" if passed else "❌",
                     "horizontalAlignment": "Center", "size": "Small"},
                    {"type": "TextBlock", "text": label,
                     "size": "Small", "wrap": True,
                     "horizontalAlignment": "Center", "isSubtle": True},
                ],
            })
        if dim_cols:
            body.append({
                "type": "Container",
                "separator": True,
                "items": [
                    {"type": "TextBlock", "text": "DIMENSIONS", "size": "Small",
                     "weight": "Bolder", "isSubtle": True, "spacing": "Medium"},
                    {"type": "ColumnSet", "columns": dim_cols},
                ],
            })

    # --- Issues ---
    if issues:
        issue_items = [
            {"type": "TextBlock", "text": f"• {issue}", "wrap": True, "size": "Small",
             "color": "Attention", "spacing": "Small"}
            for issue in issues
        ]
        body.append({
            "type": "Container",
            "separator": True,
            "items": [
                {"type": "TextBlock", "text": "ISSUES TO FIX", "size": "Small",
                 "weight": "Bolder", "isSubtle": True, "spacing": "Medium"},
                *issue_items,
            ],
        })

    # --- Suggestions ---
    if suggestions:
        sugg_items = [
            {"type": "TextBlock", "text": f"→ {s}", "wrap": True, "size": "Small",
             "color": "Accent", "spacing": "Small"}
            for s in suggestions
        ]
        body.append({
            "type": "Container",
            "separator": True,
            "items": [
                {"type": "TextBlock", "text": "SUGGESTIONS", "size": "Small",
                 "weight": "Bolder", "isSubtle": True, "spacing": "Medium"},
                *sugg_items,
            ],
        })

    # --- Improved prompt ---
    if improved:
        body.append({
            "type": "Container",
            "separator": True,
            "style": "emphasis",
            "items": [
                {"type": "TextBlock", "text": "✨ IMPROVED PROMPT", "size": "Small",
                 "weight": "Bolder", "color": "Good", "spacing": "Medium"},
                {"type": "TextBlock", "text": improved, "wrap": True, "size": "Small",
                 "fontType": "Monospace", "spacing": "Small"},
            ],
        })

    # --- Actions ---
    actions: list[dict[str, Any]] = []
    if improved:
        actions.append({
            "type": "Action.Submit",
            "title": "📋 Copy Improved Prompt",
            "data": {"action": "copy_prompt", "text": improved},
        })
    actions.append({
        "type": "Action.Submit",
        "title": "🔄 Change Persona",
        "data": {"action": "list_personas"},
    })

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
        "actions": actions if actions else [],
    }


def _build_persona_list_card() -> dict[str, Any]:
    """Adaptive Card showing the persona list with selection buttons."""
    body = [
        {"type": "TextBlock", "text": "Select Your Persona", "weight": "Bolder",
         "size": "Medium", "color": "Accent"},
        {"type": "TextBlock",
         "text": "Your persona determines the scoring dimensions applied to your prompts.",
         "wrap": True, "isSubtle": True, "size": "Small"},
    ]
    actions = [
        {
            "type": "Action.Submit",
            "title": f"{p['emoji']} {p['name']}",
            "data": {"action": "set_persona", "persona_id": p["id"]},
        }
        for p in PERSONAS
    ]
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }


def _card_activity(card: dict[str, Any]) -> Activity:
    """Wrap an Adaptive Card dict in a Bot Framework Activity."""
    return Activity(
        type=ActivityTypes.message,
        attachments=[{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card,
        }],
    )


# ---------------------------------------------------------------------------
# Bot class
# ---------------------------------------------------------------------------

class PromptValidatorTeamsBot(TeamsActivityHandler):
    def __init__(self, settings: TeamsBotSettings, adapter: BotFrameworkAdapter, db=None) -> None:
        super().__init__()
        self._settings = settings
        self._adapter = adapter
        self._db = db  # optional in-process DB session for direct service calls

    # ------------------------------------------------------------------
    # Main message handler
    # ------------------------------------------------------------------

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        text = (turn_context.activity.text or "").strip()
        # Strip @mention prefix Teams injects in channel conversations
        if text.startswith("<at>") and "</at>" in text:
            text = text[text.index("</at>") + 5:].strip()

        if not text:
            await turn_context.send_activity("Please send a prompt to validate.")
            return

        conv_id = turn_context.activity.conversation.id

        # ---- Command dispatch ----------------------------------------
        lower = text.lower()

        if lower in ("/help", "help"):
            await turn_context.send_activity(_HELP_TEXT)
            return

        if lower in ("/persona", "persona list", "/persona list"):
            await turn_context.send_activity(_card_activity(_build_persona_list_card()))
            return

        if lower.startswith("/set-persona "):
            pid = text[13:].strip().lower()
            if pid in PERSONA_BY_ID:
                _conversation_persona[conv_id] = pid
                p = PERSONA_BY_ID[pid]
                await turn_context.send_activity(
                    f"✅ Persona set to **{p['emoji']} {p['name']}** (`{pid}`).\n\n"
                    "Now just send any prompt to validate it."
                )
            else:
                valid = ", ".join(f"`{p['id']}`" for p in PERSONAS)
                await turn_context.send_activity(
                    f"Unknown persona `{pid}`. Valid options: {valid}"
                )
            return

        if lower in ("/my-persona", "my persona"):
            pid = _conversation_persona.get(conv_id)
            if pid and pid in PERSONA_BY_ID:
                p = PERSONA_BY_ID[pid]
                await turn_context.send_activity(
                    f"Your active persona: **{p['emoji']} {p['name']}** (`{pid}`)"
                )
            else:
                await turn_context.send_activity(
                    "No persona set yet. Use `/set-persona <id>` or `/persona` to choose."
                )
            return

        if lower in ("/last-score", "last score", "my score"):
            last = _conversation_last_result.get(conv_id)
            if last:
                await turn_context.send_activity(_card_activity(_build_adaptive_card(last)))
            else:
                await turn_context.send_activity(
                    "No validation yet in this conversation. Send a prompt to validate it first."
                )
            return

        # ---- Action.Submit callbacks (Adaptive Card button presses) --
        value = turn_context.activity.value
        if isinstance(value, dict):
            action = value.get("action")
            if action == "set_persona":
                pid = (value.get("persona_id") or "").strip()
                if pid in PERSONA_BY_ID:
                    _conversation_persona[conv_id] = pid
                    p = PERSONA_BY_ID[pid]
                    await turn_context.send_activity(
                        f"✅ Persona set to **{p['emoji']} {p['name']}** (`{pid}`).\n\n"
                        "Now just send any prompt to validate it."
                    )
                return
            if action == "list_personas":
                await turn_context.send_activity(_card_activity(_build_persona_list_card()))
                return
            if action == "copy_prompt":
                # Teams doesn't support clipboard directly — show the text for easy copy
                improved_text = value.get("text", "")
                if improved_text:
                    await turn_context.send_activity(
                        f"**Improved Prompt** (select all and copy):\n\n```\n{improved_text}\n```"
                    )
                return

        # ---- Treat message as a prompt to validate -------------------
        await self._validate_and_reply(turn_context, text, conv_id)

    # ------------------------------------------------------------------
    # Validation call
    # ------------------------------------------------------------------

    async def _validate_and_reply(
        self, turn_context: TurnContext, prompt_text: str, conv_id: str
    ) -> None:
        # Send typing indicator so Teams doesn't look frozen during LLM call
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))

        user_email = self._extract_user_email(turn_context)
        access_token = await self._get_access_token(turn_context)
        if self._settings.oauth_connection_name and not access_token and not user_email:
            await turn_context.send_activity(
                "I could not resolve your identity. Please sign in through Teams and try again."
            )
            return

        persona_id = _conversation_persona.get(conv_id) or None

        from_user = turn_context.activity.from_property
        teams_user_id: str | None = getattr(from_user, "aad_object_id", None) or getattr(from_user, "id", None) or None

        # Build stable email fallback from Teams AAD ID when OAuth is not configured
        email = user_email or ""
        if not email:
            if teams_user_id:
                email = f"{teams_user_id.lower().replace(' ', '-')}@teams.local"
            else:
                email = "teams-anonymous@teams.local"

        result, error_msg = await self._call_validator(prompt_text, persona_id, email)
        if error_msg:
            await turn_context.send_activity(error_msg)
            return

        _conversation_last_result[conv_id] = result
        await turn_context.send_activity(_card_activity(_build_adaptive_card(result)))

    async def _call_validator(
        self, prompt_text: str, persona_id: str | None, email: str
    ) -> tuple[dict[str, Any], str]:
        """Call the validator — in-process when db is available, HTTP otherwise.

        Returns (result_dict, error_message). Exactly one of the two is truthy.
        """
        import asyncio
        import logging as _logging
        _log = _logging.getLogger("teams_bot.bot")

        if self._db is not None:
            # In-process direct call: avoids HTTP self-round-trip on Vercel
            try:
                from app.integrations.teams.bot import handle_teams_message
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: handle_teams_message(
                        self._db,
                        user_email=email,
                        message_text=prompt_text,
                        persona_id=persona_id,
                    ),
                )
                return result, ""
            except Exception as exc:
                _log.error("In-process validation error: %s", exc, exc_info=True)
                # Fall through to HTTP fallback

        # HTTP fallback (used when running standalone or VALIDATOR_API_BASE is set explicitly)
        payload: dict[str, Any] = {
            "user_email": email or None,
            "message_text": prompt_text,
            "persona_id": persona_id,
        }
        headers = {
            "x-api-key": self._settings.validator_api_key,
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    self._settings.validator_teams_endpoint,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json(), ""
        except httpx.HTTPStatusError as exc:
            return {}, f"Validator API error ({exc.response.status_code}): {exc.response.text}"
        except Exception as exc:
            _log.error("HTTP validation error: %s", exc, exc_info=True)
            return {}, "Unable to reach the validator service right now. Please try again."

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    def _extract_user_email(self, turn_context: TurnContext) -> str:
        from_user = turn_context.activity.from_property
        if not from_user:
            return ""
        direct_email = getattr(from_user, "email", "") or ""
        if isinstance(direct_email, str) and "@" in direct_email:
            return direct_email.strip().lower()
        principal_name = getattr(from_user, "user_principal_name", "") or ""
        if isinstance(principal_name, str) and "@" in principal_name:
            return principal_name.strip().lower()
        return ""

    async def _get_access_token(self, turn_context: TurnContext) -> str | None:
        if not self._settings.oauth_connection_name:
            return None
        try:
            token_response = await self._adapter.get_user_token(
                turn_context,
                self._settings.oauth_connection_name,
            )
        except Exception:
            return None
        if not token_response:
            return None
        token = getattr(token_response, "token", None)
        return token if isinstance(token, str) and token.strip() else None
