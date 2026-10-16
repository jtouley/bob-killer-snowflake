"""graph/dag.py and graph/stage.py: dependency DAG, topological order, cycles, volatile flags."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bob_killer import registry
from bob_killer.contracts.graph import (
    CellGraph,
    CellKey,
    CellNode,
    DefinedName,
    FormulaCell,
    GraphInput,
)
from bob_killer.graph.dag import build_graph, toposort
from bob_killer.graph.stage import STAGE_NAME, register_stages
from bob_killer.registry import Registry

SHEET = "Sheet1"


def key(address: str, sheet: str = SHEET) -> CellKey:
    """A key from an address, written independently of the parser (single-letter columns)."""
    return CellKey(sheet=sheet, column=ord(address[0]) - ord("A") + 1, row=int(address[1:]))


def graph_of(
    cells: Sequence[tuple[str, str] | tuple[str, str, str]], names: Sequence[DefinedName] = ()
) -> CellGraph:
    built = [
        FormulaCell(sheet=c[2] if len(c) == 3 else SHEET, address=c[0], formula=c[1]) for c in cells
    ]
    return build_graph(GraphInput(cells=tuple(built), names=tuple(names)))


def node(graph: CellGraph, k: CellKey) -> CellNode:
    return next(n for n in graph.nodes if n.key == k)


@pytest.mark.parametrize(
    ("cells", "names", "target", "expected"),
    [
        pytest.param([("B1", "=A1+1"), ("A1", "=1")], (), key("B1"), (key("A1"),), id="cell"),
        pytest.param([("B1", "=Z9")], (), key("B1"), (), id="constant-cell-is-not-a-node"),
        pytest.param(
            [("C1", "=SUM(A1:A3)"), ("A2", "=1"), ("A4", "=1")],
            (),
            key("C1"),
            (key("A2"),),
            id="range-covers-formula-cells",
        ),
        pytest.param(
            [("C1", "=SUM(A:A)"), ("A2", "=1"), ("A9", "=2"), ("B1", "=3")],
            (),
            key("C1"),
            (key("A2"), key("A9")),
            id="whole-column",
        ),
        pytest.param(
            [("A1", "=Data!B2"), ("B2", "=1", "Data"), ("B2", "=1")],
            (),
            key("A1"),
            (key("B2", "Data"),),
            id="cross-sheet",
        ),
        pytest.param(
            [("A1", "='My Data'!B2*2"), ("B2", "=1", "My Data")],
            (),
            key("A1"),
            (key("B2", "My Data"),),
            id="quoted-sheet",
        ),
        pytest.param(
            [("B1", "=Rate*2"), ("A1", "=1")],
            (DefinedName(name="Rate", refers_to="=Sheet1!$A$1"),),
            key("B1"),
            (key("A1"),),
            id="defined-name",
        ),
        pytest.param(
            [("B1", "=rate*2"), ("A1", "=1"), ("A2", "=1")],
            (
                DefinedName(name="Rate", refers_to="=Sheet1!$A$1"),
                DefinedName(name="Rate", scope=SHEET, refers_to="=Sheet1!$A$2"),
            ),
            key("B1"),
            (key("A2"),),
            id="sheet-scope-wins-case-insensitive",
        ),
        pytest.param(
            [("B1", "=Total"), ("A1", "=1"), ("A2", "=1")],
            (
                DefinedName(name="Total", refers_to="=Part+Sheet1!$A$2"),
                DefinedName(name="Part", refers_to="=Sheet1!$A$1"),
            ),
            key("B1"),
            (key("A1"), key("A2")),
            id="name-refers-to-name",
        ),
        pytest.param(
            [("B1", "=OFFSET(A1,1,1)"), ("A1", "=1")],
            (),
            key("B1"),
            (key("A1"),),
            id="dynamic-keeps-static-args",
        ),
    ],
)
def test_precedents(
    cells: Sequence[tuple[str, str]],
    names: Sequence[DefinedName],
    target: CellKey,
    expected: tuple[CellKey, ...],
) -> None:
    assert node(graph_of(cells, names), target).precedents == expected


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        pytest.param("=Nope+1", ("Nope",), id="undefined"),
        pytest.param("=Sheet1!Nope+Also", ("Also", "Nope"), id="sorted"),
    ],
)
def test_unresolved_names_are_reported(formula: str, expected: tuple[str, ...]) -> None:
    assert node(graph_of([("A1", formula)]), key("A1")).unresolved_names == expected


def test_chain_is_ordered_precedents_first() -> None:
    graph = graph_of([("C1", "=B1"), ("B1", "=A1"), ("A1", "=1")])
    assert graph.order == (key("A1"), key("B1"), key("C1"))
    assert graph.cycles == ()


@pytest.mark.parametrize(
    ("cells", "members", "ordered"),
    [
        pytest.param(
            [("A1", "=B1"), ("B1", "=A1"), ("C1", "=A1")],
            {key("A1"), key("B1")},
            (key("C1"),),
            id="two-cell-cycle",
        ),
        pytest.param([("A1", "=A1+1")], {key("A1")}, (), id="self-reference"),
        pytest.param(
            [("A1", "=SUM(A1:A3)"), ("A2", "=1")], {key("A1")}, (key("A2"),), id="range-self"
        ),
    ],
)
def test_cycles_report_members(
    cells: Sequence[tuple[str, str]], members: set[CellKey], ordered: tuple[CellKey, ...]
) -> None:
    graph = graph_of(cells)
    assert [set(c) for c in graph.cycles] == [members]
    assert graph.order == ordered


def test_parse_error_is_recorded_on_the_node() -> None:
    graph = graph_of([("A1", "=SUM(")])
    bad = node(graph, key("A1"))
    assert bad.ast is None
    assert bad.error
    assert graph.order == (key("A1"),)


def test_duplicate_cell_is_rejected() -> None:
    with pytest.raises(ValueError, match="A1"):
        graph_of([("A1", "=1"), ("A1", "=2")])


@pytest.mark.parametrize(
    ("formula", "volatile", "dynamic"),
    [
        pytest.param("=SUM(A1)", (), (), id="stable"),
        pytest.param("=NOW()", ("NOW",), (), id="now"),
        pytest.param("=TODAY()", ("TODAY",), (), id="today"),
        pytest.param("=RAND()", ("RAND",), (), id="rand"),
        pytest.param("=RANDBETWEEN(1,2)", ("RANDBETWEEN",), (), id="randbetween"),
        pytest.param('=INFO("osversion")', ("INFO",), (), id="info"),
        pytest.param('=CELL("row",A1)', ("CELL",), (), id="cell"),
        pytest.param("=INDIRECT(A1)", ("INDIRECT",), ("INDIRECT",), id="indirect"),
        pytest.param(
            "=SUM(OFFSET(A1,1,1),RAND(),now())",
            ("NOW", "OFFSET", "RAND"),
            ("OFFSET",),
            id="sorted-and-deduplicated",
        ),
    ],
)
def test_volatile_and_dynamic_flags(
    formula: str, volatile: tuple[str, ...], dynamic: tuple[str, ...]
) -> None:
    flagged = node(graph_of([("B9", formula)]), key("B9"))
    assert flagged.volatile == volatile
    assert flagged.dynamic == dynamic


# --- property tests on toposort ------------------------------------------------------------------


def _reach(deps: Mapping[int, set[int]]) -> dict[int, set[int]]:
    """Transitive closure by brute force to a fixed point: the oracle for cycle membership."""
    reach = {n: set(d) for n, d in deps.items()}
    changed = True
    while changed:
        changed = False
        for src in deps:
            grown = reach[src].union(*(reach[m] for m in reach[src]))
            if grown != reach[src]:
                reach[src], changed = grown, True
    return reach


graphs = st.integers(0, 10).flatmap(
    lambda n: st.fixed_dictionaries(
        {i: st.sets(st.integers(0, n - 1), max_size=n) if n else st.just(set()) for i in range(n)}
    )
)


def _dags(n: int) -> st.SearchStrategy[dict[int, set[int]]]:
    order = st.permutations(range(n))
    return order.flatmap(
        lambda perm: st.fixed_dictionaries(
            {
                perm[i]: st.sets(st.sampled_from(perm[:i]), max_size=i) if i else st.just(set())
                for i in range(n)
            }
        )
    )


def _assert_valid_order(deps: Mapping[int, set[int]], order: Sequence[int]) -> None:
    index = {n: i for i, n in enumerate(order)}
    for n, precedents in deps.items():
        for p in precedents:
            if n in index and p in index:
                assert index[p] < index[n]


@given(st.integers(0, 10).flatmap(_dags))
def test_any_dag_gets_a_valid_topological_order(deps: dict[int, set[int]]) -> None:
    order, cycles = toposort(deps)
    assert sorted(order) == sorted(deps)
    assert cycles == ()
    _assert_valid_order(deps, order)


@given(graphs)
def test_any_cycle_is_reported_with_its_members(deps: dict[int, set[int]]) -> None:
    order, cycles = toposort(deps)
    reach = _reach(deps)
    in_cycle = {n for n in deps if n in reach[n]}
    expected = {
        frozenset({m for m in in_cycle if m in reach[n] and n in reach[m]}) for n in in_cycle
    }
    assert {frozenset(c) for c in cycles} == expected
    assert set(order) == set(deps) - in_cycle
    assert len(order) + sum(len(c) for c in cycles) == len(deps)
    _assert_valid_order(deps, order)


# --- stage registration ------------------------------------------------------------------------


class MemoryIO:
    def __init__(self, data: GraphInput) -> None:
        self.data = data
        self.saved: dict[str, CellGraph] = {}

    def load_graph_input(self, run_id: str) -> GraphInput:
        return self.data

    def save_cell_graph(self, run_id: str, graph: CellGraph) -> None:
        self.saved[run_id] = graph


def test_register_stages_is_idempotent_and_runs_the_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "stages", Registry("stages"))
    data = GraphInput(cells=(FormulaCell(sheet=SHEET, address="A1", formula="=1"),))
    io = MemoryIO(data)
    register_stages(io)
    register_stages(io)
    assert registry.stages.names() == (STAGE_NAME,)
    run_id = "run-1"
    registry.stages.get(STAGE_NAME)(run_id)
    assert list(io.saved) == [run_id]
    assert io.saved[run_id] == build_graph(data)
