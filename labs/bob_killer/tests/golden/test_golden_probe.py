"""Every pinned golden through extract, graph and runtime; Excel's cached values are the oracle.

One parametrized module over the resolved entries of golden.lock. Expected values are never
written here: each comes from the workbook's own cache (SPEC, decision 1).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from bob_killer.contracts.golden import GoldenEntry
from tests.golden.conftest import ProbeReport, pinned_goldens

GOLDENS = [pytest.param(e, id=e.id) for e in pinned_goldens()]
Probe = Callable[[GoldenEntry], ProbeReport]


@pytest.mark.parametrize("entry", GOLDENS)
def test_every_formula_parses_or_is_a_named_gap(golden_probe: Probe, entry: GoldenEntry) -> None:
    assert golden_probe(entry).defect_parse_failures == []


@pytest.mark.parametrize("entry", GOLDENS)
def test_graph_has_a_node_per_formula_cell(golden_probe: Probe, entry: GoldenEntry) -> None:
    report = golden_probe(entry)
    assert report.formulas == report.formula_cells


@pytest.mark.parametrize("entry", GOLDENS)
def test_supported_cells_match_excel_exactly(golden_probe: Probe, entry: GoldenEntry) -> None:
    report = golden_probe(entry)
    assert report.mismatches == []
    assert report.matches == report.evaluated


@pytest.mark.parametrize("golden_id", ["mt_dot_budget", "sgec_current"])
def test_every_ir_step_of_the_goal_set_matches_excel_exactly(golden_id: str) -> None:
    """The MVP goal set: each lifted step, from cached precedents, equals its cached value."""
    from bob_killer.extract import extract_workbook
    from bob_killer.graph.dag import build_graph
    from bob_killer.lift import lift
    from bob_killer.verify.config import values_equal
    from tests.conftest import golden_workbook
    from tests.golden.conftest import IrEvaluator, graph_input

    raw = extract_workbook(golden_workbook(golden_id))
    ir = lift(raw, build_graph(graph_input(raw)))
    ev = IrEvaluator(raw)
    mismatches = []
    for step in ir.steps:
        ref = step.cells()[0]
        expected = ev.value(ref.sheet, ref.row, ref.col)
        got = ev.result(step.expr)  # a refusal or a missing function fails the test
        if not values_equal(expected, got):
            mismatches.append((step.origin[0], step.formula, expected, got))
    assert mismatches == []
    assert len(ir.steps) == sum(bool(c.formula) for c in raw.cells)
