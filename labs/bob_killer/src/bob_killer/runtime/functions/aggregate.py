"""SUM, PRODUCT, MIN, MAX, AVERAGE, COUNT, COUNTA, SUMIF, SUMPRODUCT.

Inside a reference or array only numbers count (COUNTA: anything non-empty); values typed directly
into the argument list are converted like any formula operand. The first error met in argument
order is returned. Sums and products accumulate left to right in IEEE double; that this is Excel's
order is an open fact for the oracle (SPEC decision 1). SUMIF's criteria are runtime/criteria.py;
SUMPRODUCT multiplies equal-shaped ranges entry by entry (non-numbers count as 0) and sums.
"""

from __future__ import annotations

from collections.abc import Callable

from bob_killer.registry import excel_function
from bob_killer.runtime import criteria
from bob_killer.runtime.coercion import (
    Arg,
    CellValue,
    ExcelError,
    Range,
    UnsupportedValue,
    to_number,
)
from bob_killer.runtime.operators import number_result, operand
from bob_killer.runtime.values import shape

TypedRule = Callable[[CellValue], float | ExcelError]


def _typed(value: CellValue) -> float | ExcelError:
    if value is None:
        raise UnsupportedValue("an omitted argument")  # pragma: no mutate
    return to_number(value)


def _typed_numbers_only(value: CellValue) -> float | ExcelError:
    # The AVERAGE page says typed logicals and number text are "not counted"; unconfirmed.
    if isinstance(value, bool | str):
        raise UnsupportedValue(f"typed {value!r} in AVERAGE")  # pragma: no mutate
    return _typed(value)


def _numbers(args: tuple[Arg, ...], typed: TypedRule = _typed) -> list[float] | ExcelError:
    out: list[float] = []
    for arg in args:
        cells = arg if isinstance(arg, tuple) else (typed(arg),)
        for cell in cells:
            if isinstance(cell, ExcelError):
                return cell
            if isinstance(cell, float):
                out.append(cell)
    return out


def _accumulate(numbers: list[float], start: float, op: Callable[[float, float], float]) -> float:
    total = start
    for x in numbers:
        total = op(total, x)
    return total


@excel_function("SUM")
def sum_(*args: Arg) -> float | ExcelError:
    numbers = _numbers(args)
    if isinstance(numbers, ExcelError):
        return numbers
    return _accumulate(numbers, 0.0, float.__add__)


@excel_function("PRODUCT")
def product(*args: Arg) -> float | ExcelError:
    numbers = _numbers(args)
    if isinstance(numbers, ExcelError):
        return numbers
    if not numbers:
        return 0.0  # open fact: Excel's PRODUCT of no numbers
    return _accumulate(numbers, 1.0, float.__mul__)


@excel_function("MIN")
def min_(*args: Arg) -> float | ExcelError:
    numbers = _numbers(args)
    if isinstance(numbers, ExcelError):
        return numbers
    return min(numbers) if numbers else 0.0


@excel_function("MAX")
def max_(*args: Arg) -> float | ExcelError:
    numbers = _numbers(args)
    if isinstance(numbers, ExcelError):
        return numbers
    return max(numbers) if numbers else 0.0


@excel_function("AVERAGE")
def average(*args: Arg) -> float | ExcelError:
    numbers = _numbers(args, _typed_numbers_only)
    if isinstance(numbers, ExcelError):
        return numbers
    if not numbers:
        return ExcelError.DIV0
    return _accumulate(numbers, 0.0, float.__add__) / len(numbers)


@excel_function("COUNT")
def count(*args: Arg) -> float:
    n = 0
    for arg in args:
        cells = arg if isinstance(arg, tuple) else (_typed(arg),)
        n += sum(isinstance(cell, float) for cell in cells)
    return float(n)


@excel_function("COUNTA")
def counta(*args: Arg) -> float:
    n = 0
    for arg in args:
        if isinstance(arg, tuple):
            n += sum(cell is not None for cell in arg)
        elif arg is None:
            raise UnsupportedValue("an omitted argument")  # pragma: no mutate
        else:
            n += 1
    return float(n)


def _reference(arg: Arg, what: str) -> Range:
    if not isinstance(arg, tuple):
        raise UnsupportedValue(f"a typed value as {what}")  # pragma: no mutate
    return arg


@excel_function("SUMIF")
def sumif(range_: Arg, criteria_: Arg, sum_range: Arg = None) -> float | ExcelError:
    cells = _reference(range_, "SUMIF range")
    addends = cells if sum_range is None else _reference(sum_range, "SUMIF sum_range")
    if len(addends) != len(cells):
        raise UnsupportedValue("a sum_range of another size")  # pragma: no mutate
    match = criteria.criteria(operand(criteria_))
    numbers: list[float] = []
    for cell, addend in zip(cells, addends, strict=True):
        if not match(cell):
            continue
        if isinstance(addend, ExcelError):
            raise UnsupportedValue("an error value among the cells to add")  # pragma: no mutate
        if isinstance(addend, float):
            numbers.append(addend)
    return number_result(_accumulate(numbers, 0.0, float.__add__))


def _entry(cell: CellValue) -> float:
    if isinstance(cell, ExcelError):
        raise UnsupportedValue("an error value in a SUMPRODUCT array")  # pragma: no mutate
    if isinstance(cell, str) and criteria.is_number_text(cell):
        raise UnsupportedValue("number text in a SUMPRODUCT array")  # pragma: no mutate
    return cell if isinstance(cell, float) else 0.0


@excel_function("SUMPRODUCT")
def sumproduct(*arrays: Arg) -> float | ExcelError:
    ranges = [_reference(a, "a SUMPRODUCT array") for a in arrays]
    if not ranges:
        raise UnsupportedValue("SUMPRODUCT without arrays")  # pragma: no mutate
    if len({shape(r) for r in ranges}) != 1:
        return ExcelError.VALUE
    products = [
        _accumulate([_entry(c) for c in row[1:]], _entry(row[0]), float.__mul__)
        for row in zip(*ranges, strict=True)
    ]
    return number_result(_accumulate(products, 0.0, float.__add__))
