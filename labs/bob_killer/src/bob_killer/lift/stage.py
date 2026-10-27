"""The ``lift`` stage. Nothing registers at import time; ``register_stages`` is idempotent."""

from __future__ import annotations

from typing import Final, Protocol

from bob_killer import registry
from bob_killer.contracts.graph import CellGraph
from bob_killer.contracts.ir import WorkbookIR
from bob_killer.contracts.raw import RawWorkbook
from bob_killer.lift.core import lift
from bob_killer.registry import Stage

STAGE_NAME: Final = "lift"


class LiftIO(Protocol):
    def load_lift_input(self, run_id: str) -> tuple[RawWorkbook, CellGraph]: ...

    def save_ir(self, run_id: str, ir: WorkbookIR) -> None: ...


def lift_stage(io: LiftIO) -> Stage:
    def run(run_id: str) -> None:
        raw, graph = io.load_lift_input(run_id)
        io.save_ir(run_id, lift(raw, graph))

    return run


def register_stages(io: LiftIO) -> None:
    if STAGE_NAME not in registry.stages:
        registry.stages.add(STAGE_NAME, lift_stage(io))
