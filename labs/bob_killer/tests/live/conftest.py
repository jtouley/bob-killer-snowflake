"""Live Snowflake fixtures. One session per test run; later phases extend this file, not copy it.

Run: ``uv run pytest -m live tests/live`` with the ``bob_killer`` connection in
``~/.snowflake/connections.toml``. Without a working connection the suite fails; it never skips.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from snowflake.snowpark import Session

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
    s = Session.builder.config("connection_name", CONNECTION).create()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(scope="session")
def expected_role() -> str:
    """The build role, from the environment (no repo file names a role; spec §10.4)."""
    role = os.environ.get("BK_EXPECTED_ROLE", "")
    if not role:
        raise RuntimeError("set BK_EXPECTED_ROLE to the role of the bob_killer connection")
    return role
