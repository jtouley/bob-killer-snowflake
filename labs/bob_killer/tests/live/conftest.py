"""Live Snowflake fixtures. One session per test run; later phases extend this file, not copy it.

Run: ``uv run pytest -m live tests/live`` with the ``bob_killer`` connection in
``~/.snowflake/connections.toml``. Without a working connection the suite fails; it never skips.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from snowflake.snowpark import Session

from bob_killer.hosts.snowflake import session as sf

CONNECTION = os.environ.get("BK_CONNECTION", "bob_killer")


def _is_live(item: pytest.Item) -> bool:
    return "tests/live/" in str(item.path).replace(os.sep, "/")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every test under tests/live/ is a live test, so the default `-m 'not live'` deselects it."""
    for item in items:
        if _is_live(item):
            item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session")
def session() -> Iterator[Session]:
    """The one live session. Before any test, the TEST_ sweep drops schemas older than 24 h."""
    s = sf.open_session(CONNECTION)
    try:
        sf.sweep_test_schemas(s)
        yield s
    finally:
        s.close()


@pytest.fixture(scope="session")
def schema(session: Session) -> Iterator[str]:
    """A TEST_<uuid8> schema for this run, dropped at teardown. Tests qualify names with it."""
    with sf.test_schema(session) as name:
        yield name


@pytest.fixture(scope="session")
def expected_role() -> str:
    """The build role, from the environment (no repo file names a role; spec §10.4)."""
    role = os.environ.get("BK_EXPECTED_ROLE", "")
    if not role:
        raise RuntimeError("set BK_EXPECTED_ROLE to the role of the bob_killer connection")
    return role


def fresh_tables(session: Session, schema: str, models: tuple[type, ...]) -> None:
    """Create (or replace) these contract tables, from the snowflake DDL dialect, in ``schema``."""
    from bob_killer.hosts.snowflake.ddl import table_ddl

    session.use_schema(schema)
    for model in models:
        ddl = table_ddl(model).replace("CREATE TABLE IF NOT EXISTS", "CREATE OR REPLACE TABLE", 1)
        session.sql(ddl).collect()


@pytest.fixture
def store(session: Session, schema: str) -> object:
    """The shared RunRepository suite's ``store``, overridden here with a live SnowflakeRunStore.

    Fresh RUNS and STAGE_STATUS tables in this run's TEST_ schema for every test.
    """
    from bob_killer.contracts.runs import Run, StageStatus
    from bob_killer.hosts.snowflake.store import SnowflakeRunStore

    fresh_tables(session, schema, (Run, StageStatus))
    return SnowflakeRunStore(session)


@pytest.fixture
def bronze_session(session: Session, schema: str) -> Session:
    """Fresh LANDED_FILES and BRONZE_ROWS tables in this run's TEST_ schema for every test."""
    from bob_killer.contracts.bronze import BronzeRow, LandedFile

    fresh_tables(session, schema, (LandedFile, BronzeRow))
    return session
