"""The build connection reaches Snowflake as the build role (host Phase 1)."""

from __future__ import annotations

from snowflake.snowpark import Session


def test_connection_uses_the_build_role(session: Session, expected_role: str) -> None:
    (row,) = session.sql("SELECT CURRENT_ROLE()").collect()
    assert row[0] == expected_role
