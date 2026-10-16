"""IF, AND, OR, NOT, IFERROR.

Arguments arrive evaluated, so IF and IFERROR return the chosen value as given; an error in the
branch not chosen never surfaces.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from bob_killer.registry import excel_function
from bob_killer.runtime.coercion import Arg, ExcelError, UnsupportedValue, to_logical


def _logicals(args: tuple[Arg, ...]) -> list[bool] | ExcelError:
    out: list[bool] = []
    for arg in args:
        if arg is None:
            raise UnsupportedValue("an omitted argument")
        cells = arg if isinstance(arg, tuple) else (to_logical(arg),)
        for cell in cells:
            if isinstance(cell, ExcelError):
                return cell
            if isinstance(cell, float):
                raise UnsupportedValue("a number inside a reference given to AND or OR")
            if isinstance(cell, bool):
                out.append(cell)
    return out or ExcelError.VALUE


def _combine(args: tuple[Arg, ...], how: Callable[[Iterable[bool]], bool]) -> bool | ExcelError:
    logicals = _logicals(args)
    return logicals if isinstance(logicals, ExcelError) else how(logicals)


@excel_function("IF")
def if_(logical_test: Arg, value_if_true: Arg, value_if_false: Arg = False) -> Arg:
    test = to_logical(logical_test)
    if isinstance(test, ExcelError):
        return test
    return value_if_true if test else value_if_false


@excel_function("AND")
def and_(*args: Arg) -> bool | ExcelError:
    return _combine(args, all)


@excel_function("OR")
def or_(*args: Arg) -> bool | ExcelError:
    return _combine(args, any)


@excel_function("NOT")
def not_(logical: Arg) -> bool | ExcelError:
    value = to_logical(logical)
    return value if isinstance(value, ExcelError) else not value


@excel_function("IFERROR")
def iferror(value: Arg, value_if_error: Arg) -> Arg:
    chosen = value_if_error if isinstance(value, ExcelError) else value
    return "" if chosen is None else chosen
