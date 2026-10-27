"""The dependency DAG over formula cells: precedents, topological order, cycles and flags.

Only formula cells are nodes. A reference to a constant cell is a leaf input and adds no edge;
a range adds an edge to every formula cell inside it. Excel semantics are not evaluated here.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Hashable, Iterable, Mapping
from typing import Final

from bob_killer.contracts.graph import (
    Anchor,
    CellGraph,
    CellKey,
    CellNode,
    CellRef,
    DefinedName,
    Expr,
    GraphInput,
    NameRef,
    RangeRef,
    Reference,
)
from bob_killer.graph.parser import FormulaError, parse
from bob_killer.graph.refs import cell_anchor
from bob_killer.graph.walk import function_names, references

VOLATILE: Final = frozenset(
    {"NOW", "TODAY", "RAND", "RANDBETWEEN", "OFFSET", "INDIRECT", "INFO", "CELL"}
)
DYNAMIC: Final = frozenset({"INDIRECT", "OFFSET"})


def sort_key(key: CellKey) -> tuple[str, int, int]:
    return key.sheet, key.row, key.column


def toposort[K: Hashable](
    deps: Mapping[K, Iterable[K]],
) -> tuple[tuple[K, ...], tuple[tuple[K, ...], ...]]:
    """Order ``deps`` precedents first; nodes on a cycle are left out and reported per cycle.

    ``deps[n]`` holds the precedents of ``n``; precedents that are not keys are ignored.
    Cycles are the strongly connected components with more than one node or a self-edge.
    """
    succ = {n: [m for m in deps[n] if m in deps] for n in deps}
    rank = {n: i for i, n in enumerate(deps)}
    cycles = [
        tuple(sorted(c, key=rank.__getitem__))
        for c in _components(succ)
        if len(c) > 1 or c[0] in succ[c[0]]
    ]
    cycles.sort(key=lambda c: rank[c[0]])
    on_cycle = {n for c in cycles for n in c}
    remaining = [n for n in deps if n not in on_cycle]
    pending = {n: {m for m in succ[n] if m not in on_cycle} for n in remaining}
    dependents: dict[K, list[K]] = {n: [] for n in remaining}
    for n in remaining:
        for m in pending[n]:
            dependents[m].append(n)
    ready = deque(n for n in remaining if not pending[n])
    order: list[K] = []
    while ready:
        n = ready.popleft()
        order.append(n)
        for d in dependents[n]:
            pending[d].discard(n)
            if not pending[d]:
                ready.append(d)
    return tuple(order), tuple(cycles)


def _components[K: Hashable](succ: Mapping[K, list[K]]) -> list[list[K]]:
    """Tarjan's strongly connected components, iterative (no recursion limit)."""
    index: dict[K, int] = {}
    low: dict[K, int] = {}
    stack: list[K] = []
    on_stack: set[K] = set()
    found: list[list[K]] = []

    def visit(v: K) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on_stack.add(v)

    for root in succ:
        if root in index:
            continue
        visit(root)
        work = [(root, iter(succ[root]))]
        while work:
            v, edges = work[-1]
            for w in edges:
                if w not in index:
                    visit(w)
                    work.append((w, iter(succ[w])))
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[v])
                if low[v] == index[v]:
                    component: list[K] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        component.append(w)
                        if w == v:
                            break
                    found.append(component)
    return found


def _within(lo: int | None, hi: int | None, value: int) -> bool:
    if lo is None or hi is None:
        return True
    return min(lo, hi) <= value <= max(lo, hi)


class _Resolver:
    def __init__(self, data: GraphInput) -> None:
        self.by_sheet: dict[str, list[CellKey]] = {}
        self.names: dict[tuple[str | None, str], DefinedName] = {}
        self._parsed: dict[tuple[str | None, str], Expr | None] = {}
        for n in data.names:
            scope = None if n.scope is None else n.scope.casefold()
            self.names[(scope, n.name.casefold())] = n

    def add(self, key: CellKey) -> None:
        self.by_sheet.setdefault(key.sheet.casefold(), []).append(key)

    def _cells(self, sheet: str, start: Anchor, end: Anchor) -> Iterable[CellKey]:
        return (
            k
            for k in self.by_sheet.get(sheet.casefold(), ())
            if _within(start.column, end.column, k.column) and _within(start.row, end.row, k.row)
        )

    def _name(self, ref: NameRef, sheet: str) -> tuple[tuple[str | None, str], Expr | None] | None:
        scopes = [ref.sheet] if ref.sheet is not None else [sheet, None]
        for scope in scopes:
            slot = (None if scope is None else scope.casefold(), ref.name.casefold())
            if slot in self.names:
                if slot not in self._parsed:
                    text = self.names[slot].refers_to
                    try:
                        self._parsed[slot] = parse(text if text.startswith("=") else "=" + text)
                    except FormulaError:
                        self._parsed[slot] = None
                return slot, self._parsed[slot]
        return None

    def resolve(
        self, refs: Iterable[Reference], sheet: str, seen: frozenset[tuple[str | None, str]]
    ) -> tuple[set[CellKey], set[str]]:
        cells: set[CellKey] = set()
        unresolved: set[str] = set()
        for ref in refs:
            match ref:
                case CellRef(at=at):
                    cells.update(self._cells(ref.sheet or sheet, at, at))
                case RangeRef(start=start, end=end):
                    cells.update(self._cells(ref.sheet or sheet, start, end))
                case NameRef():
                    found = self._name(ref, sheet)
                    if found is None or found[1] is None:
                        unresolved.add(ref.name)
                    elif found[0] not in seen:
                        more, missing = self.resolve(references(found[1]), sheet, seen | {found[0]})
                        cells |= more
                        unresolved |= missing
        return cells, unresolved


def _key(sheet: str, address: str) -> CellKey:
    anchor = cell_anchor(address.replace("$", ""))
    if anchor is None or anchor.column is None or anchor.row is None:
        raise ValueError(f"address {sheet}!{address} is outside the sheet")
    return CellKey(sheet=sheet, column=anchor.column, row=anchor.row)


def _node(key: CellKey, formula: str, resolver: _Resolver) -> CellNode:
    try:
        ast = parse(formula)
    except FormulaError as exc:
        return CellNode(key=key, formula=formula, error=str(exc))
    refs = references(ast)
    cells, unresolved = resolver.resolve(refs, key.sheet, frozenset())
    called = set(function_names(ast))
    return CellNode(
        key=key,
        formula=formula,
        ast=ast,
        references=refs,
        precedents=tuple(sorted(cells, key=sort_key)),
        volatile=tuple(sorted(called & VOLATILE)),
        dynamic=tuple(sorted(called & DYNAMIC)),
        unresolved_names=tuple(sorted(unresolved)),
    )


def build_graph(data: GraphInput) -> CellGraph:
    resolver = _Resolver(data)
    formulas: dict[CellKey, str] = {}
    for cell in data.cells:
        key = _key(cell.sheet, cell.address)
        if key in formulas:
            raise ValueError(f"duplicate cell {cell.sheet}!{cell.address}")
        formulas[key] = cell.formula
        resolver.add(key)
    nodes = tuple(_node(k, formulas[k], resolver) for k in sorted(formulas, key=sort_key))
    order, cycles = toposort({n.key: n.precedents for n in nodes})
    return CellGraph(nodes=nodes, order=order, cycles=cycles)
