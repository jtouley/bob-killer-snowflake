"""hosts/snowflake/dbt.py: the dbt_build stage over CREATE / EXECUTE DBT PROJECT (§3.4, F11-F13)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from bob_killer import registry
from bob_killer.hosts.snowflake import dbt
from tests.fakes.snowpark import FakeSession

RUN_ID = "0123456789abcdef" * 2
ARCHIVES = {dbt.BUILD_ARGS: "snow://build.zip", dbt.PARITY_ARGS: "snow://parity.zip"}


def _session(build_ok: bool, parity_ok: bool) -> FakeSession:
    s = FakeSession()
    s.script("CREATE OR REPLACE DBT PROJECT", [{"status": "created"}])
    for args, ok in ((dbt.BUILD_ARGS, build_ok), (dbt.PARITY_ARGS, parity_ok)):
        s.script(
            dbt.execute_sql(RUN_ID, args),
            [
                {
                    "SUCCESS": ok,
                    "EXCEPTION": None if ok else f"error in {args}",
                    "STDOUT": f"stdout of {args}",
                    "OUTPUT_ARCHIVE_URL": ARCHIVES[args],
                }
            ],
        )
    return s


class IO:
    def __init__(self, session: Any) -> None:
        self.session = session


def test_build_and_parity_succeed_and_the_detail_names_both_archives() -> None:
    session = _session(build_ok=True, parity_ok=True)
    detail = json.loads(dbt.dbt_stage(IO(session))(RUN_ID))
    assert session.sql_texts == [
        dbt.create_sql(RUN_ID),
        dbt.execute_sql(RUN_ID, dbt.BUILD_ARGS),
        dbt.execute_sql(RUN_ID, dbt.PARITY_ARGS),
    ]
    assert detail["project"] == dbt.project_name(RUN_ID)
    assert detail["build"]["archive"] == ARCHIVES[dbt.BUILD_ARGS]
    assert detail["parity"]["success"] is True
    assert detail["parity"]["archive"] == ARCHIVES[dbt.PARITY_ARGS]


def test_a_failed_build_fails_the_stage_with_the_dbt_output() -> None:
    session = _session(build_ok=False, parity_ok=True)
    with pytest.raises(dbt.DbtBuildFailed) as failed:
        dbt.dbt_stage(IO(session))(RUN_ID)
    assert f"error in {dbt.BUILD_ARGS}" in str(failed.value)
    assert f"stdout of {dbt.BUILD_ARGS}" in str(failed.value)
    assert dbt.execute_sql(RUN_ID, dbt.PARITY_ARGS) not in session.sql_texts


def test_a_parity_failure_is_recorded_not_raised() -> None:
    session = _session(build_ok=True, parity_ok=False)
    detail = json.loads(dbt.dbt_stage(IO(session))(RUN_ID))
    assert detail["parity"]["success"] is False


def test_the_project_comes_from_the_runs_dbt_folder_at_the_pinned_version() -> None:
    from bob_killer.hosts.snowflake.compiler import DBT_SRC, DBT_VERSION

    sql = dbt.create_sql(RUN_ID)
    assert f"FROM '{DBT_SRC}/{RUN_ID}/dbt'" in sql
    assert f"DBT_VERSION = '{DBT_VERSION}'" in sql
    assert f"DBT_VERSION = '{DBT_VERSION}'" in dbt.execute_sql(RUN_ID, dbt.BUILD_ARGS)
    assert dbt.project_name(RUN_ID) == dbt.PROJECT_PREFIX + RUN_ID[: len(RUN_ID) // 4].upper()


@pytest.mark.parametrize("bad", [RUN_ID.upper(), RUN_ID[:-1], RUN_ID + "'; DROP"])
def test_a_bad_run_id_runs_no_sql(bad: str) -> None:
    session = _session(build_ok=True, parity_ok=True)
    with pytest.raises(ValueError):
        dbt.dbt_stage(IO(session))(bad)
    assert session.sql_texts == []


def test_register_stages_is_idempotent() -> None:
    io = IO(FakeSession())
    dbt.register_stages(io)
    dbt.register_stages(io)
    assert registry.stages.names() == (dbt.STAGE_NAME,)
