"""VLOOKUP, MATCH, INDEX and XLOOKUP (support.microsoft.com function pages, the lookup examples
topic and "How to correct a #N/A error").

Exact match returns the first row whose first-column value equals the lookup value (text with
wildcards, case ignored). A number never matches text, number text included: the #N/A page names
"you try to have VLOOKUP reference a number, but the source data is stored as text" as a cause
of #N/A. A blank lookup value is answered only when every reading of it (as 0, as empty text,
or as matching no cell) gives #N/A, that is when the column holds no 0, no empty text and no
blank cell; otherwise it is refused. Approximate match needs a first column sorted ascending and of the
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
    return type(cell) is type(key) and _order(cell, key) == 0


def _check_blank_key(column: list[CellValue]) -> None:
    """A blank lookup value matches no row when no reading of the blank can match; else refused."""
    if any(cell is None or cell == "" or cell == 0.0 for cell in column):
        raise UnsupportedValue("a blank lookup value")  # pragma: no mutate
    if any(isinstance(cell, ExcelError) for cell in column):
        raise UnsupportedValue("an error value in the first column")  # pragma: no mutate


def _exact_row(key: CellValue, column: list[CellValue]) -> int | None:
    if key is None:
        _check_blank_key(column)
        return None
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
    if key == "":
        raise UnsupportedValue("an empty-text lookup value")  # pragma: no mutate
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
    if approximate and key is None:
        raise UnsupportedValue("a blank lookup value")  # pragma: no mutate
    row = _approximate_row(key, column) if approximate else _exact_row(key, column)
    if row is None:
        return ExcelError.NA
    return table_array[row * columns + int(col) - 1]


def _vector(array: Arg, what: str) -> list[CellValue]:
    """The cells of a one-row or one-column reference."""
    if not isinstance(array, tuple):
        raise UnsupportedValue(f"a typed value as {what}")  # pragma: no mutate
    rows, columns = shape(array)
    if rows != 1 and columns != 1:
        raise UnsupportedValue(f"a {what} of more than one row and column")  # pragma: no mutate
    return list(array)


def _key(lookup_value: Arg) -> CellValue:
    key = operand(lookup_value)
    if key == "":
        raise UnsupportedValue("an empty-text lookup value")  # pragma: no mutate
    if isinstance(key, str) and criteria.has_wildcard(key):
        raise UnsupportedValue("wildcards in a lookup value")  # pragma: no mutate
    return key


def _case_exact_row(key: CellValue, cells: list[CellValue]) -> int | None:
    """The first match, when matching with and without case gives the same row (XLOOKUP: the
    page does not say whether case is ignored)."""
    row = _exact_row(key, cells)
    if row is not None and isinstance(key, str) and cells[row] != key:
        raise UnsupportedValue("a match that differs only in case")  # pragma: no mutate
    return row


@excel_function("MATCH")
def match(lookup_value: Arg, lookup_array: Arg, match_type: Arg = 1.0) -> float | ExcelError:
    """match_type 0: "the first value that is exactly equal to lookup_value" (MATCH page)."""
    key = _key(lookup_value)
    if isinstance(key, ExcelError):
        return key
    kind = to_number(operand(match_type))
    if isinstance(kind, ExcelError):
        return kind
    if kind != 0:
        raise UnsupportedValue("an approximate MATCH")  # pragma: no mutate
    row = _exact_row(key, _vector(lookup_array, "lookup_array"))  # "does not distinguish" case
    return ExcelError.NA if row is None else float(row + 1)


def _position(value: Arg) -> int | ExcelError:
    number = to_number(operand(value))
    if isinstance(number, ExcelError):
        return number
    if not number.is_integer() or number < 1:
        raise UnsupportedValue("an INDEX position other than 1, 2, ...")  # pragma: no mutate
    return int(number)


@excel_function("INDEX")
def index(array: Arg, row_num: Arg, column_num: Arg = None) -> CellValue:
    """The value at row_num, column_num of array; #REF! outside it (INDEX page)."""
    if not isinstance(array, tuple):
        raise UnsupportedValue("a typed value as array")  # pragma: no mutate
    rows, columns = shape(array)
    row = _position(row_num)
    if isinstance(row, ExcelError):
        return row
    if column_num is None:
        if columns != 1:
            raise UnsupportedValue(
                "INDEX without column_num on several columns"
            )  # pragma: no mutate
        col: int | ExcelError = 1
    else:
        col = _position(column_num)
    if isinstance(col, ExcelError):
        return col
    outside = (row > rows, col > columns)
    if all(outside):
        return ExcelError.REF  # "INDEX returns a #REF! error"
    if any(outside):
        raise UnsupportedValue("only one INDEX position outside the array")  # pragma: no mutate
    return array[(row - 1) * columns + col - 1]


@excel_function("XLOOKUP")
def xlookup(
    lookup_value: Arg,
    lookup_array: Arg,
    return_array: Arg,
    if_not_found: Arg = None,
    match_mode: Arg = 0.0,
    search_mode: Arg = 1.0,
) -> Arg:
    """match_mode 0 (exact, the default) and search_mode 1 (first to last, the default) only.

    No match gives if_not_found, or #N/A when it is missing (XLOOKUP page). return_array must be
    one row or column of lookup_array's length; anything else is refused.
    """
    key = _key(lookup_value)
    if isinstance(key, ExcelError):
        return key
    for value, default in ((match_mode, 0.0), (search_mode, 1.0)):
        mode = to_number(operand(value))
        if isinstance(mode, ExcelError):
            return mode
        if mode != default:
            raise UnsupportedValue("an XLOOKUP mode other than the default")  # pragma: no mutate
    keys = _vector(lookup_array, "lookup_array")
    values = _vector(return_array, "return_array")
    if len(values) != len(keys):
        raise UnsupportedValue("return_array of another size")  # pragma: no mutate
    row = _case_exact_row(key, keys)
    if row is None:
        return ExcelError.NA if if_not_found is None else if_not_found
    return values[row]
