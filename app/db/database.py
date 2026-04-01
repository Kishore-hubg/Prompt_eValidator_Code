from typing import Any, Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.settings import DATABASE_BACKEND, DB_PATH

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, future=True, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass


def initialize_schema():
    """
    Lightweight schema bootstrap + additive migration for SQLite MVP.
    Safe to run repeatedly on startup.
    """
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "prompt_validations" not in tables:
        return

    existing_cols = {col["name"] for col in inspector.get_columns("prompt_validations")}
    rewrite_cols = {col["name"] for col in inspector.get_columns("prompt_rewrites")} if "prompt_rewrites" in tables else set()
    with engine.begin() as conn:
        if "user_email" not in existing_cols:
            conn.execute(text("ALTER TABLE prompt_validations ADD COLUMN user_email VARCHAR(255) DEFAULT ''"))
        if "issue_count" not in existing_cols:
            conn.execute(text("ALTER TABLE prompt_validations ADD COLUMN issue_count INTEGER DEFAULT 0"))
        if "delivery_channel" not in existing_cols:
            conn.execute(text("ALTER TABLE prompt_validations ADD COLUMN delivery_channel VARCHAR(20) DEFAULT 'API'"))
        if "validation_score_10" not in existing_cols:
            conn.execute(text("ALTER TABLE prompt_validations ADD COLUMN validation_score_10 FLOAT DEFAULT 0.0"))
        if "llm_evaluation_json" not in existing_cols:
            conn.execute(text("ALTER TABLE prompt_validations ADD COLUMN llm_evaluation_json TEXT DEFAULT '{}'"))
        if "data_governance_json" not in existing_cols:
            conn.execute(text("ALTER TABLE prompt_validations ADD COLUMN data_governance_json TEXT DEFAULT '{}'"))
        if "source_of_truth_json" not in existing_cols:
            conn.execute(text("ALTER TABLE prompt_validations ADD COLUMN source_of_truth_json TEXT DEFAULT '{}'"))
        if rewrite_cols and "rewrite_metadata_json" not in rewrite_cols:
            conn.execute(text("ALTER TABLE prompt_rewrites ADD COLUMN rewrite_metadata_json TEXT DEFAULT '{}'"))

def get_db() -> Iterator[Any]:
    """Yields SQLAlchemy Session (sqlite) or pymongo Database (mongodb)."""
    if DATABASE_BACKEND == "mongodb":
        from app.db.mongo_db import get_mongo_database

        yield get_mongo_database()
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
