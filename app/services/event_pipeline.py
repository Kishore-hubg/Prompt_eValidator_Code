from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import floor
from uuid import uuid4
from typing import Any

from pymongo.database import Database
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import DATABASE_BACKEND
from app.db.mongo_db import next_sequence
from app.models.db_models import DeadLetterEventRecord, EnrichedEventRecord, RawEventRecord


VALID_CHANNELS = {"API", "MCP", "CHAT", "IDE"}


@dataclass
class RawCaptureResult:
    accepted: bool
    raw_event_id: int | None
    event_id: str


def _dedupe_key(*, user_id: str, original_prompt: str, event_ts: datetime) -> str:
    bucket = floor(event_ts.timestamp() / 30)
    prompt_hash = sha256(original_prompt.encode("utf-8")).hexdigest()
    return f"{user_id}:{prompt_hash}:{bucket}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def capture_raw_event(
    db: Session | Database,
    *,
    user_id: str,
    persona_id: str,
    delivery_channel: str,
    original_prompt: str,
    source_of_truth: dict[str, Any],
) -> RawCaptureResult:
    event_id = str(uuid4())
    event_ts = _now_utc()

    if delivery_channel not in VALID_CHANNELS:
        write_dead_letter_event(
            db,
            event_id=event_id,
            user_id=user_id,
            persona_id=persona_id,
            delivery_channel=delivery_channel,
            original_prompt=original_prompt,
            error_code="INVALID_CHANNEL",
            error_reason=f"Unsupported delivery channel: {delivery_channel}",
            source_of_truth=source_of_truth,
        )
        return RawCaptureResult(accepted=False, raw_event_id=None, event_id=event_id)

    if not original_prompt.strip():
        write_dead_letter_event(
            db,
            event_id=event_id,
            user_id=user_id,
            persona_id=persona_id,
            delivery_channel=delivery_channel,
            original_prompt=original_prompt,
            error_code="REQUIRED_FIELD_NULL",
            error_reason="original_prompt is empty.",
            source_of_truth=source_of_truth,
        )
        return RawCaptureResult(accepted=False, raw_event_id=None, event_id=event_id)

    dedupe = _dedupe_key(user_id=user_id, original_prompt=original_prompt, event_ts=event_ts)
    if DATABASE_BACKEND == "mongodb":
        existing = db.raw_events.find_one({"dedupe_key": dedupe})
        if existing:
            return RawCaptureResult(accepted=False, raw_event_id=int(existing["id"]), event_id=str(existing["event_id"]))
        next_id = int(next_sequence(db, "raw_events"))
        doc = {
            "id": next_id,
            "event_id": event_id,
            "event_timestamp": event_ts,
            "user_id": user_id,
            "persona_id": persona_id,
            "delivery_channel": delivery_channel,
            "original_prompt": original_prompt,
            "dedupe_key": dedupe,
            "source_of_truth_json": json.dumps(source_of_truth or {}),
            "created_at": event_ts,
        }
        db.raw_events.insert_one(doc)
        return RawCaptureResult(accepted=True, raw_event_id=next_id, event_id=event_id)

    existing = db.execute(select(RawEventRecord).where(RawEventRecord.dedupe_key == dedupe)).scalar_one_or_none()
    if existing:
        return RawCaptureResult(accepted=False, raw_event_id=existing.id, event_id=existing.event_id)
    row = RawEventRecord(
        event_id=event_id,
        event_timestamp=event_ts,
        user_id=user_id,
        persona_id=persona_id,
        delivery_channel=delivery_channel,
        original_prompt=original_prompt,
        dedupe_key=dedupe,
        source_of_truth_json=json.dumps(source_of_truth or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return RawCaptureResult(accepted=True, raw_event_id=row.id, event_id=event_id)


def capture_enriched_event(
    db: Session | Database,
    *,
    raw_event_id: int | None,
    event_id: str,
    user_id: str,
    persona_id: str,
    team_id: str,
    delivery_channel: str,
    original_prompt: str,
    validation_score: float,
    suggestions: list[str],
    corrected_prompt: str,
    autofix_improvement_points: list[dict[str, Any]],
    llm_evaluation: dict[str, Any] | None,
    data_governance: dict[str, Any] | None,
    source_of_truth: dict[str, Any] | None,
) -> None:
    prompt_type = _derive_prompt_type(persona_id)
    complexity = _derive_complexity_class(original_prompt)
    suggestion_count = len(suggestions)
    autofix_flag = bool(corrected_prompt and corrected_prompt.strip() and corrected_prompt.strip() != original_prompt.strip())

    payload = {
        "event_id": event_id,
        "event_timestamp": _now_utc(),
        "user_id": user_id,
        "persona_id": persona_id,
        "team_id": team_id,
        "delivery_channel": delivery_channel,
        "original_prompt": original_prompt,
        "prompt_type_classification": prompt_type,
        "prompt_complexity_class": complexity,
        "validation_score": round(float(validation_score), 2),
        "suggestion_count": suggestion_count,
        "suggestions_json": json.dumps(suggestions),
        "corrected_prompt": corrected_prompt or "",
        "autofix_improvement_points_json": json.dumps(autofix_improvement_points or []),
        "score_delta": 0.0,
        "suggestion_acceptance_rate": 0.0,
        "autofix_utilization_flag": autofix_flag,
        "intervention_flag": False,
        "llm_evaluation_json": json.dumps(llm_evaluation or {}),
        "data_governance_json": json.dumps(data_governance or {}),
        "source_of_truth_json": json.dumps(source_of_truth or {}),
        "created_at": _now_utc(),
    }

    if DATABASE_BACKEND == "mongodb":
        next_id = int(next_sequence(db, "enriched_events"))
        payload["id"] = next_id
        payload["raw_event_id"] = int(raw_event_id or 0)
        db.enriched_events.insert_one(payload)
        return

    row = EnrichedEventRecord(
        raw_event_id=(int(raw_event_id) if raw_event_id is not None else None),
        event_id=str(payload["event_id"]),
        event_timestamp=payload["event_timestamp"],
        user_id=str(payload["user_id"]),
        persona_id=str(payload["persona_id"]),
        team_id=str(payload["team_id"]),
        delivery_channel=str(payload["delivery_channel"]),
        original_prompt=str(payload["original_prompt"]),
        prompt_type_classification=str(payload["prompt_type_classification"]),
        prompt_complexity_class=str(payload["prompt_complexity_class"]),
        validation_score=float(payload["validation_score"]),
        suggestion_count=int(payload["suggestion_count"]),
        suggestions_json=str(payload["suggestions_json"]),
        corrected_prompt=str(payload["corrected_prompt"]),
        autofix_improvement_points_json=str(payload["autofix_improvement_points_json"]),
        score_delta=float(payload["score_delta"]),
        suggestion_acceptance_rate=float(payload["suggestion_acceptance_rate"]),
        autofix_utilization_flag=bool(payload["autofix_utilization_flag"]),
        intervention_flag=bool(payload["intervention_flag"]),
        llm_evaluation_json=str(payload["llm_evaluation_json"]),
        data_governance_json=str(payload["data_governance_json"]),
        source_of_truth_json=str(payload["source_of_truth_json"]),
    )
    db.add(row)
    db.commit()


def write_dead_letter_event(
    db: Session | Database,
    *,
    event_id: str,
    user_id: str,
    persona_id: str,
    delivery_channel: str,
    original_prompt: str,
    error_code: str,
    error_reason: str,
    source_of_truth: dict[str, Any],
) -> None:
    if DATABASE_BACKEND == "mongodb":
        next_id = int(next_sequence(db, "dead_letter_events"))
        db.dead_letter_events.insert_one(
            {
                "id": next_id,
                "event_id": event_id,
                "user_id": user_id,
                "persona_id": persona_id,
                "delivery_channel": delivery_channel,
                "original_prompt": original_prompt,
                "error_code": error_code,
                "error_reason": error_reason,
                "source_of_truth_json": json.dumps(source_of_truth or {}),
                "created_at": _now_utc(),
            }
        )
        return
    row = DeadLetterEventRecord(
        event_id=event_id,
        user_id=user_id,
        persona_id=persona_id,
        delivery_channel=delivery_channel,
        original_prompt=original_prompt,
        error_code=error_code,
        error_reason=error_reason,
        source_of_truth_json=json.dumps(source_of_truth or {}),
    )
    db.add(row)
    db.commit()


def _derive_prompt_type(persona_id: str) -> str:
    mapping = {
        "persona_1": "TECHNICAL_IMPLEMENTATION",
        "persona_2": "PROGRAM_MANAGEMENT",
        "persona_3": "REQUIREMENTS_ANALYSIS",
        "persona_4": "SUPPORT_COMMUNICATION",
    }
    return mapping.get(persona_id, "GENERAL_INSTRUCTION")


def _derive_complexity_class(prompt_text: str) -> str:
    length = len((prompt_text or "").split())
    if length < 30:
        return "SIMPLE"
    if length < 120:
        return "MODERATE"
    return "COMPLEX"
