"""store/: typed repository over the DDL generated from contracts."""

from __future__ import annotations

from pathlib import Path

from bob_killer.contracts.runs import RunState, StageState, StageStatus
from bob_killer.store.db import RunStore
from tests.conftest import sample_run


def test_run_round_trips(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "w.db")
    run = sample_run()
    store.insert_run(run)
    assert store.get_run(run.run_id) == run


def test_missing_run_is_none(tmp_path: Path) -> None:
    assert RunStore(tmp_path / "w.db").get_run("nope") is None


def test_set_state_and_stages(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "w.db")
    run = sample_run()
    store.insert_run(run)
    store.set_state(run.run_id, RunState.SUCCEEDED)
    status = StageStatus(run_id=run.run_id, stage="extract", state=StageState.SUCCEEDED, detail="")
    store.upsert_stage(status)
    store.upsert_stage(status)
    fetched = store.get_run(run.run_id)
    assert fetched is not None
    assert fetched.state == RunState.SUCCEEDED
    assert store.stages(run.run_id) == (status,)
