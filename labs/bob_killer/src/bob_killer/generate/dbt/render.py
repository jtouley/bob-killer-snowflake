"""Expression renderer: IR expression AST -> Snowflake SQL with dbt macro calls (§4.1, D20, D21).

Only the SQL-exact set renders as plain SQL: cell references, parameter references and literals.
Every function call renders as ``{{ bk_fn('<NAME>') }}(ARRAY_CONSTRUCT(<args>))`` and every
operator as ``{{ bk_op('<OP>') }}(ARRAY_CONSTRUCT(<args>))``: each BK_* UDF built from
``runtime/`` takes its positional arguments as one array (hosts/snowflake/udfs.py). A one-cell
reference argument is a one-element array (a reference, which Excel functions treat apart from a
typed value); a range is ``{"cols": <columns>, "cells": ARRAY_AGG(...)}`` in Excel order (F23).

IF is lazy, as in Excel: a scalar subquery binds ``IF(<condition>, m1, m2)`` once (the runtime
IF returns marker m1 or m2 for the chosen branch, or the condition's error), and a ``CASE``
evaluates only the chosen branch. A branch Excel never evaluates can then never fail the model.
``cell_value`` gives a step's cell value: a one-cell reference unwrapped, a blank shown as 0.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from bob_killer.contracts.ir import (
    RANGE_CELLS,
    RANGE_COLUMNS,
    CellExpr,
    CellRange,
    CellRef,
    CellValue,
    Expr,
    Input,
    LiteralExpr,
    Node,
    RangeExpr,
    WorkbookIR,
)
from bob_killer.ir.analysis import intersect, owners
from bob_killer.registry import Registry

_ESCAPES = {"\\": "\\\\", "'": "\\'", "{": "\\x7b", "}": "\\x7d"}


def sql_string(text: str) -> str:
    """A Snowflake string literal that dbt's Jinja cannot read as a tag (braces are hex escapes)."""
    return "'" + "".join(_ESCAPES.get(ch, ch) for ch in text) + "'"


def ident(name: str) -> str:
    """Every identifier is quoted by the one macro ``bk_ident`` (§3.5)."""
    return "{{ bk_ident(" + sql_string(name) + ") }}"


def ref(model: str) -> str:
    return "{{ ref(" + sql_string(model) + ") }}"


SHEET, ROW, COL, NODE_ID, VALUE = (ident(c) for c in ("sheet", "row", "col", "node_id", "value"))
ARGS = "ARRAY_CONSTRUCT"  # every UDF call's one argument: its positional arguments
IF_BRANCHES = (1.0, 2.0)  # markers: IF returns the chosen one unchanged


def _wire(value: CellValue) -> str:
    return f"PARSE_JSON({sql_string(value.wire())})"


def cell_value(sql: str) -> str:
    """A step's cell value: a one-cell reference unwrapped, a blank result shown as 0 (IF page)."""
    zero = _wire(CellValue.number(0.0))
    return (
        f"(SELECT IFF(_c:k::VARCHAR = 'z', {zero}, _c) FROM (SELECT IFF(IS_ARRAY(_v) "
        f"AND ARRAY_SIZE(_v) = 1, _v[0], _v) AS _c FROM (SELECT {sql} AS _v)))"
    )


@dataclass(frozen=True)
class Scope:
    """Where an expression is evaluated: one cell, or row-wise over a column step's input."""

    anchor_row: int | None = None
    height: int = 1
    over: str | None = None

    def rows(self, expr: CellExpr) -> range:
        """The rows a reference reads across the scope (one row unless it is relative)."""
        if self.anchor_row is None or expr.row_abs:
            return range(expr.row, expr.row + 1)
        return range(expr.row, expr.row + self.height)

    def row_sql(self, expr: CellExpr) -> str:
        if self.anchor_row is None or expr.row_abs:
            return str(expr.row)
        delta = expr.row - self.anchor_row
        return "src._row" if delta == 0 else f"src._row {'+' if delta > 0 else '-'} {abs(delta)}"


NodeRenderer = Callable[["SqlRenderer", Any, Scope], str]
node_renderers: Registry[NodeRenderer] = Registry("expression renderers")


class SqlRenderer:
    def __init__(self, ir: WorkbookIR, model_of: Mapping[str, str]) -> None:
        self.ir = ir
        self.model_of = model_of
        self.owner = owners(ir)

    def scalar(self, expr: Expr) -> str:
        return self.render(expr, Scope())

    def render(self, expr: Expr, scope: Scope) -> str:
        return node_renderers.get(expr.type)(self, expr, scope)

    def owner_of(self, ref_: CellRef) -> Node:
        try:
            return self.owner[ref_]
        except KeyError:
            raise ValueError(
                f"{ref_.sheet}!R{ref_.row}C{ref_.col} is read but no IR node owns it"
            ) from None

    def pieces(self, rng: CellRange) -> list[str]:
        """Long-form selects (_r, _c, _v) that together cover every cell of ``rng`` once.

        An input gives one select per column it shares with ``rng``. Step cells give one select
        per model: the model's rows inside ``rng`` are exactly the range's cells it owns.
        """
        out: list[str] = []
        covered = 0
        models: set[str] = set()
        nodes = {n.id: n for n in (self.owner_of(c) for c in rng.cells())}
        for nid in sorted(nodes):
            for own in nodes[nid].ranges():
                part = intersect(own, rng)
                if part is None:
                    continue
                covered += len(part.cells())
                node = nodes[nid]
                if isinstance(node, Input):
                    out.extend(self._piece(node, own, part))
                else:
                    models.add(self.model_of[nid])
        if covered != len(rng.cells()):
            raise ValueError(f"range on {rng.sheet} is not covered exactly once")
        out.extend(self._model_piece(m, rng) for m in sorted(models))
        return out

    def _model_piece(self, model: str, rng: CellRange) -> str:
        return (
            f"SELECT m.{ROW} AS _r, m.{COL} AS _c, m.{VALUE} AS _v FROM {ref(model)} AS m "
            f"WHERE m.{SHEET} = {sql_string(rng.sheet)} "
            f"AND m.{ROW} BETWEEN {rng.row} AND {rng.last_row} "
            f"AND m.{COL} BETWEEN {rng.col} AND {rng.last_col}"
        )

    def _piece(self, node: Input, own: CellRange, part: CellRange) -> list[str]:
        model = ref(self.model_of[node.id])
        names = {own.col + i: ident(c.name) for i, c in enumerate(node.columns)}
        return [
            f"SELECT i._row AS _r, {col} AS _c, i.{names[col]} AS _v FROM {model} AS i "
            f"WHERE i._row BETWEEN {part.row} AND {part.last_row}"
            for col in range(part.col, part.last_col + 1)
        ]


@node_renderers.register("cell")
def _cell(r: SqlRenderer, e: CellExpr, scope: Scope) -> str:
    read = {r.owner_of(CellRef(sheet=e.sheet, row=n, col=e.col)).id: n for n in scope.rows(e)}
    if len(read) != 1:
        raise ValueError(f"a relative reference on {e.sheet} crosses nodes {sorted(read)}")
    node = r.owner_of(CellRef(sheet=e.sheet, row=e.row, col=e.col))
    model, row = ref(r.model_of[node.id]), scope.row_sql(e)
    if isinstance(node, Input):
        column = ident(node.columns[e.col - node.ranges()[0].col].name)
        if node.id == scope.over and row == "src._row":
            return f"src.{column}"
        return f"(SELECT ANY_VALUE(i.{column}) FROM {model} AS i WHERE i._row = {row})"
    return (
        f"(SELECT ANY_VALUE(m.{VALUE}) FROM {model} AS m WHERE m.{SHEET} = {sql_string(e.sheet)} "
        f"AND m.{ROW} = {row} AND m.{COL} = {e.col})"
    )


@node_renderers.register("range")
def _range(r: SqlRenderer, e: RangeExpr, scope: Scope) -> str:
    union = " UNION ALL ".join(r.pieces(e.as_range()))
    cells = f"(SELECT ARRAY_AGG(p._v) WITHIN GROUP (ORDER BY p._r, p._c) FROM ({union}) AS p)"
    width = e.as_range().width
    return f"OBJECT_CONSTRUCT('{RANGE_COLUMNS}', {width}, '{RANGE_CELLS}', {cells})"


@node_renderers.register("param")
def _param(r: SqlRenderer, e: Any, scope: Scope) -> str:
    return "{{ bk_param(" + sql_string(e.id) + ") }}"


@node_renderers.register("lit")
def _literal(r: SqlRenderer, e: Any, scope: Scope) -> str:
    return _wire(e.value)


def _arg(r: SqlRenderer, a: Expr, scope: Scope) -> str:
    """An argument as the runtime receives it: a one-cell reference is a one-element array."""
    sql = r.render(a, scope)
    return f"{ARGS}({sql})" if isinstance(a, CellExpr) else sql


def _udf(macro: str, name: str, r: SqlRenderer, args: tuple[Expr, ...], scope: Scope) -> str:
    rendered = ", ".join(_arg(r, a, scope) for a in args)
    return "{{ " + macro + "(" + sql_string(name) + ") }}(" + f"{ARGS}({rendered}))"


def _if(r: SqlRenderer, e: Any, scope: Scope) -> str:
    choose = _udf("bk_fn", e.name, r, (e.args[0], *_marks()), scope)
    false = LiteralExpr(value=CellValue.boolean(False))  # IF's value_if_false when omitted
    when_true, when_false = (_arg(r, a, scope) for a in (*e.args[1:3], false, false)[:2])
    hex_true, hex_false = (sql_string(m.hex()) for m in IF_BRANCHES)
    return (
        f"(SELECT CASE _if:h::VARCHAR WHEN {hex_true} THEN {when_true} "
        f"WHEN {hex_false} THEN {when_false} ELSE _if END FROM (SELECT {choose} AS _if))"
    )


def _marks() -> tuple[LiteralExpr, ...]:
    return tuple(LiteralExpr(value=CellValue.number(m)) for m in IF_BRANCHES)


@node_renderers.register("call")
def _call(r: SqlRenderer, e: Any, scope: Scope) -> str:
    # IF(c, m1, m2) is the choice itself: its branches are literals, so nothing is skipped.
    if e.name == "IF" and len(e.args) >= 2 and tuple(e.args[1:]) != _marks():
        return _if(r, e, scope)
    return _udf("bk_fn", e.name, r, e.args, scope)


@node_renderers.register("op")
def _op(r: SqlRenderer, e: Any, scope: Scope) -> str:
    return _udf("bk_op", e.op.value, r, e.args, scope)
