"""The ``generate`` stage: a run's IR through every registered generator (§3.4).

Reviews are applied first (core decision 3: generation fails while an output-facing name needs
review). The stage writes the generated files and the run's input cells (the cached value of
each IR input cell, the only workbook data a model reads, D22) through the host's ``GenerateIO``.
Nothing registers at import time; ``register_stages`` is idempotent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol

import bob_killer.generate.dbt  # noqa: F401  (registers "dbt")
import bob_killer.generate.docs  # noqa: F401  (registers "docs")
from bob_killer import registry
from bob_killer.contracts.ir import CellRef, CellValue, GeneratedProject, TargetConfig, WorkbookIR
from bob_killer.contracts.workbook import NameReview, WbInputCell
from bob_killer.generate.base import run_generators
from bob_killer.ir.reviews import apply_reviews
from bob_killer.registry import Stage

STAGE_NAME: Final = "generate"


class GenerateIO(Protocol):
    def load_ir(self, run_id: str) -> WorkbookIR: ...

    def cell_values(self, run_id: str) -> Mapping[CellRef, CellValue]: ...

    def reviews(self, ir: WorkbookIR) -> tuple[NameReview, ...]: ...

    def target(self, run_id: str) -> TargetConfig: ...

    def write_project(self, run_id: str, project: GeneratedProject) -> None: ...

    def write_input_cells(self, run_id: str, rows: tuple[WbInputCell, ...]) -> None: ...


def input_cells(
    run_id: str, ir: WorkbookIR, values: Mapping[CellRef, CellValue]
) -> tuple[WbInputCell, ...]:
    """One row per cell of every IR input, its cached value as a wire object."""
    return tuple(
        WbInputCell(
            run_id=run_id,
            sheet=ref.sheet,
            cell_row=ref.row,
            cell_col=ref.col,
            node_id=node.id,
            value=values[ref],
        )
        for node in ir.inputs
        for ref in node.cells()
    )


def generate_stage(io: GenerateIO) -> Stage:
    def run(run_id: str) -> str:
        ir = io.load_ir(run_id)
        ir = apply_reviews(ir, io.reviews(ir))
        values = io.cell_values(run_id)
        project = run_generators(ir, io.target(run_id), values)
        io.write_project(run_id, project)
        rows = input_cells(run_id, ir, values)
        io.write_input_cells(run_id, rows)
        return f"{len(project.files)} files, {len(rows)} input cells"

    return run


def register_stages(io: GenerateIO) -> None:
    if STAGE_NAME not in registry.stages:
        registry.stages.add(STAGE_NAME, generate_stage(io))
