"""TEST_ sweep and test-schema rules (docs/SPEC.md §6.4, §8 Phase 2), against the shared FakeSession."""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import UTC, datetime, timedelta, timezone

import pytest

from bob_killer.hosts.snowflake import session as sf
from tests.fakes.snowpark import FakeSession

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
OLD = NOW - timedelta(hours=25)
NEW = NOW - timedelta(hours=23)
PST = timezone(timedelta(hours=-8))
SELECT_DB = "SELECT CURRENT_DATABASE()"

SWEEP_CASES = [
    pytest.param(
        "BOB_KILLER",
        [("TEST_OLD", OLD), ("TEST_NEW", NEW), ("TESTX_OLD", OLD), ("APP", OLD)],
        [
            SELECT_DB,
            'SHOW SCHEMAS IN DATABASE "BOB_KILLER"',
            'DROP SCHEMA IF EXISTS "BOB_KILLER"."TEST_OLD"',
        ],
        ["TEST_OLD"],
        ["sweep dropped TEST_OLD"],
        id="prefix-and-age",
    ),
    pytest.param(
        None,
        [("TEST_OLD", OLD)],
        [SELECT_DB],
        [],
        ["sweep skipped: no current database"],
        id="no-current-database",
    ),
    pytest.param(
        "BOB_KILLER",
        [
            ("TEST_UTC_OLD", OLD),
            ("TEST_PST_OLD", OLD.astimezone(PST)),
            ("TEST_UTC_NEW", NEW),
            ("TEST_PST_NEW", NEW.astimezone(PST)),
        ],
        [
            SELECT_DB,
            'SHOW SCHEMAS IN DATABASE "BOB_KILLER"',
            'DROP SCHEMA IF EXISTS "BOB_KILLER"."TEST_UTC_OLD"',
            'DROP SCHEMA IF EXISTS "BOB_KILLER"."TEST_PST_OLD"',
        ],
        ["TEST_UTC_OLD", "TEST_PST_OLD"],
        ["sweep dropped TEST_UTC_OLD", "sweep dropped TEST_PST_OLD"],
        id="utc-and-utc-0800",
    ),
    pytest.param(
        "BOB_KILLER",
        [('TEST_A"B', OLD)],
        [
            SELECT_DB,
            'SHOW SCHEMAS IN DATABASE "BOB_KILLER"',
            'DROP SCHEMA IF EXISTS "BOB_KILLER"."TEST_A""B"',
        ],
        ['TEST_A"B'],
        ['sweep dropped TEST_A"B'],
        id="schema-quote-doubled",
    ),
    pytest.param(
        'BK"DB',
        [("TEST_OLD", OLD)],
        [
            SELECT_DB,
            'SHOW SCHEMAS IN DATABASE "BK""DB"',
            'DROP SCHEMA IF EXISTS "BK""DB"."TEST_OLD"',
        ],
        ["TEST_OLD"],
        ["sweep dropped TEST_OLD"],
        id="database-quote-doubled",
    ),
]


def _fake(db: str | None, schemas: list[tuple[str, datetime]]) -> FakeSession:
    fake = FakeSession()
    fake.script(SELECT_DB, [{"CURRENT_DATABASE()": db}])
    fake.script("SHOW SCHEMAS", [{"name": n, "created_on": c} for n, c in schemas])
    return fake


@pytest.mark.parametrize(("db", "schemas", "statements", "dropped", "logs"), SWEEP_CASES)
def test_sweep(
    db: str | None,
    schemas: list[tuple[str, datetime]],
    statements: list[str],
    dropped: list[str],
    logs: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = _fake(db, schemas)
    with caplog.at_level(logging.INFO, logger=sf.__name__):
        result = sf.sweep_test_schemas(fake, now=NOW)  # type: ignore[arg-type]
    assert fake.sql_texts == statements
    assert result == dropped
    assert caplog.messages == logs


def test_sweep_rejects_created_on_without_tzinfo() -> None:
    fake = _fake("BOB_KILLER", [("TEST_OLD", OLD.replace(tzinfo=None))])
    with pytest.raises(ValueError):
        sf.sweep_test_schemas(fake, now=NOW)  # type: ignore[arg-type]


@pytest.mark.parametrize("body_raises", [False, True])
def test_test_schema_creates_then_drops(body_raises: bool) -> None:
    fake = FakeSession()
    with contextlib.suppress(RuntimeError), sf.test_schema(fake) as name:  # type: ignore[arg-type]
        if body_raises:
            raise RuntimeError
    assert re.fullmatch(r"TEST_[0-9A-F]{8}", name)
    assert fake.sql_texts == [f'CREATE SCHEMA "{name}"', f'DROP SCHEMA IF EXISTS "{name}"']
