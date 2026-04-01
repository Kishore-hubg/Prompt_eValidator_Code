from dataclasses import dataclass
from datetime import datetime
from typing import Union

from pymongo.database import Database
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import DATABASE_BACKEND
from app.models.db_models import PersonaAssignment, User


@dataclass
class PersonaMappingResult:
    user_email: str
    persona_id: str
    source: str


def upsert_user(db: Union[Session, Database], *, email: str, display_name: str = ""):
    if DATABASE_BACKEND == "mongodb":
        return _upsert_user_mongo(db, email=email, display_name=display_name)
    return _upsert_user_sql(db, email=email, display_name=display_name)


def _upsert_user_sql(db: Session, *, email: str, display_name: str = ""):
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        if display_name and existing.display_name != display_name:
            existing.display_name = display_name
            db.commit()
            db.refresh(existing)
        return existing

    user = User(email=email, display_name=display_name or email.split("@")[0])
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _upsert_user_mongo(db: Database, *, email: str, display_name: str = ""):
    email = email.strip().lower()
    now = datetime.utcnow()
    name = display_name or email.split("@")[0]
    db.users.update_one(
        {"email": email},
        {
            "$set": {"display_name": name, "is_active": True},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return {"email": email, "display_name": name}


def map_persona(db: Union[Session, Database], *, email: str, persona_id: str, source: str = "manual"):
    if DATABASE_BACKEND == "mongodb":
        return _map_persona_mongo(db, email=email, persona_id=persona_id, source=source)
    return _map_persona_sql(db, email=email, persona_id=persona_id, source=source)


def _map_persona_sql(db: Session, *, email: str, persona_id: str, source: str):
    upsert_user(db, email=email)
    existing = db.execute(
        select(PersonaAssignment).where(
            PersonaAssignment.user_email == email,
            PersonaAssignment.is_primary == True,  # noqa: E712
        )
    ).scalar_one_or_none()
    if existing:
        existing.persona_id = persona_id
        existing.source = source
        db.commit()
        db.refresh(existing)
        return PersonaMappingResult(
            user_email=existing.user_email,
            persona_id=existing.persona_id,
            source=existing.source,
        )

    assignment = PersonaAssignment(
        user_email=email,
        persona_id=persona_id,
        source=source,
        is_primary=True,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return PersonaMappingResult(
        user_email=assignment.user_email,
        persona_id=assignment.persona_id,
        source=assignment.source,
    )


def _map_persona_mongo(db: Database, *, email: str, persona_id: str, source: str):
    email = email.strip().lower()
    _upsert_user_mongo(db, email=email)
    now = datetime.utcnow()
    db.persona_assignments.update_one(
        {"user_email": email, "is_primary": True},
        {
            "$set": {
                "persona_id": persona_id,
                "source": source,
                "is_primary": True,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return PersonaMappingResult(user_email=email, persona_id=persona_id, source=source)


def resolve_persona_for_user(db: Union[Session, Database], *, email: str) -> str:
    if DATABASE_BACKEND == "mongodb":
        return _resolve_persona_mongo(db, email=email)
    return _resolve_persona_sql(db, email=email)


def _resolve_persona_sql(db: Session, *, email: str) -> str:
    assignment = db.execute(
        select(PersonaAssignment).where(
            PersonaAssignment.user_email == email,
            PersonaAssignment.is_primary == True,  # noqa: E712
        )
    ).scalar_one_or_none()
    return assignment.persona_id if assignment else "persona_0"


def _resolve_persona_mongo(db: Database, *, email: str) -> str:
    email = email.strip().lower()
    doc = db.persona_assignments.find_one({"user_email": email, "is_primary": True})
    if doc and doc.get("persona_id"):
        return str(doc["persona_id"])
    return "persona_0"
