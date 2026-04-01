from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Union

from pymongo.database import Database
from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.orm import Session

from app.core.settings import DATABASE_BACKEND
from app.models.db_models import EnrichedEventRecord, WeeklyIntelligenceRecord


def _week_start_utc(dt: datetime) -> datetime:
    base = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    start = base - timedelta(days=base.weekday())
    return datetime(start.year, start.month, start.day)


def _week_start_str(dt: datetime) -> str:
    return _week_start_utc(dt).strftime("%Y-%m-%d")


def _ewma(values: list[float], *, span: int = 4) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (span + 1.0)
    acc = values[0]
    for value in values[1:]:
        acc = (alpha * value) + ((1.0 - alpha) * acc)
    return round(acc, 2)


def refresh_weekly_intelligence(db: Union[Session, Database], *, week_start: str | None = None) -> dict:
    target_week = week_start or _week_start_str(datetime.utcnow())
    if DATABASE_BACKEND == "mongodb":
        return _refresh_weekly_mongo(db, target_week)
    return _refresh_weekly_sql(db, target_week)


def _refresh_weekly_sql(db: Session, week_start: str) -> dict:
    week_start_dt = datetime.fromisoformat(week_start)
    week_end_dt = week_start_dt + timedelta(days=7)
    prev_4w_start = week_start_dt - timedelta(days=28)

    rows = db.execute(
        select(
            EnrichedEventRecord.user_id,
            func.count(EnrichedEventRecord.id),
            func.avg(EnrichedEventRecord.validation_score),
        ).where(
            and_(
                EnrichedEventRecord.event_timestamp >= week_start_dt,
                EnrichedEventRecord.event_timestamp < week_end_dt,
            )
        ).group_by(EnrichedEventRecord.user_id)
    ).all()

    db.execute(delete(WeeklyIntelligenceRecord).where(WeeklyIntelligenceRecord.week_start_date == week_start))
    for user_id, event_count, avg_score in rows:
        user = user_id or ""
        current_avg = round(float(avg_score or 0.0), 2)
        rolling_prev = db.execute(
            select(func.avg(EnrichedEventRecord.validation_score)).where(
                and_(
                    EnrichedEventRecord.user_id == user,
                    EnrichedEventRecord.event_timestamp >= prev_4w_start,
                    EnrichedEventRecord.event_timestamp < week_start_dt,
                )
            )
        ).scalar_one()
        rolling_avg = float(rolling_prev) if rolling_prev is not None else current_avg
        score_delta = round(current_avg - rolling_avg, 2)

        prev_deltas = db.execute(
            select(WeeklyIntelligenceRecord.score_delta)
            .where(WeeklyIntelligenceRecord.user_id == user)
            .order_by(desc(WeeklyIntelligenceRecord.week_start_date))
            .limit(3)
        ).scalars().all()
        delta_series = [float(x) for x in reversed(prev_deltas)] + [score_delta]
        learning_velocity = _ewma(delta_series, span=4) if len(delta_series) >= 3 else 0.0

        prev_velocities = db.execute(
            select(WeeklyIntelligenceRecord.learning_velocity)
            .where(WeeklyIntelligenceRecord.user_id == user)
            .order_by(desc(WeeklyIntelligenceRecord.week_start_date))
            .limit(2)
        ).scalars().all()
        velocity_series = [learning_velocity] + [float(v or 0.0) for v in prev_velocities]
        intervention_flag = len(velocity_series) >= 3 and all(v < 0 for v in velocity_series[:3])

        db.add(
            WeeklyIntelligenceRecord(
                user_id=user,
                week_start_date=week_start,
                weekly_active_user_flag=bool((event_count or 0) >= 1),
                score_delta=score_delta,
                learning_velocity=learning_velocity,
                intervention_flag=bool(intervention_flag),
            )
        )
    db.commit()
    return {"week_start_date": week_start, "records_upserted": len(rows)}


def _refresh_weekly_mongo(db: Database, week_start: str) -> dict:
    week_start_dt = datetime.fromisoformat(week_start)
    week_end_dt = week_start_dt + timedelta(days=7)
    prev_4w_start = week_start_dt - timedelta(days=28)
    pipeline = [
        {
            "$match": {
                "event_timestamp": {"$gte": week_start_dt, "$lt": week_end_dt},
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "event_count": {"$sum": 1},
                "avg_score": {"$avg": "$validation_score"},
            }
        },
    ]
    rows = list(db.enriched_events.aggregate(pipeline))
    db.weekly_intelligence_records.delete_many({"week_start_date": week_start})
    for row in rows:
        user = row.get("_id") or ""
        current_avg = round(float(row.get("avg_score") or 0.0), 2)
        prev_avg_rows = list(
            db.enriched_events.aggregate(
                [
                    {
                        "$match": {
                            "user_id": user,
                            "event_timestamp": {"$gte": prev_4w_start, "$lt": week_start_dt},
                        }
                    },
                    {"$group": {"_id": None, "avg_score": {"$avg": "$validation_score"}}},
                ]
            )
        )
        rolling_avg = float(prev_avg_rows[0]["avg_score"]) if prev_avg_rows else current_avg
        score_delta = round(current_avg - rolling_avg, 2)

        prev_records = list(
            db.weekly_intelligence_records.find({"user_id": user}).sort("week_start_date", -1).limit(3)
        )
        prev_deltas = [float(r.get("score_delta", 0.0)) for r in reversed(prev_records)]
        delta_series = prev_deltas + [score_delta]
        learning_velocity = _ewma(delta_series, span=4) if len(delta_series) >= 3 else 0.0

        prev_velocities = [float(r.get("learning_velocity", 0.0)) for r in prev_records[:2]]
        velocity_series = [learning_velocity] + prev_velocities
        intervention_flag = len(velocity_series) >= 3 and all(v < 0 for v in velocity_series[:3])

        db.weekly_intelligence_records.insert_one(
            {
                "user_id": user,
                "week_start_date": week_start,
                "weekly_active_user_flag": bool((row.get("event_count") or 0) >= 1),
                "score_delta": score_delta,
                "learning_velocity": learning_velocity,
                "intervention_flag": intervention_flag,
                "created_at": datetime.utcnow(),
            }
        )
    return {"week_start_date": week_start, "records_upserted": len(rows)}


def user_weekly_summary(db: Union[Session, Database], *, user_id: str, week_start: str | None = None) -> dict:
    target_week = week_start or _week_start_str(datetime.utcnow())
    if DATABASE_BACKEND == "mongodb":
        row = db.weekly_intelligence_records.find_one({"user_id": user_id, "week_start_date": target_week}) or {}
        return {
            "user_id": user_id,
            "week_start_date": target_week,
            "weekly_active_user_flag": bool(row.get("weekly_active_user_flag")),
            "score_delta": float(row.get("score_delta", 0.0)),
            "learning_velocity": float(row.get("learning_velocity", 0.0)),
            "intervention_flag": bool(row.get("intervention_flag", False)),
        }

    row = db.execute(
        select(WeeklyIntelligenceRecord).where(
            WeeklyIntelligenceRecord.user_id == user_id,
            WeeklyIntelligenceRecord.week_start_date == target_week,
        )
    ).scalar_one_or_none()
    if not row:
        return {
            "user_id": user_id,
            "week_start_date": target_week,
            "weekly_active_user_flag": False,
            "score_delta": 0.0,
            "learning_velocity": 0.0,
            "intervention_flag": False,
        }
    return {
        "user_id": row.user_id,
        "week_start_date": row.week_start_date,
        "weekly_active_user_flag": bool(row.weekly_active_user_flag),
        "score_delta": float(row.score_delta),
        "learning_velocity": float(row.learning_velocity),
        "intervention_flag": bool(row.intervention_flag),
    }


def leaderboard_weekly(db: Union[Session, Database], *, week_start: str | None = None, limit: int = 10) -> list[dict]:
    target_week = week_start or _week_start_str(datetime.utcnow())
    if DATABASE_BACKEND == "mongodb":
        cursor = (
            db.weekly_intelligence_records.find({"week_start_date": target_week})
            .sort("score_delta", -1)
            .limit(limit)
        )
        return [
            {"display_name": doc.get("user_id", ""), "score_delta": float(doc.get("score_delta", 0.0))}
            for doc in cursor
        ]

    rows = db.execute(
        select(WeeklyIntelligenceRecord)
        .where(WeeklyIntelligenceRecord.week_start_date == target_week)
        .order_by(desc(WeeklyIntelligenceRecord.score_delta))
        .limit(limit)
    ).scalars().all()
    return [{"display_name": row.user_id, "score_delta": float(row.score_delta)} for row in rows]


def org_dashboard(db: Union[Session, Database], *, week_start: str | None = None) -> dict:
    target_week = week_start or _week_start_str(datetime.utcnow())
    if DATABASE_BACKEND == "mongodb":
        weekly_rows = list(db.weekly_intelligence_records.find({"week_start_date": target_week}))
        enriched_rows = list(db.enriched_events.find({"event_timestamp": {"$gte": datetime.fromisoformat(target_week)}}))
        active = sum(1 for r in weekly_rows if r.get("weekly_active_user_flag"))
        total_users = len({r.get("user_id", "") for r in weekly_rows if r.get("user_id")})
        adoption_rate = round((active / total_users) * 100, 2) if total_users else 0.0
        avg_score = round(sum(float(r.get("validation_score", 0.0)) for r in enriched_rows) / len(enriched_rows), 2) if enriched_rows else 0.0
        positive_velocity = sum(1 for r in weekly_rows if float(r.get("learning_velocity", 0.0)) > 0)
        pct_positive_velocity_users = round((positive_velocity / total_users) * 100, 2) if total_users else 0.0
        return {
            "week_start_date": target_week,
            "adoption_rate": adoption_rate,
            "avg_validation_score": avg_score,
            "pct_positive_velocity_users": pct_positive_velocity_users,
            "pii_masking": {"applied": True, "prompt_fields": "[REDACTED]"},
        }

    week_start_dt = datetime.fromisoformat(target_week)
    active_users = db.execute(
        select(func.count(WeeklyIntelligenceRecord.id)).where(
            WeeklyIntelligenceRecord.week_start_date == target_week,
            WeeklyIntelligenceRecord.weekly_active_user_flag == True,  # noqa: E712
        )
    ).scalar_one()
    total_users = db.execute(
        select(func.count(func.distinct(WeeklyIntelligenceRecord.user_id))).where(
            WeeklyIntelligenceRecord.week_start_date == target_week
        )
    ).scalar_one()
    adoption_rate = round((float(active_users) / float(total_users)) * 100, 2) if total_users else 0.0
    avg_score = db.execute(
        select(func.avg(EnrichedEventRecord.validation_score)).where(
            EnrichedEventRecord.event_timestamp >= week_start_dt
        )
    ).scalar_one() or 0.0
    positive_velocity = db.execute(
        select(func.count(WeeklyIntelligenceRecord.id)).where(
            WeeklyIntelligenceRecord.week_start_date == target_week,
            WeeklyIntelligenceRecord.learning_velocity > 0,
        )
    ).scalar_one()
    pct_positive_velocity_users = round((float(positive_velocity) / float(total_users)) * 100, 2) if total_users else 0.0
    return {
        "week_start_date": target_week,
        "adoption_rate": adoption_rate,
        "avg_validation_score": round(float(avg_score), 2),
        "pct_positive_velocity_users": pct_positive_velocity_users,
        "pii_masking": {"applied": True, "prompt_fields": "[REDACTED]"},
    }


def team_report(db: Union[Session, Database], *, team_id: str, week_start: str | None = None) -> dict:
    target_week = week_start or _week_start_str(datetime.utcnow())
    if DATABASE_BACKEND == "mongodb":
        rows = list(
            db.enriched_events.find(
                {
                    "team_id": team_id,
                    "event_timestamp": {"$gte": datetime.fromisoformat(target_week)},
                }
            )
        )
        if not rows:
            return {
                "week_start_date": target_week,
                "team_id": team_id,
                "team_avg_score": 0.0,
                "intervention_flag_count": 0,
                "pii_masking": {"applied": True, "prompt_fields": "[REDACTED]"},
            }
        team_avg = round(sum(float(r.get("validation_score", 0.0)) for r in rows) / len(rows), 2)
        intervention_count = sum(1 for r in rows if bool(r.get("intervention_flag")))
        return {
            "week_start_date": target_week,
            "team_id": team_id,
            "team_avg_score": team_avg,
            "intervention_flag_count": intervention_count,
            "pii_masking": {"applied": True, "prompt_fields": "[REDACTED]"},
        }

    week_start_dt = datetime.fromisoformat(target_week)
    avg_score = db.execute(
        select(func.avg(EnrichedEventRecord.validation_score)).where(
            EnrichedEventRecord.team_id == team_id,
            EnrichedEventRecord.event_timestamp >= week_start_dt,
        )
    ).scalar_one()
    intervention_count = db.execute(
        select(func.count(EnrichedEventRecord.id)).where(
            EnrichedEventRecord.team_id == team_id,
            EnrichedEventRecord.event_timestamp >= week_start_dt,
            EnrichedEventRecord.intervention_flag == True,  # noqa: E712
        )
    ).scalar_one()
    return {
        "week_start_date": target_week,
        "team_id": team_id,
        "team_avg_score": round(float(avg_score or 0.0), 2),
        "intervention_flag_count": int(intervention_count or 0),
        "pii_masking": {"applied": True, "prompt_fields": "[REDACTED]"},
    }
