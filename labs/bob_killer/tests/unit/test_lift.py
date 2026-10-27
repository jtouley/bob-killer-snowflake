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


# --- defined names and missing arguments (MVP goal set) --------------------------------------------


def _lift_with_names(raw: RawWorkbook) -> WorkbookIR:
    """Lift over the graph of every formula cell and every defined name (the Workspace input)."""
    from bob_killer.graph.dag import build_graph
    from bob_killer.lift import lift
    from tests.golden.conftest import graph_input

    return lift(raw, build_graph(graph_input(raw)))


@pytest.mark.parametrize("workbook_id", ["mt_dot_budget", "sgec_current"])
def test_every_formula_cell_of_the_goal_set_lifts(
    workbook_id: str, pinned_raw: Callable[[str], RawWorkbook]
) -> None:
    raw = pinned_raw(workbook_id)
    ir = _lift_with_names(raw)
    formulas = [c for c in raw.cells if c.formula]
    from bob_killer.lift.core import FORMULA

    assert [u for u in ir.unsupported if u.kind == FORMULA] == []
    assert len(ir.steps) == len(formulas)


def test_a_defined_name_reads_the_cells_it_refers_to(
    pinned_raw: Callable[[str], RawWorkbook],
) -> None:
    import re

    from bob_killer.contracts.ir import CellRef, cell_range
    from bob_killer.lift.core import _reads

    raw = pinned_raw("sgec_current")
    ir = _lift_with_names(raw)
    names = {d.name.casefold(): d.refers_to for d in raw.defined_names if d.scope == ""}
    checked = 0
    for step in ir.steps:
        words = {w.casefold() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", step.formula)}
        reads = set(_reads(step.expr))
        for word in words & names.keys():
            try:
                target = cell_range(names[word])
            except ValueError:
                continue
            cells = {CellRef(sheet=c.sheet, row=c.row, col=c.col) for c in target.cells()}
            assert cells <= reads, (step.origin, word)
            checked += 1
    assert checked


def test_a_missing_argument_lifts_to_a_blank_literal(
    pinned_raw: Callable[[str], RawWorkbook],
) -> None:
    from bob_killer.contracts.graph import Missing
    from bob_killer.contracts.ir import CellValue, LiteralExpr, iter_expr
    from bob_killer.graph.dag import build_graph
    from bob_killer.graph.walk import walk
    from tests.golden.conftest import graph_input

    raw = pinned_raw("mt_dot_budget")
    graph = build_graph(graph_input(raw))
    with_missing = {
        (n.key.sheet, n.key.row, n.key.column)
        for n in graph.nodes
        if n.ast is not None and any(isinstance(x, Missing) for x in walk(n.ast))
    }
    assert with_missing
    steps = {
        (s.cells()[0].sheet, s.cells()[0].row, s.cells()[0].col): s
        for s in _lift_with_names(raw).steps
    }
    for key in with_missing:
        literals = [e for e in iter_expr(steps[key].expr) if isinstance(e, LiteralExpr)]
        assert CellValue.blank() in [e.value for e in literals]


@pytest.mark.parametrize("workbook_id", ["mt_dot_budget", "sgec_current"])
def test_input_cells_lift_as_maximal_rectangles(
    workbook_id: str, pinned_raw: Callable[[str], RawWorkbook]
) -> None:
    """Inputs are disjoint rectangles covering exactly the read constant cells. Each column of a
    rectangle is a whole run of consecutive read rows; a neighbour to the right has another run."""
    from bob_killer.contracts.ir import CellRef, InputKind, InputShape
    from bob_killer.lift.core import _reads

    ir = _lift_with_names(pinned_raw(workbook_id))
    computed = {c for s in ir.steps for c in s.cells()}
    wanted = {c for s in ir.steps for c in _reads(s.expr)} - computed
    inputs = [i for i in ir.inputs if i.kind is InputKind.INPUT]
    owner = {c: i.ranges()[0] for i in inputs for c in i.cells()}
    assert sum(len(i.cells()) for i in inputs) == len(owner)
    assert set(owner) == wanted
    for i in inputs:
        r = i.ranges()[0]
        assert (i.shape is InputShape.SCALAR) == (len(i.cells()) == len(i.columns) == r.height)
        assert len(i.columns) == r.width
        for col in range(r.col, r.last_col + 1):
            outside = (CellRef(sheet=r.sheet, row=n, col=col) for n in (r.row - 1, r.last_row + 1))
            assert not [c for c in outside if c in wanted], (i.id, col)
        right = owner.get(CellRef(sheet=r.sheet, row=r.row, col=r.last_col + 1))
        if right is not None:
            assert (right.row, right.last_row) != (r.row, r.last_row), i.id
    assert len(inputs) < len(wanted)
