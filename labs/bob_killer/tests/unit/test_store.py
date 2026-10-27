"""store/: the shared RunRepository contract suite.

Every test that takes the ``store`` fixture runs on each factory in
``tests.conftest.STORE_FACTORIES``. A new store implementation adds one factory there.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from bob_killer import registry
from bob_killer.contracts.runs import RunState, StageState, StageStatus
from bob_killer.service.runs import execute_run
from bob_killer.store.db import RunStore
from tests.conftest import queued_run, sample_run

if TYPE_CHECKING:
    from bob_killer.store import RunRepository


def test_run_round_trips(store: RunRepository) -> None:
    run = sample_run()
    store.insert_run(run)
    assert store.get_run(run.run_id) == run


def test_missing_run_is_none(tmp_path: Path) -> None:
    assert RunStore(tmp_path / "w.db").get_run("nope") is None


def test_set_state_and_stages(store: RunRepository) -> None:
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


def test_unknown_run_is_none_and_not_claimed(store: RunRepository) -> None:
    missing = sample_run().run_id
    assert not store.claim_run(missing)
    assert store.get_run(missing) is None


def test_upsert_updates_the_row_in_place(store: RunRepository) -> None:
    """G8: a second upsert of a stage keeps its position in insert order."""
    run = sample_run()
    store.insert_run(run)
    first, second = (
        StageStatus(run_id=run.run_id, stage=name, state=StageState.PENDING, detail="")
        for name in ("extract", "lift")
    )
    store.upsert_stage(first)
    store.upsert_stage(second)
    failed = first.model_copy(update={"state": StageState.FAILED, "detail": "boom"})
    store.upsert_stage(failed)
    assert store.stages(run.run_id) == (failed, second)


@pytest.mark.parametrize("first_fails", [False, True], ids=["all-succeed", "first-fails"])
def test_stage_rows_keep_registry_order_after_execute(
    store: RunRepository, first_fails: bool
) -> None:
    def first(run_id: str) -> None:
        if first_fails:
            raise RuntimeError(run_id)

    def second(run_id: str) -> None:
        return None

    for stage in (first, second):
        registry.stages.add(stage.__name__, stage)
    run = queued_run(store)
    execute_run(store, run.run_id)
    assert tuple(s.stage for s in store.stages(run.run_id)) == registry.stages.names()


def test_claim_is_won_once(store: RunRepository) -> None:
    run = sample_run()
    store.insert_run(run)
    assert store.claim_run(run.run_id)
    assert not store.claim_run(run.run_id)
    fetched = store.get_run(run.run_id)
    assert fetched is not None
    assert fetched.state == RunState.RUNNING
