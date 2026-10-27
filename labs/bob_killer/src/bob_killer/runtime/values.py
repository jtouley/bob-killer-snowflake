"""The runtime's cell value: blank, number, text, logical or error. Pure Python, no dependencies.

A ``CellValue`` is ``None`` (an empty cell), a ``float`` (Excel stores every number as a double),
a ``str`` (text, ``""`` included), a ``bool`` (a logical) or an ``ExcelError``. A ``Range`` is a
reference or array argument: its cells in order. An ``Area`` is a ``Range`` that also knows its
column count (cells row by row), for functions that read the shape. A bare ``CellValue``
argument is a value typed directly into a function's argument list; Excel treats the two
differently.
"""

from __future__ import annotations

from collections.abc import Iterable
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


class Area(tuple[CellValue, ...]):
    """A rectangular reference or array: its cells row by row, and its column count."""

    columns: int

    def __new__(cls, cells: Iterable[CellValue], columns: int) -> Area:
        area = super().__new__(cls, cells)
        if columns < 1 or len(area) % columns:
            raise ValueError(f"{len(area)} cells do not fill rows of {columns} columns")
        area.columns = columns
        return area

    @property
    def rows(self) -> int:
        return len(self) // self.columns


def shape(cells: Range) -> tuple[int, int]:
    """(rows, columns) of a reference; a range that does not carry its shape is refused."""
    if isinstance(cells, Area):
        return cells.rows, cells.columns
    if len(cells) == 1:
        return 1, 1
    raise UnsupportedValue("a range without its shape")  # pragma: no mutate
