"""lift/: RawWorkbook + CellGraph into a WorkbookIR, on every pinned golden.

Expected properties come from the workbook itself (its formula cells), never from literals.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

import fetch_golden

if TYPE_CHECKING:
    from bob_killer.contracts.ir import WorkbookIR
    from bob_killer.contracts.raw import RawWorkbook

PINNED = {e.id: e for e in fetch_golden.load_lock(fetch_golden.LOCK_PATH).workbooks if e.sha256}
GOLDENS = sorted(PINNED)


@pytest.fixture(scope="module")
def pinned_raw() -> Callable[[str], RawWorkbook]:
    """Extract of a golden pinned in golden.lock; a missing file says to run fetch_golden.py."""
    from bob_killer.extract import extract_workbook

    def get(workbook_id: str) -> RawWorkbook:
        entry = PINNED[workbook_id]
        assert entry.filename is not None
        path = fetch_golden.DEST / entry.filename
        assert path.is_file(), f"{path} is missing: run scripts/fetch_golden.py"
        return extract_workbook(path.read_bytes())

    return get


def _lift(raw: RawWorkbook) -> WorkbookIR:
    from bob_killer.contracts.graph import FormulaCell, GraphInput
    from bob_killer.graph.dag import build_graph
    from bob_killer.lift import lift

    graph = build_graph(
        GraphInput(
            cells=tuple(
                FormulaCell(sheet=c.sheet, address=c.address, formula=c.formula)
                for c in raw.cells
                if c.formula
            )
        )
    )
    return lift(raw, graph)


@pytest.mark.parametrize("workbook_id", GOLDENS)
def test_golden_lifts_to_a_valid_ir_that_round_trips(
    workbook_id: str, pinned_raw: Callable[[str], RawWorkbook]
) -> None:
    from bob_killer.contracts.ir import InputKind
    from bob_killer.ir import dump_ir, load_ir

    raw = pinned_raw(workbook_id)
    ir = _lift(raw)
    assert load_ir(dump_ir(ir)) == ir
    formula_cells = sum(1 for c in raw.cells if c.formula)
    lifted = sum(len(s.cells()) for s in ir.steps)
    frozen = sum(len(i.cells()) for i in ir.inputs if i.kind is InputKind.FROZEN_VOLATILE)
    unsupported_formulas = sum(1 for u in ir.unsupported if u.kind == "formula")
    assert lifted + frozen + unsupported_formulas == formula_cells
    assert {o.step for o in ir.outputs} <= {s.id for s in ir.steps}
    print(f"{workbook_id}: steps={len(ir.steps)} outputs={len(ir.outputs)}")


def test_register_stages_is_idempotent() -> None:
    from bob_killer import registry
    from bob_killer.lift.stage import STAGE_NAME, register_stages

    class _IO:
        def load_lift_input(self, run_id: str) -> object: ...

        def save_ir(self, run_id: str, ir: object) -> None: ...

    assert STAGE_NAME not in registry.stages
    register_stages(_IO())  # type: ignore[arg-type]
    register_stages(_IO())  # type: ignore[arg-type]
    assert STAGE_NAME in registry.stages
