"""The ``dbt_build`` stage: the run's generated project as a dbt Project on Snowflake (§3.4).

``CREATE OR REPLACE DBT PROJECT BK_<run_id8> FROM '@DBT_SRC/<run_id>/dbt' DBT_VERSION = '1.12.3'``
(F11, F13), then ``EXECUTE DBT PROJECT`` twice: ``build`` without the parity tests, which must
return ``SUCCESS = TRUE`` or the stage fails with dbt's output as its detail (F12); then the
parity tests, whose result is recorded, never raised: the ``verify`` stage reports mismatches.
The models land in the profile's schema ``<deployment schema>__R_<run_id>`` (upper case: dbt
creates it unquoted). SQL text holds only the checked run id and constants.
"""

from __future__ import annotations

import json
import re
from typing import Any, Final, Protocol

from bob_killer import registry
from bob_killer.generate.dbt.generator import PARITY_TAG
from bob_killer.hosts.snowflake.compiler import DBT_SRC, DBT_VERSION
from bob_killer.registry import Stage

STAGE_NAME: Final = "dbt_build"
PROJECT_PREFIX = "BK_"
DBT_TARGET = "bk"  # the one output of the generated profiles.yml
BUILD_ARGS = f"build --exclude tag:{PARITY_TAG} --target {DBT_TARGET}"
PARITY_ARGS = f"test --select tag:{PARITY_TAG} --target {DBT_TARGET}"
DETAIL_TAIL = 8_000  # characters of dbt output kept in a failed stage's detail
_RUN_ID = re.compile(r"[0-9a-f]{32}")


class DbtBuildFailed(RuntimeError):
    """``EXECUTE DBT PROJECT ... build`` returned SUCCESS = FALSE."""


class DbtIO(Protocol):
    @property
    def session(self) -> Any: ...


def project_name(run_id: str) -> str:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError(f"not a run id: {run_id!r}")
    return f"{PROJECT_PREFIX}{run_id[:8].upper()}"


def create_sql(run_id: str) -> str:
    source = f"{DBT_SRC}/{run_id}/dbt"
    return (
        f"CREATE OR REPLACE DBT PROJECT {project_name(run_id)} FROM '{source}' "
        f"DBT_VERSION = '{DBT_VERSION}'"
    )


def execute_sql(run_id: str, args: str) -> str:
    return (
        f"EXECUTE DBT PROJECT {project_name(run_id)} ARGS = '{args}' DBT_VERSION = '{DBT_VERSION}'"
    )


def _execute(session: Any, run_id: str, args: str) -> dict[str, Any]:
    (row,) = session.sql(execute_sql(run_id, args)).collect()
    result: dict[str, Any] = row.as_dict()
    return result


def dbt_build(session: Any, run_id: str) -> str:
    """Create and build the run's project; the stage detail is a JSON summary."""
    project = project_name(run_id)
    session.sql(create_sql(run_id)).collect()
    build = _execute(session, run_id, BUILD_ARGS)
    if build["SUCCESS"] is not True:
        output = f"{build.get('EXCEPTION')}\n{build.get('STDOUT') or ''}"
        raise DbtBuildFailed(output[-DETAIL_TAIL:])
    parity = _execute(session, run_id, PARITY_ARGS)
    return json.dumps(
        {
            "project": project,
            "dbt_version": DBT_VERSION,
            "build": {"success": True, "archive": build.get("OUTPUT_ARCHIVE_URL")},
            "parity": {
                "success": parity["SUCCESS"] is True,
                "archive": parity.get("OUTPUT_ARCHIVE_URL"),
            },
        },
        sort_keys=True,
    )


def dbt_stage(io: DbtIO) -> Stage:
    def run(run_id: str) -> str:
        return dbt_build(io.session, run_id)

    return run


def register_stages(io: DbtIO) -> None:
    if STAGE_NAME not in registry.stages:
        registry.stages.add(STAGE_NAME, dbt_stage(io))
