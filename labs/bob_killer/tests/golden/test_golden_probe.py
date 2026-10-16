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
