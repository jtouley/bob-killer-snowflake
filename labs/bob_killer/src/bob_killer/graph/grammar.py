"""Excel operator precedence, shared by the parser and the renderer (higher binds tighter).

Excel's order: reference operators (``:``, space, ``,``), negation, percent, ``^``, ``*`` and
``/``, ``+`` and ``-``, ``&``, then comparisons. Every binary operator is left-associative,
so ``2^3^2`` is ``(2^3)^2`` and ``-2^2`` is ``(-2)^2``.
"""

from __future__ import annotations

from typing import Final

ATOM: Final = 10
PREFIX: Final = 6
PERCENT: Final = 5

REFERENCE_OPERATORS: Final = {":": 9, " ": 8, ",": 7}
VALUE_OPERATORS: Final = {
    "^": 4,
    "*": 3,
    "/": 3,
    "+": 2,
    "-": 2,
    "&": 1,
    "=": 0,
    "<>": 0,
    "<": 0,
    "<=": 0,
    ">": 0,
    ">=": 0,
}
BINARY: Final = {**REFERENCE_OPERATORS, **VALUE_OPERATORS}
STORAGE_PREFIXES: Final = ("_XLFN.", "_XLWS.")
