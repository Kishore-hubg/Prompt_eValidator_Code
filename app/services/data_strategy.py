from __future__ import annotations

from hashlib import sha256
from typing import Any


SOURCE_OF_TRUTH_DOC = "docs/source_of_truth/Infovision_Data_Strategy_Business_Rules.docx"
SOURCE_OF_TRUTH_SCOPE = "Day2 Data Strategy Business Rules"


def normalize_delivery_channel(channel: str) -> str:
    lowered = (channel or "").strip().lower()
    mapping = {
        "api": "API",
        "web": "API",
        "rest": "API",
        "mcp": "MCP",
        "chat": "CHAT",
        "teams": "CHAT",
        "ide": "IDE",
    }
    return mapping.get(lowered, "API")


def to_validation_score_10(score_100: float) -> float:
    # Additive Day2 field; keeps current 0-100 behavior intact.
    return round(max(0.0, min(100.0, float(score_100))) / 10.0, 2)


def _mask_email(email: str) -> str:
    value = (email or "").strip().lower()
    if not value:
        return ""
    if "@" not in value:
        return "***"
    name, domain = value.split("@", 1)
    if len(name) <= 2:
        masked = "*" * len(name)
    else:
        masked = f"{name[:2]}***"
    return f"{masked}@{domain}"


def _email_hash(email: str) -> str:
    value = (email or "").strip().lower()
    if not value:
        return ""
    return sha256(value.encode("utf-8")).hexdigest()


def build_data_governance_payload(
    *,
    user_email: str,
    channel: str,
    score_100: float,
    score_10: float,
    llm_evaluation: dict[str, Any] | None,
) -> dict[str, Any]:
    delivery_channel = normalize_delivery_channel(channel)
    return {
        "source_of_truth_scope": SOURCE_OF_TRUTH_SCOPE,
        "delivery_channel": delivery_channel,
        "validation_score_100": round(float(score_100), 2),
        "validation_score_10": round(float(score_10), 2),
        "pii_masking": {
            "enabled": True,
            "masked_user_email": _mask_email(user_email),
            "user_email_hash_sha256": _email_hash(user_email),
        },
        "llm_scoring_governance": {
            "llm_used": bool((llm_evaluation or {}).get("used")),
            "scoring_mode": (llm_evaluation or {}).get("scoring_mode"),
            "provider": (llm_evaluation or {}).get("provider"),
            "model": (llm_evaluation or {}).get("model"),
            "semantic_score_100": (llm_evaluation or {}).get("semantic_score"),
            "static_score_100": (llm_evaluation or {}).get("static_score"),
            "llm_error": (llm_evaluation or {}).get("error"),
        },
    }


def build_source_of_truth_payload() -> dict[str, Any]:
    return {
        "document_path": SOURCE_OF_TRUTH_DOC,
        "document_scope": SOURCE_OF_TRUTH_SCOPE,
        "applied_ruleset_version": "day2-v1",
    }
