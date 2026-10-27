"""Snowpark sessions, TEST_ schemas and the TEST_ sweep (docs/SPEC.md §6.4, §8 Phase 2).

Only the host gets a session from Snowpark (spec §5.3); the sweep and ``test_schema`` receive one.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from snowflake.snowpark import Session

log = logging.getLogger(__name__)

TEST_PREFIX = "TEST_"
SWEEP_MAX_AGE = timedelta(hours=24)


def open_session(connection_name: str) -> Session:
    session: Session = Session.builder.config("connection_name", connection_name).create()
    return session


def quote_ident(name: str) -> str:
    """A Snowflake quoted identifier; each ``"`` in the name is doubled."""
    return '"' + name.replace('"', '""') + '"'


@contextmanager
def test_schema(session: Session) -> Iterator[str]:
    """Create ``TEST_<uuid8>`` in the current database, yield its name, drop it on exit."""
    name = f"{TEST_PREFIX}{uuid.uuid4().hex[:8].upper()}"
    session.sql(f"CREATE SCHEMA {quote_ident(name)}").collect()
    try:
        yield name
    finally:
        session.sql(f"DROP SCHEMA IF EXISTS {quote_ident(name)}").collect()


def sweep_test_schemas(session: Session, now: datetime | None = None) -> list[str]:
    """Drop ``TEST_`` schemas of the current database created more than 24 h before ``now``."""
    ((db,),) = session.sql("SELECT CURRENT_DATABASE()").collect()
    if db is None:
        log.info("sweep skipped: no current database")
        return []
    cutoff = (now or datetime.now(UTC)) - SWEEP_MAX_AGE
    dropped: list[str] = []
    for row in session.sql(f"SHOW SCHEMAS IN DATABASE {quote_ident(db)}").collect():
        name: str = row["name"]
        created_on: datetime = row["created_on"]
        if created_on.tzinfo is None:
            raise ValueError(f"created_on of schema {name!r} has no tzinfo")
        if name.startswith(TEST_PREFIX) and created_on < cutoff:
            session.sql(f"DROP SCHEMA IF EXISTS {quote_ident(db)}.{quote_ident(name)}").collect()
            log.info("sweep dropped %s", name)
            dropped.append(name)
    return dropped
