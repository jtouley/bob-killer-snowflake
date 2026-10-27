"""Read-only views of a WorkbookIR that every generator shares (cell owners, precedents, levels)."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from bob_killer.contracts.ir import (
    CellExpr,
    CellRange,
    CellRef,
    ColumnExprStep,
    Expr,
    Node,
    Operator,
    OpExpr,
    ParamExpr,
    RangeExpr,
    Step,
    VbaProcedureStep,
    VbaStatus,
    WorkbookIR,
    iter_expr,
)

SYMBOLS = {
    Operator.ADD: "+",
    Operator.SUB: "-",
    Operator.MUL: "*",
    Operator.DIV: "/",
    Operator.POW: "^",
    Operator.CONCAT: "&",
    Operator.EQ: "=",
    Operator.NE: "<>",
    Operator.LT: "<",
    Operator.GT: ">",
    Operator.LE: "<=",
    Operator.GE: ">=",
}


def is_generated(step: Step) -> bool:
    """A VBA procedure generates only once its translation is verified (§6)."""
    return not isinstance(step, VbaProcedureStep) or step.status is VbaStatus.TRANSLATED_VERIFIED


def generated_steps(ir: WorkbookIR) -> tuple[Step, ...]:
    return tuple(s for s in ir.steps if is_generated(s))


def owners(ir: WorkbookIR) -> dict[CellRef, Node]:
    """The node that owns each cell: an input, a lookup or a step. A cell has one owner."""
    found: dict[CellRef, Node] = {}
    for node in (*ir.inputs, *ir.lookups, *generated_steps(ir)):
        for ref in node.cells():
            if ref in found:
                raise ValueError(
                    f"{ref.sheet}!R{ref.row}C{ref.col}: owned by {found[ref].id} and {node.id}"
                )
            found[ref] = node
    return found


def referenced_cells(step: Step) -> Iterator[CellRef]:
    """Every cell the step reads, with relative references shifted down a column step."""
    rows = step.ranges()[0].height if isinstance(step, ColumnExprStep) else 1
    for root in step.exprs():
        for node in iter_expr(root):
            if isinstance(node, CellExpr):
                shifts = range(1) if node.row_abs else range(rows)
                for i in shifts:
                    yield CellRef(sheet=node.sheet, row=node.row + i, col=node.col)
            elif isinstance(node, RangeExpr):
                yield from node.as_range().cells()


def precedents(step: Step, owner: Mapping[CellRef, Node]) -> tuple[str, ...]:
    """The ids of the nodes a step reads: owners of its cells, then its parameters."""
    ids: set[str] = set()
    for ref in referenced_cells(step):
        if ref not in owner:
            raise ValueError(f"{step.id}: {ref.sheet}!R{ref.row}C{ref.col} has no owner in the IR")
        ids.add(owner[ref].id)
    ids |= {e.id for root in step.exprs() for e in iter_expr(root) if isinstance(e, ParamExpr)}
    if step.id in ids:
        raise ValueError(f"{step.id}: a step cannot read its own cells")
    return tuple(sorted(ids))


def precedent_map(ir: WorkbookIR) -> dict[str, tuple[str, ...]]:
    """Precedents of every step, with the cell owners computed once."""
    owner = owners(ir)
    return {s.id: precedents(s, owner) for s in ir.steps}


def levels(ir: WorkbookIR) -> dict[str, int]:
    """Topological level of each generated step: 1 + the deepest step it reads (inputs are 0).

    Iterative (Kahn), so a deep calculation chain cannot exhaust the Python stack.
    """
    reads = precedent_map(ir)
    steps = [s.id for s in generated_steps(ir)]
    generated = set(steps)
    deps = {sid: [p for p in reads[sid] if p in generated] for sid in steps}
    waiting = {sid: set(d) for sid, d in deps.items()}
    users: dict[str, list[str]] = {sid: [] for sid in steps}
    for sid, ds in deps.items():
        for d in ds:
            users[d].append(sid)
    ready = deque(sid for sid in steps if not waiting[sid])
    level: dict[str, int] = {}
    while ready:
        sid = ready.popleft()
        level[sid] = 1 + max((level[d] for d in deps[sid]), default=0)
        for user in users[sid]:
            waiting[user].discard(sid)
            if not waiting[user]:
                ready.append(user)
    if len(level) != len(steps):
        raise ValueError(f"cycle among steps {sorted(set(steps) - set(level))}")
    return level


def intersect(a: CellRange, b: CellRange) -> CellRange | None:
    if a.sheet != b.sheet:
        return None
    row, col = max(a.row, b.row), max(a.col, b.col)
    last_row, last_col = min(a.last_row, b.last_row), min(a.last_col, b.last_col)
    if row > last_row or col > last_col:
        return None
    return CellRange(sheet=a.sheet, row=row, col=col, last_row=last_row, last_col=last_col)


def _quote_sheet(sheet: str) -> str:
    return "'" + sheet.replace("'", "''") + "'"


def _op_text(expr: OpExpr) -> str:
    args = [expr_text(a) for a in expr.args]
    if expr.op is Operator.NEG:
        return f"-({args[0]})"
    if expr.op is Operator.PERCENT:
        return f"({args[0]})%"
    return f"({args[0]} {SYMBOLS[expr.op]} {args[1]})"


def _range_text(r: RangeExpr) -> str:
    return f"{_quote_sheet(r.sheet)}!R{r.row}C{r.col}:R{r.last_row}C{r.last_col}"


_TEXT: dict[str, Callable[[Any], str]] = {
    "cell": lambda e: f"{_quote_sheet(e.sheet)}!R{e.row}C{e.col}",
    "range": _range_text,
    "param": lambda e: str(e.id),
    "lit": lambda e: str(e.value.wire()),
    "call": lambda e: f"{e.name}({', '.join(expr_text(a) for a in e.args)})",
    "op": _op_text,
}


def expr_text(expr: Expr) -> str:
    """A readable, Excel-like rendering of an IR expression for docs (R1C1 references)."""
    return _TEXT[expr.type](expr)
