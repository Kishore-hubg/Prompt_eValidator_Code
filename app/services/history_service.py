import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Union

from pymongo.database import Database
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import DATABASE_BACKEND
from app.db.mongo_db import next_sequence
from app.models.db_models import (
    ChannelUsageRecord,
    DimensionScoreRecord,
    FeedbackEventRecord,
    PromptRewriteRecord,
    PromptValidationRecord,
)


@dataclass
class HistoryRow:
    id: int
    persona_id: str
    channel: str
    score: float
    rating: str
    prompt_text: str
    improved_prompt: str
    created_at: datetime


def save_validation(
    db: Union[Session, Database],
    *,
    persona_id: str,
    channel: str,
    prompt_text: str,
    score: float,
    rating: str,
    issues: list[str],
    suggestions: list[str],
    improved_prompt: str,
    dimension_scores: list[dict],
    user_email: str = "",
    llm_evaluation: dict[str, Any] | None = None,
    data_governance: dict[str, Any] | None = None,
    source_of_truth: dict[str, Any] | None = None,
    delivery_channel: str = "API",
    validation_score_10: float = 0.0,
    rewrite_strategy: str = "template",
    rewrite_metadata: dict[str, Any] | None = None,
) -> Any:
    if DATABASE_BACKEND == "mongodb":
        return _save_validation_mongo(
            db,
            persona_id=persona_id,
            channel=channel,
            prompt_text=prompt_text,
            score=score,
            rating=rating,
            issues=issues,
            suggestions=suggestions,
            improved_prompt=improved_prompt,
            dimension_scores=dimension_scores,
            user_email=user_email,
            llm_evaluation=llm_evaluation,
            data_governance=data_governance,
            source_of_truth=source_of_truth,
            delivery_channel=delivery_channel,
            validation_score_10=validation_score_10,
            rewrite_strategy=rewrite_strategy,
            rewrite_metadata=rewrite_metadata,
        )
    return _save_validation_sql(
        db,
        persona_id=persona_id,
        channel=channel,
        prompt_text=prompt_text,
        score=score,
        rating=rating,
        issues=issues,
        suggestions=suggestions,
        improved_prompt=improved_prompt,
        dimension_scores=dimension_scores,
        user_email=user_email,
        llm_evaluation=llm_evaluation,
        data_governance=data_governance,
        source_of_truth=source_of_truth,
        delivery_channel=delivery_channel,
        validation_score_10=validation_score_10,
        rewrite_strategy=rewrite_strategy,
        rewrite_metadata=rewrite_metadata,
    )


def _save_validation_sql(
    db: Session,
    *,
    persona_id: str,
    channel: str,
    prompt_text: str,
    score: float,
    rating: str,
    issues: list[str],
    suggestions: list[str],
    improved_prompt: str,
    dimension_scores: list[dict],
    user_email: str,
    llm_evaluation: dict[str, Any] | None,
    data_governance: dict[str, Any] | None,
    source_of_truth: dict[str, Any] | None,
    delivery_channel: str,
    validation_score_10: float,
    rewrite_strategy: str,
    rewrite_metadata: dict[str, Any] | None,
):
    record = PromptValidationRecord(
        persona_id=persona_id,
        channel=channel,
        prompt_text=prompt_text,
        score=score,
        rating=rating,
        issues_json=json.dumps(issues),
        suggestions_json=json.dumps(suggestions),
        improved_prompt=improved_prompt,
        user_email=user_email,
        issue_count=len(issues),
        delivery_channel=delivery_channel,
        validation_score_10=validation_score_10,
        llm_evaluation_json=json.dumps(llm_evaluation or {}),
        data_governance_json=json.dumps(data_governance or {}),
        source_of_truth_json=json.dumps(source_of_truth or {}),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    for dim in dimension_scores:
        db.add(
            DimensionScoreRecord(
                validation_id=record.id,
                persona_id=persona_id,
                dimension_name=dim.get("name", ""),
                score=float(dim.get("score", 0.0)),
                weight=float(dim.get("weight", 0.0)),
                passed=bool(dim.get("passed", False)),
                notes=dim.get("notes") or "",
            )
        )

    db.add(
        PromptRewriteRecord(
            validation_id=record.id,
            persona_id=persona_id,
            original_prompt=prompt_text,
            improved_prompt=improved_prompt,
            rewrite_strategy=rewrite_strategy or "template",
            rewrite_metadata_json=json.dumps(rewrite_metadata or {}),
        )
    )
    db.add(
        ChannelUsageRecord(
            channel=channel,
            persona_id=persona_id,
            user_email=user_email,
            event_type="validation",
        )
    )
    db.add(
        FeedbackEventRecord(
            validation_id=record.id,
            persona_id=persona_id,
            event_type="issues_generated",
            message=f"{len(issues)} issues identified",
        )
    )
    db.commit()
    return record


def _save_validation_mongo(
    db: Database,
    *,
    persona_id: str,
    channel: str,
    prompt_text: str,
    score: float,
    rating: str,
    issues: list[str],
    suggestions: list[str],
    improved_prompt: str,
    dimension_scores: list[dict],
    user_email: str,
    llm_evaluation: dict[str, Any] | None,
    data_governance: dict[str, Any] | None,
    source_of_truth: dict[str, Any] | None,
    delivery_channel: str,
    validation_score_10: float,
    rewrite_strategy: str,
    rewrite_metadata: dict[str, Any] | None,
):
    vid = next_sequence(db, "prompt_validations")
    now = datetime.utcnow()
    doc = {
        "id": vid,
        "persona_id": persona_id,
        "channel": channel,
        "prompt_text": prompt_text,
        "score": score,
        "rating": rating,
        "issues_json": json.dumps(issues),
        "suggestions_json": json.dumps(suggestions),
        "improved_prompt": improved_prompt,
        "user_email": user_email,
        "issue_count": len(issues),
        "delivery_channel": delivery_channel,
        "validation_score_10": validation_score_10,
        "llm_evaluation_json": json.dumps(llm_evaluation or {}),
        "data_governance_json": json.dumps(data_governance or {}),
        "source_of_truth_json": json.dumps(source_of_truth or {}),
        "created_at": now,
    }
    db.prompt_validations.insert_one(doc)

    for dim in dimension_scores:
        db.dimension_scores.insert_one(
            {
                "validation_id": vid,
                "persona_id": persona_id,
                "dimension_name": dim.get("name", ""),
                "score": float(dim.get("score", 0.0)),
                "weight": float(dim.get("weight", 0.0)),
                "passed": bool(dim.get("passed", False)),
                "notes": dim.get("notes") or "",
                "created_at": now,
            }
        )

    db.prompt_rewrites.insert_one(
        {
            "validation_id": vid,
            "persona_id": persona_id,
            "original_prompt": prompt_text,
            "improved_prompt": improved_prompt,
            "rewrite_strategy": rewrite_strategy or "template",
            "rewrite_metadata_json": json.dumps(rewrite_metadata or {}),
            "created_at": now,
        }
    )
    db.channel_usage.insert_one(
        {
            "channel": channel,
            "persona_id": persona_id,
            "user_email": user_email,
            "event_type": "validation",
            "created_at": now,
        }
    )
    db.feedback_events.insert_one(
        {
            "validation_id": vid,
            "persona_id": persona_id,
            "event_type": "issues_generated",
            "message": f"{len(issues)} issues identified",
            "created_at": now,
        }
    )
    return doc


def fetch_history(db: Union[Session, Database], limit: int = 50) -> List[HistoryRow]:
    if DATABASE_BACKEND == "mongodb":
        return _fetch_history_mongo(db, limit)
    return _fetch_history_sql(db, limit)


def _fetch_history_sql(db: Session, limit: int) -> List[HistoryRow]:
    stmt = select(PromptValidationRecord).order_by(PromptValidationRecord.created_at.desc()).limit(limit)
    rows = list(db.execute(stmt).scalars().all())
    return [
        HistoryRow(
            id=r.id,
            persona_id=r.persona_id,
            channel=r.channel,
            score=r.score,
            rating=r.rating,
            prompt_text=r.prompt_text,
            improved_prompt=r.improved_prompt,
            created_at=r.created_at,
        )
        for r in rows
    ]


def _fetch_history_mongo(db: Database, limit: int) -> List[HistoryRow]:
    cursor = (
        db.prompt_validations.find().sort("created_at", -1).limit(limit)
    )
    out: List[HistoryRow] = []
    for doc in cursor:
        created = doc.get("created_at")
        if created is None:
            continue
        out.append(
            HistoryRow(
                id=int(doc["id"]),
                persona_id=doc.get("persona_id", ""),
                channel=doc.get("channel", "web"),
                score=float(doc.get("score", 0.0)),
                rating=doc.get("rating", ""),
                prompt_text=doc.get("prompt_text", ""),
                improved_prompt=doc.get("improved_prompt", ""),
                created_at=created,
            )
        )
    return out
