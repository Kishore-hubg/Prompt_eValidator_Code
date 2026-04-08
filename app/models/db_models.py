from datetime import datetime
from sqlalchemy import String, Text, Float, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PersonaAssignment(Base):
    __tablename__ = "persona_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_email: Mapped[str] = mapped_column(String(255), index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PromptValidationRecord(Base):
    __tablename__ = "prompt_validations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    channel: Mapped[str] = mapped_column(String(50), default="web")
    prompt_text: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    rating: Mapped[str] = mapped_column(String(50))
    issues_json: Mapped[str] = mapped_column(Text)
    suggestions_json: Mapped[str] = mapped_column(Text)
    improved_prompt: Mapped[str] = mapped_column(Text)
    user_email: Mapped[str] = mapped_column(String(255), default="", index=True)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    delivery_channel: Mapped[str] = mapped_column(String(20), default="API", index=True)
    validation_score_10: Mapped[float] = mapped_column(Float, default=0.0)
    llm_evaluation_json: Mapped[str] = mapped_column(Text, default="{}")
    data_governance_json: Mapped[str] = mapped_column(Text, default="{}")
    source_of_truth_json: Mapped[str] = mapped_column(Text, default="{}")
    token_usage_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class DimensionScoreRecord(Base):
    __tablename__ = "dimension_scores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    validation_id: Mapped[int] = mapped_column(ForeignKey("prompt_validations.id"), index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    dimension_name: Mapped[str] = mapped_column(String(80), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PromptRewriteRecord(Base):
    __tablename__ = "prompt_rewrites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    validation_id: Mapped[int] = mapped_column(ForeignKey("prompt_validations.id"), index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    original_prompt: Mapped[str] = mapped_column(Text)
    improved_prompt: Mapped[str] = mapped_column(Text)
    rewrite_strategy: Mapped[str] = mapped_column(String(80), default="template")
    rewrite_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ChannelUsageRecord(Base):
    __tablename__ = "channel_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(50), index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    user_email: Mapped[str] = mapped_column(String(255), default="", index=True)
    event_type: Mapped[str] = mapped_column(String(80), default="validation")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class FeedbackEventRecord(Base):
    __tablename__ = "feedback_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    validation_id: Mapped[int] = mapped_column(ForeignKey("prompt_validations.id"), index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class RawEventRecord(Base):
    __tablename__ = "raw_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    delivery_channel: Mapped[str] = mapped_column(String(20), index=True)
    original_prompt: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    source_of_truth_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class EnrichedEventRecord(Base):
    __tablename__ = "enriched_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    raw_event_id: Mapped[int | None] = mapped_column(ForeignKey("raw_events.id"), index=True, nullable=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    team_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    delivery_channel: Mapped[str] = mapped_column(String(20), index=True)
    original_prompt: Mapped[str] = mapped_column(Text)
    prompt_type_classification: Mapped[str] = mapped_column(String(50), default="")
    prompt_complexity_class: Mapped[str] = mapped_column(String(20), default="")
    validation_score: Mapped[float] = mapped_column(Float, default=0.0)
    suggestion_count: Mapped[int] = mapped_column(Integer, default=0)
    suggestions_json: Mapped[str] = mapped_column(Text, default="[]")
    corrected_prompt: Mapped[str] = mapped_column(Text, default="")
    autofix_improvement_points_json: Mapped[str] = mapped_column(Text, default="[]")
    score_delta: Mapped[float] = mapped_column(Float, default=0.0)
    suggestion_acceptance_rate: Mapped[float] = mapped_column(Float, default=0.0)
    autofix_utilization_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    intervention_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_evaluation_json: Mapped[str] = mapped_column(Text, default="{}")
    data_governance_json: Mapped[str] = mapped_column(Text, default="{}")
    source_of_truth_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class DeadLetterEventRecord(Base):
    __tablename__ = "dead_letter_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    persona_id: Mapped[str] = mapped_column(String(50), default="", index=True)
    delivery_channel: Mapped[str] = mapped_column(String(20), default="", index=True)
    original_prompt: Mapped[str] = mapped_column(Text, default="")
    error_code: Mapped[str] = mapped_column(String(80), index=True)
    error_reason: Mapped[str] = mapped_column(Text, default="")
    source_of_truth_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class WeeklyIntelligenceRecord(Base):
    __tablename__ = "weekly_intelligence_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    week_start_date: Mapped[str] = mapped_column(String(20), index=True)
    weekly_active_user_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    score_delta: Mapped[float] = mapped_column(Float, default=0.0)
    learning_velocity: Mapped[float] = mapped_column(Float, default=0.0)
    intervention_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
