"""Stage 3, Lift: a RawWorkbook and its CellGraph into a WorkbookIR (core SPEC "Lift").

This first cut lifts every formula cell as a ``scalar_expr`` with an R1C1 fingerprint, every
non-formula cell a formula reads as a scalar input, volatile cells as ``frozen_volatile`` inputs
(D24), and formula cells nothing reads as outputs. Names use the sheet+address fallback of core
decision 3 and are ``needs_review``. A defined name becomes the cell or range it refers to
(sheet scope first, then workbook scope); a missing argument is a blank literal, the value the
golden probe evaluates it to. A formula whose AST has no IR form is ``unsupported``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from bob_killer.contracts import graph as g
from bob_killer.contracts.base import SCHEMA_VERSION
from bob_killer.contracts.ir import (
    CallExpr,
    CellExpr,
    CellRef,
    CellValue,
    Column,
    DType,
    ExcelError,
    Expr,
    Format,
    Input,
    InputKind,
    InputShape,
    LiteralExpr,
    NameRule,
    NameStatus,
    Operator,
    OpExpr,
    Output,
    RangeExpr,
    ScalarExprStep,
    Sheet,
    Source,
    Unsupported,
    WorkbookIR,
    cell_range,
    iter_expr,
)
from bob_killer.contracts.raw import RawWorkbook

FORMULA = "formula"

_BINARY = {
    "^": Operator.POW,
    "*": Operator.MUL,
    "/": Operator.DIV,
    "+": Operator.ADD,
    "-": Operator.SUB,
    "&": Operator.CONCAT,
    "=": Operator.EQ,
    "<>": Operator.NE,
    "<": Operator.LT,
    "<=": Operator.LE,
    ">": Operator.GT,
    ">=": Operator.GE,
}


class NotLiftable(ValueError):
    """The formula uses a form the IR expression language has no node for."""


def _letters(col: int) -> str:
    out = ""
    while col:
        col, rest = divmod(col - 1, 26)
        out = chr(ord("A") + rest) + out
    return out


def a1(ref: CellRef) -> str:
    return "'" + ref.sheet.replace("'", "''") + f"'!{_letters(ref.col)}{ref.row}"


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s if s[:1].isalpha() else f"s_{s}"


Names = Mapping[tuple[str, str], str]
"""(scope, casefolded name) -> refers_to; scope is "" for workbook scope, else the sheet."""


class _Converter:
    def __init__(self, sheet: str, sheets: Mapping[str, str], names: Names) -> None:
        self.sheet = sheet
        self.sheets = sheets
        self.names = names

    def _name(self, sheet: str | None, name: str) -> Expr:
        scope = self._sheet(sheet) if sheet is not None else self.sheet
        key = name.casefold()
        target = self.names.get((scope, key), self.names.get(("", key)))
        if target is None:
            raise NotLiftable(f"unknown name {name!r}")
        try:
            r = cell_range(target)
        except ValueError:
            raise NotLiftable(f"name {name!r} refers to {target!r}") from None
        sheet_name = self._sheet(r.sheet)
        if r.height == 1 and r.width == 1:
            return CellExpr(sheet=sheet_name, row=r.row, col=r.col, row_abs=True, col_abs=True)
        return RangeExpr(
            sheet=sheet_name, row=r.row, col=r.col, last_row=r.last_row, last_col=r.last_col
        )

    def _sheet(self, name: str | None) -> str:
        if name is None:
            return self.sheet
        try:
            return self.sheets[name.casefold()]
        except KeyError:
            raise NotLiftable(f"unknown sheet {name!r}") from None

    def convert(self, e: g.Expr) -> Expr:
        match e:
            case g.Number(value=v):
                return LiteralExpr(value=CellValue.number(v))
            case g.Text(value=v):
                return LiteralExpr(value=CellValue.text(v))
            case g.Boolean(value=v):
                return LiteralExpr(value=CellValue.boolean(v))
            case g.ErrorLiteral(value=v):
                return LiteralExpr(value=CellValue.error(ExcelError(v.value)))
            case g.Missing():
                return LiteralExpr(value=CellValue.blank())
            case g.NameRef(sheet=s, name=n):
                return self._name(s, n)
            case g.CellRef(sheet=s, at=at) if at.row is not None and at.column is not None:
                return CellExpr(
                    sheet=self._sheet(s),
                    row=at.row,
                    col=at.column,
                    row_abs=at.row_absolute,
                    col_abs=at.column_absolute,
                )
            case g.RangeRef(sheet=s, start=a, end=b) if None not in (
                a.row,
                a.column,
                b.row,
                b.column,
            ):
                rows = sorted((a.row or 0, b.row or 0))
                cols = sorted((a.column or 0, b.column or 0))
                return RangeExpr(
                    sheet=self._sheet(s),
                    row=rows[0],
                    col=cols[0],
                    last_row=rows[1],
                    last_col=cols[1],
                )
            case g.UnaryOp(op="+", operand=x):
                return self.convert(x)
            case g.UnaryOp(op=o, operand=x):
                return OpExpr(
                    op=Operator.NEG if o == "-" else Operator.PERCENT, args=(self.convert(x),)
                )
            case g.BinaryOp(op=o, left=left, right=right) if o in _BINARY:
                return OpExpr(op=_BINARY[o], args=(self.convert(left), self.convert(right)))
            case g.Call(name=n, args=args) if re.fullmatch(r"[A-Z][A-Z0-9_.]*", n):
                return CallExpr(name=n, args=tuple(self.convert(a) for a in args))
        raise NotLiftable(f"no IR form for {e.kind}")


def fingerprint(expr: Expr, at: CellRef) -> str:
    """R1C1-normalized text: relative parts become offsets from the formula's own cell."""

    def part(axis: str, value: int, absolute: bool, base: int) -> str:
        return (
            f"{axis}{value}" if absolute else (axis if value == base else f"{axis}[{value - base}]")
        )

    def text(e: Expr) -> str:
        match e:
            case CellExpr():
                where = "" if e.sheet == at.sheet else f"'{e.sheet}'!"
                return (
                    where
                    + part("R", e.row, e.row_abs, at.row)
                    + part("C", e.col, e.col_abs, at.col)
                )
            case RangeExpr():
                where = "" if e.sheet == at.sheet else f"'{e.sheet}'!"
                return f"{where}R{e.row}C{e.col}:R{e.last_row}C{e.last_col}"
            case LiteralExpr():
                return e.value.wire()
            case CallExpr():
                return f"{e.name}({','.join(text(a) for a in e.args)})"
            case OpExpr():
                return f"{e.op.value}({','.join(text(a) for a in e.args)})"
        return e.type

    return "=" + text(expr)


def _key_ref(key: g.CellKey) -> CellRef:
    return CellRef(sheet=key.sheet, row=key.row, col=key.column)


def _node(nid: str, origin: str) -> dict[str, object]:
    return {
        "id": nid,
        "label": origin,
        "origin": (origin,),
        "name_rule": NameRule.SHEET_ADDRESS,
        "name_status": NameStatus.NEEDS_REVIEW,
    }


def lift(raw: RawWorkbook, graph: g.CellGraph, *, file: str = "workbook.xlsx") -> WorkbookIR:
    sheet_ids: dict[str, str] = {}
    sheets = []
    for sh in sorted(raw.sheets, key=lambda x: x.position):
        sid, n = slug(sh.name)[:40], 2
        while sid in sheet_ids.values():
            sid, n = f"{slug(sh.name)[:40]}_{n}", n + 1
        sheet_ids[sh.name] = sid
        sheets.append(Sheet(id=sid, name=sh.name, index=sh.position))
    by_fold = {name.casefold(): name for name in sheet_ids}
    names = {(d.scope, d.name.casefold()): d.refers_to for d in raw.defined_names}

    def node_id(ref: CellRef) -> str:
        return f"{sheet_ids[ref.sheet]}_{_letters(ref.col).lower()}{ref.row}"

    nodes = {n.key: n for n in graph.nodes}
    unsupported: list[Unsupported] = []
    frozen: list[CellRef] = []
    steps: list[ScalarExprStep] = []
    for key in graph.order:
        node, ref = nodes[key], _key_ref(key)
        if node.volatile:
            frozen.append(ref)
            continue
        try:
            if node.ast is None:
                raise NotLiftable(node.error or "no AST")
            if node.unresolved_names or node.dynamic:
                raise NotLiftable("unresolved names or dynamic references")
            expr = _Converter(key.sheet, by_fold, names).convert(node.ast)
        except NotLiftable as exc:
            unsupported.append(Unsupported(kind=FORMULA, origin=a1(ref), reason=str(exc)))
            continue
        steps.append(
            ScalarExprStep(
                **_node(node_id(ref), a1(ref)),  # type: ignore[arg-type]
                expr=expr,
                formula=node.formula,
                fingerprint=fingerprint(expr, ref),
            )
        )
    on_cycle = {k for c in graph.cycles for k in c}
    for key in sorted(on_cycle, key=lambda k: (k.sheet, k.row, k.column)):
        unsupported.append(
            Unsupported(kind=FORMULA, origin=a1(_key_ref(key)), reason="on a calculation cycle")
        )

    # A step that reads an unsupported cell cannot be computed: it becomes unsupported too.
    blocked = {cell_range(u.origin).cells()[0] for u in unsupported}
    computed = {s.cells()[0] for s in steps}
    kept: list[ScalarExprStep] = []
    for s in steps:
        reads = set(_reads(s.expr))
        if reads & blocked:
            blocked |= set(s.cells())
            computed -= set(s.cells())
            unsupported.append(
                Unsupported(kind=FORMULA, origin=s.origin[0], reason="reads an unsupported cell")
            )
        else:
            kept.append(s)

    frozen_set = set(frozen)
    inputs = [
        Input(
            **_node(node_id(r), a1(r)),  # type: ignore[arg-type]
            shape=InputShape.SCALAR,
            kind=InputKind.FROZEN_VOLATILE,
            columns=(Column(name="value", label="value", dtype=DType.CELL),),
        )
        for r in frozen
    ]
    read_cells = {c for s in kept for c in _reads(s.expr)}
    for r in sorted(read_cells - computed - frozen_set, key=lambda c: (c.sheet, c.row, c.col)):
        inputs.append(
            Input(
                **_node(node_id(r), a1(r)),  # type: ignore[arg-type]
                shape=InputShape.SCALAR,
                columns=(Column(name="value", label="value", dtype=DType.CELL),),
            )
        )
    outputs = [
        Output(**_node(f"out_{s.id}"[:63], s.origin[0]), step=s.id, format=Format.GENERAL)  # type: ignore[arg-type]
        for s in kept
        if s.cells()[0] not in read_cells
    ]
    for u in raw.unsupported:
        try:
            cell_range(u.origin)
        except ValueError:
            continue
        if re.fullmatch(r"[a-z][a-z0-9_]*", u.kind):
            unsupported.append(Unsupported(kind=u.kind, origin=u.origin, reason=u.reason))
    return WorkbookIR(
        schema_version=SCHEMA_VERSION,
        source=Source(file=file, sha256=raw.source.sha256),
        sheets=tuple(sheets),
        parameters=(),
        inputs=tuple(inputs),
        lookups=(),
        steps=tuple(kept),
        outputs=tuple(outputs),
        unsupported=tuple(unsupported),
        vba=(),
    )


def _reads(expr: Expr) -> list[CellRef]:
    out: list[CellRef] = []
    for e in iter_expr(expr):
        if isinstance(e, CellExpr):
            out.append(CellRef(sheet=e.sheet, row=e.row, col=e.col))
        elif isinstance(e, RangeExpr):
            out.extend(e.as_range().cells())
    return out
