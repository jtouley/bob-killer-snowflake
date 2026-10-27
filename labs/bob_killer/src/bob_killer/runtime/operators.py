"""Excel operators: ``+ - * / ^ & = <> < > <= >=``, unary minus and percent.

Each is a registered runtime function named ``OP_<contracts.ir.Operator value>`` (SPEC-compiler-dbt
§4.4), so the dbt generator's ``bk_op('<value>')`` resolves to the ``BK_OP_<value>`` UDF built
from here. ``SYMBOLS`` maps an Excel operator symbol to that name for evaluators of formula ASTs.

Sources: support.microsoft.com "Calculation operators and precedence" and "Using calculation
operators"; learn.microsoft.com "Excel worksheet and expression evaluation" (#VALUE!, #DIV/0!,
subnormal numbers become +0) and "Floating-point arithmetic may give inaccurate results" (near-zero
compensation of + and -); the MATCH page for the order across types (numbers, text A-Z, FALSE,
TRUE). The first error operand wins, as in the aggregate functions.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any

from bob_killer.registry import excel_function
from bob_killer.runtime.coercion import (
    Arg,
    CellValue,
    ExcelError,
    UnsupportedValue,
    to_number,
    to_text,
)
from bob_killer.runtime.rounding import fifteen_digits
from bob_killer.runtime.values import Area

SYMBOLS: dict[str, str] = {
    "+": "ADD",
    "-": "SUB",
    "*": "MUL",
    "/": "DIV",
    "^": "POW",
    "&": "CONCAT",
    "=": "EQ",
    "<>": "NE",
    "<": "LT",
    ">": "GT",
    "<=": "LE",
    ">=": "GE",
}
UNARY_SYMBOLS: dict[str, str] = {"-": "NEG", "%": "PERCENT"}

_SMALLEST_NORMAL = 2.2250738585072014e-308
# A + or - result this close to zero, relative to its operands, may be compensated to 0 by Excel;
# the threshold is not documented, so a nonzero result inside this band is refused.
_NEAR_ZERO = 2.0**-44
_MAX_TEXT = 32_767  # characters in one cell (Excel specifications and limits)
_ASCII_ORDERED = re.compile(r"[0-9A-Za-z]")

Number = float | ExcelError


def operand(value: Arg) -> CellValue:
    """One operand: a single-cell reference is its value; a larger one is not supported here."""
    if isinstance(value, tuple):
        if len(value) != 1:
            raise UnsupportedValue("a multi-cell reference as an operand")  # pragma: no mutate
        return value[0]
    return value


def _elementwise[F: Callable[..., Any]](op: F) -> F:
    """The operator on arrays: element by element over areas of one shape, a single value
    applied to every element (SUMPRODUCT page: "replace the commas separating the array
    arguments with the arithmetic operators"; arrays "must have the same dimensions").

    Only a shaped area (an ``Area``) is an array here; other multi-cell references stay refused.
    """

    def apply(*args: Arg) -> Any:
        areas = [a for a in args if isinstance(a, Area) and len(a) > 1]
        if not areas:
            return op(*args)
        shapes = {(a.rows, a.columns) for a in areas}
        if len(shapes) != 1:
            raise UnsupportedValue("arrays of different dimensions")  # pragma: no mutate
        first = areas[0]
        cells = [
            op(*(a[i] if isinstance(a, Area) and len(a) > 1 else operand(a) for a in args))
            for i in range(len(first))
        ]
        return Area(cells, columns=first.columns)

    return apply  # type: ignore[return-value]


def number_result(x: float) -> float | ExcelError:
    """A computed double as Excel keeps it: subnormals and -0 become +0; overflow is refused."""
    if not math.isfinite(x):
        raise UnsupportedValue("a result beyond the largest double")  # pragma: no mutate
    if abs(x) < _SMALLEST_NORMAL:
        return 0.0
    return x


def _numbers(a: Arg, b: Arg) -> tuple[float, float] | ExcelError:
    x = to_number(operand(a))
    if isinstance(x, ExcelError):
        return x
    y = to_number(operand(b))
    if isinstance(y, ExcelError):
        return y
    return x, y


def _arithmetic(rule: Callable[[float, float], float | ExcelError]) -> Callable[[Arg, Arg], Number]:
    def apply(a: Arg, b: Arg) -> Number:
        pair = _numbers(a, b)
        if isinstance(pair, ExcelError):
            return pair
        result = rule(*pair)
        return result if isinstance(result, ExcelError) else number_result(result)

    return apply


def _compensated(total: float, x: float, y: float) -> float:
    if total != 0 and abs(total) < max(abs(x), abs(y)) * _NEAR_ZERO:
        raise UnsupportedValue("a + or - result very close to zero")  # pragma: no mutate
    return total


def _divide(x: float, y: float) -> float | ExcelError:
    return ExcelError.DIV0 if y == 0 else x / y


def _power(x: float, y: float) -> float:
    if x == 0 and y <= 0:
        raise UnsupportedValue("0 to a power of 0 or less")  # pragma: no mutate
    if x < 0 and not y.is_integer():
        raise UnsupportedValue("a negative base to a fractional power")  # pragma: no mutate
    try:
        return math.pow(x, y)
    except OverflowError:
        return math.inf


add = excel_function("OP_ADD")(_elementwise(_arithmetic(lambda x, y: _compensated(x + y, x, y))))
sub = excel_function("OP_SUB")(_elementwise(_arithmetic(lambda x, y: _compensated(x - y, x, y))))
mul = excel_function("OP_MUL")(_elementwise(_arithmetic(float.__mul__)))
div = excel_function("OP_DIV")(_elementwise(_arithmetic(_divide)))
pow_ = excel_function("OP_POW")(_elementwise(_arithmetic(_power)))


@excel_function("OP_NEG")
@_elementwise
def neg(a: Arg) -> Number:
    x = to_number(operand(a))
    return x if isinstance(x, ExcelError) else number_result(-x)


@excel_function("OP_PERCENT")
@_elementwise
def percent(a: Arg) -> Number:
    x = to_number(operand(a))
    return x if isinstance(x, ExcelError) else number_result(x / 100)


@excel_function("OP_CONCAT")
@_elementwise
def concat(a: Arg, b: Arg) -> str | ExcelError:
    left = to_text(operand(a))
    if isinstance(left, ExcelError):
        return left
    right = to_text(operand(b))
    if isinstance(right, ExcelError):
        return right
    if len(left) + len(right) > _MAX_TEXT:
        raise UnsupportedValue("text beyond 32 767 characters")  # pragma: no mutate
    return left + right


# --- comparison -----------------------------------------------------------------------------------

_TYPE_RANK = {float: 0, str: 1, bool: 2}  # MATCH: ...-1, 0, 1, ..., A-Z, FALSE, TRUE


def _sign(x: float | str | bool, y: float | str | bool) -> int:
    return (x > y) - (x < y)  # type: ignore[operator]


def _compare_numbers(x: float, y: float) -> int:
    if x != y and fifteen_digits(x) == fifteen_digits(y):
        raise UnsupportedValue("doubles equal at 15 digits")  # pragma: no mutate
    return _sign(x, y)


def _compare_text(x: str, y: str) -> int:
    if x == y:
        return 0
    if not (x.isascii() and y.isascii()):
        raise UnsupportedValue("comparison of non-ASCII text")  # pragma: no mutate
    a, b = x.lower(), y.lower()
    for ca, cb in zip(a, b, strict=False):
        if ca != cb:
            if not (_ASCII_ORDERED.match(ca) and _ASCII_ORDERED.match(cb)):
                raise UnsupportedValue("text order beyond letters and digits")  # pragma: no mutate
            return _sign(ca, cb)
    return _sign(len(a), len(b))


def _blank_as(other: float | str | bool | None) -> float | str:
    """A blank compared: 0 against a number or a blank, "" against text."""
    if isinstance(other, bool):
        raise UnsupportedValue("a blank compared with a logical")  # pragma: no mutate
    return "" if isinstance(other, str) else 0.0


def compare(a: Arg, b: Arg) -> int | ExcelError:
    """-1, 0 or 1 as Excel orders ``a`` against ``b``; an error operand is returned (left first)."""
    x, y = operand(a), operand(b)
    if isinstance(x, ExcelError):
        return x
    if isinstance(y, ExcelError):
        return y
    if x is None:
        x = _blank_as(y)
    if y is None:
        y = _blank_as(x)
    rank_x, rank_y = _TYPE_RANK[type(x)], _TYPE_RANK[type(y)]
    if rank_x != rank_y:
        return _sign(rank_x, rank_y)
    if isinstance(x, float) and isinstance(y, float):
        return _compare_numbers(x, y)
    if isinstance(x, str) and isinstance(y, str):
        return _compare_text(x, y)
    return _sign(x, y)


def _comparison(test: Callable[[int], bool]) -> Callable[[Arg, Arg], bool | ExcelError]:
    def apply(a: Arg, b: Arg) -> bool | ExcelError:
        order = compare(a, b)
        return order if isinstance(order, ExcelError) else test(order)

    return apply


eq = excel_function("OP_EQ")(_elementwise(_comparison(lambda c: c == 0)))
ne = excel_function("OP_NE")(_elementwise(_comparison(lambda c: c != 0)))
lt = excel_function("OP_LT")(_elementwise(_comparison(lambda c: c < 0)))
gt = excel_function("OP_GT")(_elementwise(_comparison(lambda c: c > 0)))
le = excel_function("OP_LE")(_elementwise(_comparison(lambda c: c <= 0)))
ge = excel_function("OP_GE")(_elementwise(_comparison(lambda c: c >= 0)))
