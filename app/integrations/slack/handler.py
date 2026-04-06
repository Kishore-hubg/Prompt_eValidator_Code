"""Slack Slash Command handler — validation logic and Block Kit card builder."""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.auth.persona_mapping import resolve_persona_for_user
from app.integrations.mcp.server import run_mcp_validation

_log = logging.getLogger("prompt_validator.slack.handler")

# ---------------------------------------------------------------------------
# Persona catalogue (mirrors teams_bot/bot.py)
# ---------------------------------------------------------------------------
_PERSONAS: dict[str, str] = {
    "persona_0": "All Employees",
    "persona_1": "Developer & QA",
    "persona_2": "Technical PM",
    "persona_3": "BA & PO",
    "persona_4": "Support Staff",
}

# Regex: optional "persona_N:" prefix at start of /validate text
_PERSONA_PREFIX_RE = re.compile(r"^(persona_[0-4])\s*:\s*", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Help text (shown for /validate help or empty /validate)
# ---------------------------------------------------------------------------
SLACK_HELP_TEXT = (
    "*Prompt Validator* — score and improve your prompts before sending to an LLM.\n\n"
    "*Usage:*\n"
    "• `/validate <your prompt>` — validate with your default persona\n"
    "• `/validate persona_1: <your prompt>` — validate with a specific persona\n"
    "• `/validate help` — show this message\n\n"
    "*Personas:*\n"
    "• `persona_0` — 🏢 All Employees _(default)_\n"
    "• `persona_1` — 💻 Developer & QA\n"
    "• `persona_2` — 📋 Technical PM\n"
    "• `persona_3` — 📊 BA & PO\n"
    "• `persona_4` — 🎧 Support Staff\n\n"
    "*Score bands:*  🔴 Poor (<50)  🟡 Needs Improvement (50–69)  🔵 Good (70–84)  🟢 Excellent (≥85)"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_emoji(score: float) -> str:
    if score >= 85:
        return "🟢"
    if score >= 70:
        return "🔵"
    if score >= 50:
        return "🟡"
    return "🔴"


def _rating_color_text(rating: str) -> str:
    """Map rating to Slack text decoration."""
    colors = {
        "Excellent": "🟢 *Excellent*",
        "Good": "🔵 *Good*",
        "Needs Improvement": "🟡 *Needs Improvement*",
        "Poor": "🔴 *Poor*",
    }
    return colors.get(rating, f"*{rating}*")


def parse_persona_and_prompt(text: str) -> tuple[str | None, str]:
    """Extract optional ``persona_N:`` prefix and return (persona_id, prompt).

    Examples::

        "persona_1: Write some code"  → ("persona_1", "Write some code")
        "Write some code"             → (None, "Write some code")
    """
    match = _PERSONA_PREFIX_RE.match(text.strip())
    if match:
        persona_id = match.group(1).lower()
        prompt = text[match.end():].strip()
        return persona_id, prompt
    return None, text.strip()


# ---------------------------------------------------------------------------
# Block Kit card builder
# ---------------------------------------------------------------------------

def build_block_kit_response(result: dict[str, Any], prompt_text: str) -> dict[str, Any]:
    """Build a rich Slack Block Kit message from a validation result.

    Args:
        result:      Dict returned by ``run_mcp_validation``.
        prompt_text: Original prompt submitted by the user.

    Returns:
        Slack Block Kit payload (``{"blocks": [...], "response_type": ...}``).
    """
    score: float = result.get("score", 0.0)
    rating: str = result.get("rating", "N/A")
    persona_name: str = result.get("persona_name", result.get("persona_id", "Unknown"))
    issues: list[str] = (result.get("issues") or [])[:6]
    suggestions: list[str] = (result.get("suggestions") or [])[:4]
    improved: str = (result.get("improved_prompt") or "").strip()
    dimensions: list[dict] = result.get("dimension_scores") or []
    provider: str = (result.get("llm_evaluation") or {}).get("provider", "")

    emoji = _score_emoji(score)
    rating_fmt = _rating_color_text(rating)
    score_int = int(round(score))

    blocks: list[dict[str, Any]] = []

    # ── Header ──────────────────────────────────────────────────────────────
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"{emoji} Prompt Validator  ·  Score: {score_int}/100",
            "emoji": True,
        },
    })

    # ── Score + Persona ──────────────────────────────────────────────────────
    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*Rating:*\n{rating_fmt}"},
            {"type": "mrkdwn", "text": f"*Persona:*\n{persona_name}"},
        ],
    })

    # ── Original prompt (truncated) ──────────────────────────────────────────
    prompt_display = prompt_text[:280] + ("…" if len(prompt_text) > 280 else "")
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*Your Prompt:*\n```{prompt_display}```"},
    })

    # ── Dimension breakdown (compact) ───────────────────────────────────────
    if dimensions:
        dim_lines = []
        for d in dimensions[:7]:
            passed = bool(d.get("passed"))
            name = str(d.get("name", "")).replace("_", " ").title()
            weight = int(d.get("weight", 0))
            tick = "✅" if passed else "❌"
            dim_lines.append(f"{tick} {name} _(wt: {weight})_")
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Dimension Breakdown:*\n" + "  ".join(dim_lines[:4])
                        + ("\n" + "  ".join(dim_lines[4:]) if len(dim_lines) > 4 else ""),
            },
        })

    # ── Issues ───────────────────────────────────────────────────────────────
    if issues:
        issues_text = "\n".join(f"• {i}" for i in issues)
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Issues Found:*\n{issues_text}"},
        })

    # ── Suggestions ──────────────────────────────────────────────────────────
    if suggestions:
        sug_text = "\n".join(f"• {s}" for s in suggestions)
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Suggestions:*\n{sug_text}"},
        })

    # ── Improved prompt ───────────────────────────────────────────────────────
    if improved and improved != prompt_text:
        improved_display = improved[:2800] + ("…" if len(improved) > 2800 else "")
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*✨ Improved Prompt:*\n```{improved_display}```",
            },
        })

    # ── Footer ────────────────────────────────────────────────────────────────
    provider_note = f" via {provider}" if provider else ""
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"Infovision Prompt Validator{provider_note}  ·  "
                    "Type `/validate help` for usage guide"
                ),
            }
        ],
    })

    return {
        "response_type": "in_channel",
        "blocks": blocks,
    }


# ---------------------------------------------------------------------------
# Background processor — called via FastAPI BackgroundTasks
# ---------------------------------------------------------------------------

def process_and_respond(
    db,
    prompt_text: str,
    persona_id: str,
    slack_user_id: str,
    response_url: str,
) -> None:
    """Run validation and POST the Block Kit result to Slack's response_url.

    This runs in a background thread (FastAPI BackgroundTasks) so the
    slash-command endpoint can return the 200 ACK within Slack's 3-second
    timeout while the (potentially 3–8 s) LLM call completes asynchronously.

    Args:
        db:           Database session/client from FastAPI dependency.
        prompt_text:  The raw prompt submitted by the user.
        persona_id:   Resolved persona ID string.
        slack_user_id: Slack user ID (e.g. ``U012AB3CD``) for email synthesis.
        response_url: Slack webhook URL to POST the final result.
    """
    email = f"{slack_user_id.lower()}@slack.local"

    try:
        result = run_mcp_validation(
            db,
            prompt_text=prompt_text,
            persona_id=persona_id,
            user_email=email,
            auto_improve=True,
            channel="slack",
        )
        payload = build_block_kit_response(result, prompt_text)
    except Exception as exc:  # noqa: BLE001
        _log.error("Slack validation failed: %s", exc)
        payload = {
            "response_type": "ephemeral",
            "text": (
                f"❌ Validation failed: {exc}\n"
                "Please try again. If the issue persists contact your admin."
            ),
        }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(response_url, json=payload)
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        _log.error("Failed to POST result to Slack response_url: %s", exc)


# ---------------------------------------------------------------------------
# Public entry point called from routes.py
# ---------------------------------------------------------------------------

def handle_slack_slash_command(
    db,
    *,
    text: str,
    user_id: str,
    response_url: str,
    background_tasks,
    default_persona: str = "persona_0",
) -> dict[str, Any]:
    """Parse the slash command, enqueue background validation, return ACK.

    Returns a dict that FastAPI serialises as the immediate Slack response
    (HTTP 200 + ephemeral "validating…" message shown only to the sender).

    Args:
        db:               DB session/client.
        text:             Raw text after ``/validate`` (may include persona prefix).
        user_id:          Slack user ID from the slash command payload.
        response_url:     Slack webhook for the delayed full response.
        background_tasks: FastAPI BackgroundTasks instance.
        default_persona:  Fallback persona when none specified in the command.
    """
    clean = text.strip()

    # Empty command or /validate help
    if not clean or clean.lower() == "help":
        return {"response_type": "ephemeral", "text": SLACK_HELP_TEXT}

    persona_id, prompt_text = parse_persona_and_prompt(clean)
    if not prompt_text:
        return {
            "response_type": "ephemeral",
            "text": "⚠️ Please include a prompt after `/validate`.\n" + SLACK_HELP_TEXT,
        }

    resolved_persona = persona_id or default_persona
    persona_name = _PERSONAS.get(resolved_persona, resolved_persona)

    # Enqueue validation — runs AFTER the 200 ACK is sent to Slack
    background_tasks.add_task(
        process_and_respond,
        db,
        prompt_text,
        resolved_persona,
        user_id,
        response_url,
    )

    return {
        "response_type": "ephemeral",
        "text": (
            f"⏳ Validating your prompt as *{persona_name}*...\n"
            "Result will appear in this channel shortly."
        ),
    }
