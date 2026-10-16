"""Pre-order walks over the AST: references and function names."""

from __future__ import annotations

from collections.abc import Iterator

from bob_killer.contracts.graph import (
    ArrayConst,
    BinaryOp,
    Call,
    CellRef,
    Expr,
    NameRef,
    RangeRef,
    Reference,
    UnaryOp,
)


def _children(expr: Expr) -> tuple[Expr, ...]:
    match expr:
        case UnaryOp(operand=operand):
            return (operand,)
        case BinaryOp(left=left, right=right):
            return (left, right)
        case Call(args=args):
            return args
        case ArrayConst(rows=rows):
            return tuple(e for row in rows for e in row)
    return ()


def walk(expr: Expr) -> Iterator[Expr]:
    stack = [expr]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(_children(node)))


def references(expr: Expr) -> tuple[Reference, ...]:
    return tuple(n for n in walk(expr) if isinstance(n, CellRef | RangeRef | NameRef))


def function_names(expr: Expr) -> tuple[str, ...]:
    """Called function names in first-use order, each once."""
    return tuple(dict.fromkeys(n.name for n in walk(expr) if isinstance(n, Call)))
