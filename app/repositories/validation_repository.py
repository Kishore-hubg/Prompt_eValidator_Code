from typing import Union

from pymongo.database import Database
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.settings import DATABASE_BACKEND
from app.models.db_models import (
    ChannelUsageRecord,
    DimensionScoreRecord,
    FeedbackEventRecord,
    PersonaAssignment,
    PromptRewriteRecord,
    PromptValidationRecord,
)


def analytics_summary(db: Union[Session, Database]) -> dict:
    if DATABASE_BACKEND == "mongodb":
        return _analytics_summary_mongo(db)
    return _analytics_summary_sql(db)


def _analytics_summary_sql(db: Session) -> dict:
    total_validations = db.execute(select(func.count(PromptValidationRecord.id))).scalar_one()
    total_users = db.execute(select(func.count(func.distinct(PromptValidationRecord.user_email)))).scalar_one()
    avg_score = db.execute(select(func.avg(PromptValidationRecord.score))).scalar_one() or 0.0

    persona_rows = db.execute(
        select(PromptValidationRecord.persona_id, func.count(PromptValidationRecord.id)).group_by(
            PromptValidationRecord.persona_id
        )
    ).all()
    channel_rows = db.execute(
        select(PromptValidationRecord.channel, func.count(PromptValidationRecord.id)).group_by(
            PromptValidationRecord.channel
        )
    ).all()

    return {
        "total_validations": int(total_validations),
        "distinct_users": int(total_users),
        "average_score": round(float(avg_score), 2),
        "validations_by_persona": {k: int(v) for k, v in persona_rows},
        "validations_by_channel": {k: int(v) for k, v in channel_rows},
        "tables": {
            "persona_assignments": db.execute(select(func.count(PersonaAssignment.id))).scalar_one(),
            "dimension_scores": db.execute(select(func.count(DimensionScoreRecord.id))).scalar_one(),
            "prompt_rewrites": db.execute(select(func.count(PromptRewriteRecord.id))).scalar_one(),
            "channel_usage": db.execute(select(func.count(ChannelUsageRecord.id))).scalar_one(),
            "feedback_events": db.execute(select(func.count(FeedbackEventRecord.id))).scalar_one(),
        },
    }


def _analytics_summary_mongo(db: Database) -> dict:
    pv = db.prompt_validations
    total_validations = pv.count_documents({})
    distinct_users = len(pv.distinct("user_email")) if total_validations else 0
    avg_doc = list(pv.aggregate([{"$group": {"_id": None, "avg": {"$avg": "$score"}}}]))
    avg_score = float(avg_doc[0]["avg"]) if avg_doc and avg_doc[0].get("avg") is not None else 0.0

    persona_map: dict[str, int] = {}
    for row in pv.aggregate(
        [{"$group": {"_id": "$persona_id", "c": {"$sum": 1}}}]
    ):
        pid = row["_id"] or ""
        persona_map[str(pid)] = int(row["c"])

    channel_map: dict[str, int] = {}
    for row in pv.aggregate([{"$group": {"_id": "$channel", "c": {"$sum": 1}}}]):
        ch = row["_id"] or ""
        channel_map[str(ch)] = int(row["c"])

    return {
        "total_validations": int(total_validations),
        "distinct_users": int(distinct_users),
        "average_score": round(avg_score, 2),
        "validations_by_persona": persona_map,
        "validations_by_channel": channel_map,
        "tables": {
            "persona_assignments": db.persona_assignments.count_documents({}),
            "dimension_scores": db.dimension_scores.count_documents({}),
            "prompt_rewrites": db.prompt_rewrites.count_documents({}),
            "channel_usage": db.channel_usage.count_documents({}),
            "feedback_events": db.feedback_events.count_documents({}),
        },
    }
