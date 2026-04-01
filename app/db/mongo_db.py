"""MongoDB Atlas connection and helpers. Used when DATABASE_BACKEND=mongodb."""

from datetime import datetime
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.database import Database

from app.core.settings import MONGODB_DB_NAME, MONGODB_URI


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    if not MONGODB_URI or not MONGODB_URI.strip():
        raise RuntimeError(
            "MongoDB connection is required when DATABASE_BACKEND=mongodb. "
            "Set MONGODB_URI, or set MONGODB_USER, MONGODB_PASSWORD, and MONGODB_CLUSTER_HOST."
        )
    return MongoClient(MONGODB_URI, appname="prompt_validator")


def get_mongo_database() -> Database:
    return get_mongo_client()[MONGODB_DB_NAME]


def init_mongo_indexes() -> None:
    db = get_mongo_database()
    db.prompt_validations.create_index([("created_at", DESCENDING)])
    db.prompt_validations.create_index([("persona_id", ASCENDING)])
    db.prompt_validations.create_index([("user_email", ASCENDING)])
    db.dimension_scores.create_index([("validation_id", ASCENDING)])
    db.users.create_index([("email", ASCENDING)], unique=True)
    db.persona_assignments.create_index([("user_email", ASCENDING), ("is_primary", ASCENDING)])


def next_sequence(db: Database, name: str) -> int:
    doc = db.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        raise RuntimeError(f"counter failed: {name}")
    return int(doc["seq"])
