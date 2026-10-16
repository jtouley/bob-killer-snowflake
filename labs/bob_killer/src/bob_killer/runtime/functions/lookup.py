"""VLOOKUP (support.microsoft.com VLOOKUP page and the lookup examples topic).

Exact match returns the first row whose first-column value equals the lookup value (text with
wildcards, case ignored). Approximate match needs a first column sorted ascending and of the
lookup value's type; it returns the last row whose value is less than or equal to the lookup
value, #N/A below the smallest. An unsorted column, mixed types or a duplicate at the match are
refused: Excel's answer then depends on its search order, which is not documented.
"""

from __future__ import annotations

from bob_killer.registry import excel_function
from bob_killer.runtime import criteria
from bob_killer.runtime.coercion import (
    Arg,
    CellValue,
    ExcelError,
    UnsupportedValue,
    to_logical,
    to_number,
)
from bob_killer.runtime.operators import compare, operand
from bob_killer.runtime.values import shape


def _order(x: CellValue, y: CellValue) -> int:
    order = compare(x, y)
    if isinstance(order, ExcelError):
        raise UnsupportedValue("an error value in the first column")  # pragma: no mutate
    return order


def _exact(key: CellValue, cell: CellValue) -> bool:
    if isinstance(cell, ExcelError):
        raise UnsupportedValue("an error value in the first column")  # pragma: no mutate
    if isinstance(key, str):
        return isinstance(cell, str) and criteria.text_matches(key, cell)
    if isinstance(cell, str) and isinstance(key, float) and criteria.is_number_text(cell):
        raise UnsupportedValue("number text in the first column")  # pragma: no mutate
    return type(cell) is type(key) and _order(cell, key) == 0


def _exact_row(key: CellValue, column: list[CellValue]) -> int | None:
    return next((i for i, cell in enumerate(column) if _exact(key, cell)), None)


def _approximate_row(key: CellValue, column: list[CellValue]) -> int | None:
    if isinstance(key, str) and criteria.has_wildcard(key):
        raise UnsupportedValue("wildcards in an approximate match")  # pragma: no mutate
    if any(type(cell) is not type(key) for cell in column):
        raise UnsupportedValue("a first column of mixed types")  # pragma: no mutate
    if any(_order(a, b) > 0 for a, b in zip(column, column[1:], strict=False)):
        raise UnsupportedValue("a first column not sorted ascending")  # pragma: no mutate
    found = None
    for i, cell in enumerate(column):
        if _order(cell, key) > 0:
            break
        found = i
    if found is not None and sum(_order(c, column[found]) == 0 for c in column) > 1:
        raise UnsupportedValue("a duplicate first-column value at the match")  # pragma: no mutate
    return found


@excel_function("VLOOKUP")
def vlookup(
    lookup_value: Arg, table_array: Arg, col_index_num: Arg, range_lookup: Arg = True
) -> CellValue:
    key = operand(lookup_value)
    if isinstance(key, ExcelError):
        return key
    if key is None or key == "":
        raise UnsupportedValue("a blank lookup value")  # pragma: no mutate
    if not isinstance(table_array, tuple):
        raise UnsupportedValue("a typed value as table_array")  # pragma: no mutate
    rows, columns = shape(table_array)
    col = to_number(operand(col_index_num))
    if isinstance(col, ExcelError):
        return col
    if not col.is_integer():
        raise UnsupportedValue("a fractional col_index_num")  # pragma: no mutate
    if col < 1:
        return ExcelError.VALUE
    if col > columns:
        return ExcelError.REF
    approximate = to_logical(operand(range_lookup))
    if isinstance(approximate, ExcelError):
        return approximate
    column = [table_array[r * columns] for r in range(rows)]
    row = _approximate_row(key, column) if approximate else _exact_row(key, column)
    if row is None:
        return ExcelError.NA
    return table_array[row * columns + int(col) - 1]
