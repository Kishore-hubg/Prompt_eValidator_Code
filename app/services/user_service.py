"""User tracking service — upsert users into the `users` table/collection.

Called by save_validation() every time any channel submits a prompt, so that
the users table always reflects the full set of people using the app.

Supports both MongoDB and SQLite backends.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Union

from pymongo.database import Database
from sqlalchemy.orm import Session

from app.core.settings import DATABASE_BACKEND

_log = logging.getLogger("prompt_validator.user_service")

# Synthetic email suffixes used as fallback identifiers when real email is
# unavailable.  We still track these so channel usage is visible in analytics.
_SYNTHETIC_SUFFIXES = ("@teams.local", "@slack.local")


def _display_name_from_email(email: str) -> str:
    """Derive a readable display name from an email / synthetic identifier."""
    local = (email or "").split("@")[0]
    return local.replace("-", " ").replace(".", " ").replace("_", " ").title()


def _is_synthetic(email: str) -> bool:
    return any(email.endswith(s) for s in _SYNTHETIC_SUFFIXES)


def upsert_user(
    db: Union[Session, Database],
    *,
    email: str,
    display_name: str = "",
    channel: str = "",
) -> None:
    """Insert the user if not already present; silently skip if email is blank.

    Args:
        db:           Active database session or MongoDB client.
        email:        User email address (real or synthetic @teams.local /
                      @slack.local identifier).
        display_name: Human-readable name — auto-derived from email if empty.
        channel:      Channel the user was seen on (for logging only).
    """
    if not email or not email.strip():
        return

    email = email.strip().lower()
    name = (display_name or "").strip() or _display_name_from_email(email)

    try:
        if DATABASE_BACKEND == "mongodb":
            _upsert_mongo(db, email=email, display_name=name)
        else:
            _upsert_sql(db, email=email, display_name=name)
    except Exception as exc:  # noqa: BLE001
        # User tracking must never block the main validation flow.
        _log.warning("upsert_user failed for %s (channel=%s): %s", email, channel, exc)


# ── MongoDB ────────────────────────────────────────────────────────────────────

def _upsert_mongo(db: Database, *, email: str, display_name: str) -> None:
    """Upsert into the `users` collection (insert if new, keep existing name)."""
    db.users.update_one(
        {"email": email},
        {
            "$setOnInsert": {
                "email": email,
                "display_name": display_name,
                "is_active": True,
                "created_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )


# ── SQLite ─────────────────────────────────────────────────────────────────────

def _upsert_sql(db: Session, *, email: str, display_name: str) -> None:
    """Insert the user row only if the email doesn't already exist."""
    from app.models.db_models import User  # local import to avoid circular deps
    from sqlalchemy import select

    existing = db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()

    if existing is None:
        db.add(User(
            email=email,
            display_name=display_name,
            is_active=True,
        ))
        db.commit()
