"""hosts/snowflake/store.py: SnowflakeRunStore SQL shape, binds and read validation (Phase 4).

The behaviour suite runs on this store through ``STORE_FACTORIES`` in tests/conftest.py;
this file checks only what the shared suite cannot see: the SQL the store sends.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from bob_killer.contracts.runs import Run, RunState, StageState, StageStatus
from bob_killer.hosts.snowflake.store import SnowflakeRunStore
from tests.conftest import sample_run, snowflake_tables_session
from tests.fakes.snowpark import FakeSession

TRANSACTION = ("BEGIN", "COMMIT", "ROLLBACK")


def _status(run: Run) -> StageStatus:
    return StageStatus(run_id=run.run_id, stage="extract", state=StageState.FAILED, detail="boom")


def _exercise(store: SnowflakeRunStore, run: Run) -> None:
    store.insert_run(run)
    store.get_run(run.run_id)
    store.set_state(run.run_id, RunState.SUCCEEDED)
    store.claim_run(run.run_id)
    store.upsert_stage(_status(run))
    store.stages(run.run_id)


def _user_values(run: Run) -> set[str]:
    """Free-text values a caller supplies; enum constants may appear in the SQL (claim_run)."""
    return {run.run_id, run.filename, run.sha256, _status(run).detail}


def test_every_value_is_bound_never_in_the_sql_text() -> None:
    session, run = snowflake_tables_session(), sample_run()
    _exercise(SnowflakeRunStore(session), run)
    values = _user_values(run)
    for query in session.sql_texts:
        assert not any(v in query for v in values)
    assert all(params for _, params in session.statements)


def test_reads_name_their_columns_and_stages_order_by_seq() -> None:
    session, run = snowflake_tables_session(), sample_run()
    _exercise(SnowflakeRunStore(session), run)
    selects = [q for q in session.sql_texts if q.startswith("SELECT")]
    assert selects
    assert not any(q.startswith("SELECT *") for q in selects)
    stage_select = next(q for q in selects if StageStatus.table_name.upper() in q)
    assert stage_select.endswith("ORDER BY _seq")
    assert all(f" {name}" in stage_select for name in StageStatus.model_fields)


def test_upsert_is_one_merge_on_the_key_that_updates_state_and_detail() -> None:
    session, run = FakeSession(), sample_run()
    SnowflakeRunStore(session).upsert_stage(_status(run))
    ((query, params),) = session.statements
    updates = ", ".join(
        f"{n} = s.{n}" for n in StageStatus.model_fields if n not in StageStatus.primary_key
    )
    assert query.startswith(f"MERGE INTO {StageStatus.table_name.upper()}")
    assert all(f"t.{k} = s.{k}" in query for k in StageStatus.primary_key)
    assert f"WHEN MATCHED THEN UPDATE SET {updates}" in query
    assert tuple(params or ()) == tuple(_status(run).model_dump(mode="json").values())


@pytest.mark.parametrize(("rows_updated", "expected"), [(0, False), (1, True), (2, False)])
def test_claim_is_one_conditional_update_with_no_transaction(
    rows_updated: int, expected: bool
) -> None:
    session, run_id = FakeSession(), sample_run().run_id
    session.script_affected("UPDATE", updated=rows_updated)
    won = SnowflakeRunStore(session).claim_run(run_id)
    ((query, params),) = session.statements
    assert won is expected
    assert tuple(params or ()) == (run_id,)
    assert query.startswith(f"UPDATE {Run.table_name.upper()}")
    assert f"SET state = '{RunState.RUNNING.value}'" in query
    assert query.endswith(f"WHERE run_id = ? AND state = '{RunState.QUEUED.value}'")
    assert not any(q.startswith(TRANSACTION) for q in session.sql_texts)


def _bad_run_row(run: Run) -> dict[str, object]:
    return {**run.model_dump(mode="json"), "state": "bogus"}


def _bad_stage_row(run: Run) -> dict[str, object]:
    return {**_status(run).model_dump(mode="json"), "state": "bogus"}


@pytest.mark.parametrize(
    ("bad_row", "read"),
    [
        (_bad_run_row, lambda store, run_id: store.get_run(run_id)),
        (_bad_stage_row, lambda store, run_id: store.stages(run_id)),
    ],
    ids=["run", "stage"],
)
def test_a_bad_enum_value_from_the_database_raises(
    bad_row: Callable[[Run], dict[str, object]],
    read: Callable[[SnowflakeRunStore, str], object],
) -> None:
    run, session = sample_run(), FakeSession()
    session.script("SELECT", [{k.upper(): v for k, v in bad_row(run).items()}])
    with pytest.raises(ValidationError):
        read(SnowflakeRunStore(session), run.run_id)
