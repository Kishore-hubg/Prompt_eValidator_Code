"""Adaptive Card builders — no botbuilder dependency (safe to import on Vercel)."""
from __future__ import annotations

from typing import Any

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


# ---------------------------------------------------------------------------
# Helpers
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


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------

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
