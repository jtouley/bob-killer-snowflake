"""The golden probe: every pinned golden through extract, graph and runtime, against Excel's cache.

The oracle is the workbook itself (SPEC, decision 1): a formula cell's expected value is the value
Excel saved for it. A cell is evaluated only when its AST uses literals, same-sheet cell or range
references and functions registered in ``registry.functions``; every input it reads is the cached
value of the referenced cell. Everything else is counted as a coverage gap, never guessed.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import bob_killer.runtime.functions  # noqa: F401  (registers the Excel functions)
from bob_killer.contracts.golden import GoldenEntry, GoldenStatus
from bob_killer.contracts.graph import (
    BinaryOp,
    Boolean,
    Call,
    CellGraph,
    CellKey,
    CellNode,
    CellRef,
    DefinedName,
    ErrorLiteral,
    Expr,
    FormulaCell,
    GraphInput,
    Missing,
    Number,
    RangeRef,
    Text,
    UnaryOp,
)
from bob_killer.contracts.raw import CachedType, RawCell, RawWorkbook
from bob_killer.graph.dag import build_graph
from bob_killer.graph.walk import walk
from bob_killer.registry import functions
from bob_killer.runtime.operators import SYMBOLS, UNARY_SYMBOLS
from bob_killer.runtime.values import Area
from bob_killer.runtime.coercion import Arg, CellValue, ExcelError, UnsupportedValue, cell_result
from bob_killer.verify.config import values_equal

# Error-message prefixes of graph/refs.py for reference forms the graph stage does not support yet.
UNSUPPORTED_FORMS = (
    "external workbook reference",
    "3D reference",
    "reference ",
    "unsupported function reference",
)
_LITERALS = (Number, Text, Boolean, ErrorLiteral, Missing)


def pinned_goldens() -> list[GoldenEntry]:
    import fetch_golden

    lock = fetch_golden.load_lock(fetch_golden.LOCK_PATH)
    return [e for e in lock.workbooks if e.status is GoldenStatus.RESOLVED]


def golden_bytes(entry: GoldenEntry) -> bytes:
    """The pinned file from golden/, fetched and hash-checked when absent or changed."""
    import fetch_golden

    assert entry.filename is not None
    path: Path = fetch_golden.DEST / entry.filename
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry.sha256:
        fetch_golden.fetch_entry(entry, fetch_golden.DEST, accept=False)
    return path.read_bytes()


def cached(cell: RawCell | None) -> CellValue | None:
    """Excel's saved value as a runtime value. Raises LookupError when there is none to use."""
    if cell is None:
        return None
    match cell.cached_type:
        case CachedType.NUMBER:
            return float(cell.cached_value)
        case CachedType.STRING:
            return cell.cached_value
        case CachedType.BOOL:
            return cell.cached_value == "TRUE"
        case CachedType.ERROR:
            return ExcelError(cell.cached_value)
        case CachedType.BLANK:
            return None
    raise LookupError(f"cached value is {cell.cached_type}")


def graph_input(raw: RawWorkbook) -> GraphInput:
    return GraphInput(
        cells=tuple(
            FormulaCell(sheet=c.sheet, address=c.address, formula=c.formula)
            for c in raw.cells
            if c.formula
        ),
        names=tuple(
            DefinedName(name=n.name, scope=n.scope or None, refers_to=n.refers_to)
            for n in raw.defined_names
        ),
    )


class Ineligible(Exception):
    """The cell is outside the supported path; the message is the coverage-gap class."""


@dataclass
class Mismatch:
    address: str
    formula: str
    expected: object
    got: object


@dataclass
class ProbeReport:
    cells: int = 0
    formula_cells: int = 0
    formulas: int = 0
    parse_failures: Counter[str] = field(default_factory=Counter)
    defect_parse_failures: list[tuple[str, str, str]] = field(default_factory=list)
    cycles: int = 0
    volatile: int = 0
    evaluated: int = 0
    matches: int = 0
    gaps: Counter[str] = field(default_factory=Counter)
    gap_cells: dict[str, list[str]] = field(default_factory=dict)
    mismatches: list[Mismatch] = field(default_factory=list)


class Evaluator:
    """Evaluates one formula cell's AST on the cached values of the cells it reads."""

    def __init__(self, raw: RawWorkbook) -> None:
        self.cells: dict[tuple[str, int, int], RawCell] = {}
        for c in raw.cells:
            key = build_key(c.sheet, c.address)
            self.cells[(c.sheet, key.row, key.column)] = c

    def value(self, sheet: str, row: int, column: int) -> CellValue:
        try:
            return cached(self.cells.get((sheet, row, column)))
        except LookupError as exc:
            raise Ineligible(f"reads a cell whose {exc}") from exc

    def eval(self, expr: Expr, sheet: str) -> Arg:
        match expr:
            case Number(value=v) | Boolean(value=v):
                return v
            case Text(value=v):
                return v
            case ErrorLiteral(value=v):
                return ExcelError(v.value)
            case Missing():
                return None
            case CellRef(at=at):
                assert at.row is not None and at.column is not None
                return (self.value(sheet, at.row, at.column),)
            case RangeRef(start=s, end=e):
                if None in (s.row, s.column, e.row, e.column):
                    raise Ineligible("whole-row or whole-column range")
                assert s.row and s.column and e.row and e.column
                first, last = min(s.column, e.column), max(s.column, e.column)
                return Area(
                    (
                        self.value(sheet, r, c)
                        for r in range(min(s.row, e.row), max(s.row, e.row) + 1)
                        for c in range(first, last + 1)
                    ),
                    columns=last - first + 1,
                )
            case Call(name=name, args=args):
                return self.call(name, args, sheet)
            case UnaryOp(op="+", operand=x):
                return self.eval(x, sheet)
            case UnaryOp(op=op, operand=x):
                return self.call(f"OP_{UNARY_SYMBOLS[op]}", (x,), sheet)
            case BinaryOp(op=op, left=left, right=right):
                return self.call(f"OP_{SYMBOLS[op]}", (left, right), sheet)
        raise Ineligible(type(expr).__name__)

    def call(self, name: str, args: tuple[Expr, ...], sheet: str) -> Arg:
        result: Arg = functions.get(name)(*(self.eval(a, sheet) for a in args))  # type: ignore[assignment]
        return result

    def check(self, node: CellNode) -> None:
        """Raise Ineligible unless the AST is on the supported path."""
        assert node.ast is not None
        for n in walk(node.ast):
            match n:
                case Call(name=name) if name not in functions:
                    raise Ineligible(f"function {name} not in the registry")
                case CellRef(sheet=s) | RangeRef(sheet=s) if s is not None and s != node.key.sheet:
                    raise Ineligible("cross-sheet reference")
                case BinaryOp(op=op) if op not in SYMBOLS:
                    raise Ineligible(f"reference operator {op!r}")
                case Call() | CellRef() | RangeRef() | UnaryOp() | BinaryOp():
                    continue
                case _ if not isinstance(n, _LITERALS):
                    raise Ineligible(f"{type(n).__name__} node")

    def result(self, node: CellNode) -> CellValue:
        self.check(node)
        try:
            out = self.eval(node.ast, node.key.sheet)  # type: ignore[arg-type]
        except UnsupportedValue as exc:
            raise Ineligible("runtime refuses the input (UnsupportedValue)") from exc
        if isinstance(out, tuple):
            if len(out) != 1:
                raise Ineligible("array result")
            out = out[0]
        return cell_result(out)


def build_key(sheet: str, address: str) -> CellKey:
    from bob_killer.graph.refs import cell_anchor

    anchor = cell_anchor(address.replace("$", ""))
    assert anchor is not None and anchor.row is not None and anchor.column is not None
    return CellKey(sheet=sheet, column=anchor.column, row=anchor.row)


def parse_reason(error: str) -> str:
    return next((form for form in UNSUPPORTED_FORMS if error.startswith(form)), error)


def probe(raw: RawWorkbook) -> ProbeReport:
    graph: CellGraph = build_graph(graph_input(raw))
    report = ProbeReport(
        cells=len(raw.cells),
        formula_cells=sum(bool(c.formula) for c in raw.cells),
        formulas=len(graph.nodes),
    )
    report.cycles = len(graph.cycles)
    report.volatile = sum(bool(n.volatile) for n in graph.nodes)
    ev = Evaluator(raw)
    for node in graph.nodes:
        cell = ev.cells[(node.key.sheet, node.key.row, node.key.column)]
        address = f"{cell.sheet}!{cell.address}"
        if node.error is not None:
            reason = parse_reason(node.error)
            report.parse_failures[reason] += 1
            if reason not in UNSUPPORTED_FORMS:
                report.defect_parse_failures.append((address, node.formula, node.error))
            continue
        try:
            expected = cached(cell)
            got = ev.result(node)
        except (Ineligible, LookupError) as exc:
            report.gaps[str(exc)] += 1
            report.gap_cells.setdefault(str(exc), []).append(address)
            continue
        report.evaluated += 1
        if values_equal(expected, got):  # type: ignore[arg-type]
            report.matches += 1
        else:
            report.mismatches.append(Mismatch(address, node.formula, expected, got))
    return report


@pytest.fixture(scope="session")
def golden_probe() -> Callable[[GoldenEntry], ProbeReport]:
    from bob_killer.extract import extract_workbook

    reports: dict[str, ProbeReport] = {}

    def get(entry: GoldenEntry) -> ProbeReport:
        if entry.id not in reports:
            reports[entry.id] = probe(extract_workbook(golden_bytes(entry)))
        return reports[entry.id]

    return get
