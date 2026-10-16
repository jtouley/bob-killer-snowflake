"""service/runs.py: stage detail (D3), the claim path (G24) and errors outside a stage (G9a)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bob_killer import registry
from bob_killer.contracts.runs import StageState
from bob_killer.service.runs import execute_run
from tests.conftest import queued_run

if TYPE_CHECKING:
    from bob_killer.store import RunRepository


@pytest.mark.parametrize("returns_text", [True, False], ids=["text", "none"])
def test_stage_return_is_the_success_detail(store: RunRepository, returns_text: bool) -> None:
    def stage(run_id: str) -> str | None:
        return f"landed {run_id}" if returns_text else None

    registry.stages.add(stage.__name__, stage)
    run = queued_run(store)
    execute_run(store, run.run_id)
    (status,) = store.stages(run.run_id)
    assert status.state == StageState.SUCCEEDED
    assert status.detail == (stage(run.run_id) or "")
