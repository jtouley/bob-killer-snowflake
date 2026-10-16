"""SUM, PRODUCT, MIN, MAX, AVERAGE, COUNT, COUNTA.

Inside a reference or array only numbers count (COUNTA: anything non-empty); values typed directly
into the argument list are converted like any formula operand. The first error met in argument
order is returned. Sums and products accumulate left to right in IEEE double; that this is Excel's
order is an open fact for the oracle (SPEC decision 1).
"""

from __future__ import annotations

from collections.abc import Callable

from bob_killer.registry import excel_function
from bob_killer.runtime.coercion import Arg, CellValue, ExcelError, UnsupportedValue, to_number

TypedRule = Callable[[CellValue], float | ExcelError]


def _typed(value: CellValue) -> float | ExcelError:
    if value is None:
        raise UnsupportedValue("an omitted argument")
    return to_number(value)


def _typed_numbers_only(value: CellValue) -> float | ExcelError:
    # The AVERAGE page says typed logicals and number text are "not counted"; unconfirmed.
    if isinstance(value, bool | str):
        raise UnsupportedValue(f"typed {value!r} in AVERAGE")
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
            raise UnsupportedValue("an omitted argument")
        else:
            n += 1
    return float(n)
