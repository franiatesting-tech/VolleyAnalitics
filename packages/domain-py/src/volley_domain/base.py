"""Shared SQLAlchemy declarative base + id/timestamp helpers, used by both
models.py (Phase 1: Match, ProcessingJob) and ontology.py (Phase 2: the full
volleyball ontology, see docs/domain/ONTOLOGY.md). Split into its own module
so both can import the same `Base` without one importing the other.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)
