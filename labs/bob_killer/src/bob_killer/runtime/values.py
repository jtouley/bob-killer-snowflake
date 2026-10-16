"""The runtime's cell value: blank, number, text, logical or error. Pure Python, no dependencies.

A ``CellValue`` is ``None`` (an empty cell), a ``float`` (Excel stores every number as a double),
a ``str`` (text, ``""`` included), a ``bool`` (a logical) or an ``ExcelError``. A ``Range`` is a
reference or array argument: its cells in order. A bare ``CellValue`` argument is a value typed
directly into a function's argument list; Excel treats the two differently.
"""

from __future__ import annotations

from enum import Enum


class ExcelError(Enum):
    """The error values IFERROR evaluates (support.microsoft.com IFERROR function)."""

    NULL = "#NULL!"
    DIV0 = "#DIV/0!"
    VALUE = "#VALUE!"
    REF = "#REF!"
    NAME = "#NAME?"
    NUM = "#NUM!"
    NA = "#N/A"


CellValue = float | str | bool | ExcelError | None
Range = tuple[CellValue, ...]
Arg = CellValue | Range


class UnsupportedValue(NotImplementedError):
    """An input whose Excel result is not yet established by the oracle: refused, never guessed."""
