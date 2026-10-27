"""AST to canonical formula text; ``parse(render(ast)) == ast`` holds for every AST."""

from __future__ import annotations

from bob_killer.contracts.graph import (
    Anchor,
    ArrayConst,
    BinaryOp,
    Boolean,
    Call,
    CellRef,
    ErrorLiteral,
    Expr,
    Missing,
    NameRef,
    Number,
    RangeRef,
    Text,
    UnaryOp,
)
from bob_killer.graph import grammar
from bob_killer.graph.refs import column_letters


def _level(expr: Expr) -> int:
    if isinstance(expr, BinaryOp):
        return grammar.BINARY[expr.op]
    if isinstance(expr, UnaryOp):
        return grammar.PERCENT if expr.op == "%" else grammar.PREFIX
    return grammar.ATOM


def _wrapped(expr: Expr, minimum: int) -> str:
    text = _render(expr)
    return text if _level(expr) >= minimum else f"({text})"


def _sheet(sheet: str | None) -> str:
    return "" if sheet is None else "'" + sheet.replace("'", "''") + "'!"


def _anchor(a: Anchor) -> str:
    column = (
        "" if a.column is None else ("$" if a.column_absolute else "") + column_letters(a.column)
    )
    row = "" if a.row is None else ("$" if a.row_absolute else "") + str(a.row)
    return column + row


def _render(expr: Expr) -> str:
    match expr:
        case Number(value=value):
            return repr(value).upper()
        case Text(value=value):
            return '"' + value.replace('"', '""') + '"'
        case Boolean(value=value):
            return "TRUE" if value else "FALSE"
        case ErrorLiteral(value=value):
            return value.value
        case Missing():
            return ""
        case CellRef(sheet=sheet, at=at):
            return _sheet(sheet) + _anchor(at)
        case RangeRef(sheet=sheet, start=start, end=end):
            return f"{_sheet(sheet)}{_anchor(start)}:{_anchor(end)}"
        case NameRef(sheet=sheet, name=name):
            return _sheet(sheet) + name
        case ArrayConst(rows=rows):
            return "{" + ";".join(",".join(_render(e) for e in row) for row in rows) + "}"
        case UnaryOp(op="%", operand=operand):
            return _wrapped(operand, grammar.PERCENT) + "%"
        case UnaryOp(op=op, operand=operand):
            return op + _wrapped(operand, grammar.PREFIX)
        case BinaryOp(op=op, left=left, right=right):
            level = grammar.BINARY[op]
            text = _wrapped(left, level) + op + _wrapped(right, level + 1)
            return f"({text})" if op == "," else text  # a bare union would split call arguments
        case Call(name=name, args=args):
            return name + "(" + ",".join(_render(a) for a in args) + ")"
    raise TypeError(f"cannot render {expr!r}")


def render(expr: Expr) -> str:
    return "=" + _render(expr)
