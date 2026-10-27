"""The run repository: the store interface that the service, API and CLI depend on."""

from __future__ import annotations

from typing import Protocol

from bob_killer.contracts.runs import Run, RunState, StageStatus


class RunRepository(Protocol):
    def insert_run(self, run: Run) -> None: ...

    def get_run(self, run_id: str) -> Run | None: ...

    def set_state(self, run_id: str, state: RunState) -> None: ...

    def claim_run(self, run_id: str) -> bool:
        """Move the run from ``queued`` to ``running``. True only for the one call that won."""
        ...

    def upsert_stage(self, status: StageStatus) -> None:
        """Insert the stage row, or update it in place so it keeps its insert order (G8)."""
        ...

    def stages(self, run_id: str) -> tuple[StageStatus, ...]:
        """The run's stage rows in insert order."""
        ...
