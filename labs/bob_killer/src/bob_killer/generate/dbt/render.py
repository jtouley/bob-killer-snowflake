"""Expression renderer: IR expression AST -> Snowflake SQL with dbt macro calls (§4.1, D20, D21).

Only the SQL-exact set renders as plain SQL: cell references, parameter references and literals.
Every function call renders as ``{{ bk_fn('<NAME>') }}(<args>)`` and every operator as
``{{ bk_op('<OP>') }}(<args>)``; each macro emits a qualified ``BK_*`` UDF name built from
``runtime/``. Ranges reach a UDF as an ordered ``ARRAY_AGG`` of wire objects (F23).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from bob_killer.contracts.ir import (
    CellExpr,
    CellRange,
    CellRef,
    Expr,
    Input,
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
        """Long-form selects (_r, _c, _v) that together cover every cell of ``rng`` once."""
        out: list[str] = []
        covered = 0
        nodes = {n.id: n for n in (self.owner_of(c) for c in rng.cells())}
        for nid in sorted(nodes):
            for own in nodes[nid].ranges():
                part = intersect(own, rng)
                if part is not None:
                    covered += len(part.cells())
                    out.extend(self._piece(nodes[nid], own, part))
        if covered != len(rng.cells()):
            raise ValueError(f"range on {rng.sheet} is not covered exactly once")
        return out

    def _piece(self, node: Node, own: CellRange, part: CellRange) -> list[str]:
        model = ref(self.model_of[node.id])
        if isinstance(node, Input):
            names = {own.col + i: ident(c.name) for i, c in enumerate(node.columns)}
            return [
                f"SELECT i._row AS _r, {col} AS _c, i.{names[col]} AS _v FROM {model} AS i "
                f"WHERE i._row BETWEEN {part.row} AND {part.last_row}"
                for col in range(part.col, part.last_col + 1)
            ]
        return [
            f"SELECT m.{ROW} AS _r, m.{COL} AS _c, m.{VALUE} AS _v FROM {model} AS m "
            f"WHERE m.{SHEET} = {sql_string(part.sheet)} "
            f"AND m.{ROW} BETWEEN {part.row} AND {part.last_row} "
            f"AND m.{COL} BETWEEN {part.col} AND {part.last_col}"
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
    return f"(SELECT ARRAY_AGG(p._v) WITHIN GROUP (ORDER BY p._r, p._c) FROM ({union}) AS p)"


@node_renderers.register("param")
def _param(r: SqlRenderer, e: Any, scope: Scope) -> str:
    return "{{ bk_param(" + sql_string(e.id) + ") }}"


@node_renderers.register("lit")
def _literal(r: SqlRenderer, e: Any, scope: Scope) -> str:
    return f"PARSE_JSON({sql_string(e.value.wire())})"


def _udf(macro: str, name: str, r: SqlRenderer, args: tuple[Expr, ...], scope: Scope) -> str:
    rendered = ", ".join(r.render(a, scope) for a in args)
    return "{{ " + macro + "(" + sql_string(name) + ") }}(" + rendered + ")"


@node_renderers.register("call")
def _call(r: SqlRenderer, e: Any, scope: Scope) -> str:
    return _udf("bk_fn", e.name, r, e.args, scope)


@node_renderers.register("op")
def _op(r: SqlRenderer, e: Any, scope: Scope) -> str:
    return _udf("bk_op", e.op.value, r, e.args, scope)
