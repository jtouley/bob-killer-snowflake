"""ROUND, ROUNDUP, ROUNDDOWN on 15-significant-digit decimals (runtime/rounding.py)."""

from __future__ import annotations

import math
from collections.abc import Callable

from bob_killer.registry import excel_function
from bob_killer.runtime import rounding
from bob_killer.runtime.coercion import Arg, ExcelError, to_number


def _round(rule: Callable[[float, int], float], number: Arg, num_digits: Arg) -> float | ExcelError:
    x = to_number(number)
    if isinstance(x, ExcelError):
        return x
    digits = to_number(num_digits)
    if isinstance(digits, ExcelError):
        return digits
    result = rule(x, math.trunc(digits))  # open fact: a fractional num_digits is truncated
    return result if math.isfinite(result) else ExcelError.NUM


@excel_function("ROUND")
def round_(number: Arg, num_digits: Arg) -> float | ExcelError:
    return _round(rounding.round_half_away, number, num_digits)


@excel_function("ROUNDUP")
def roundup(number: Arg, num_digits: Arg) -> float | ExcelError:
    return _round(rounding.round_away, number, num_digits)


@excel_function("ROUNDDOWN")
def rounddown(number: Arg, num_digits: Arg) -> float | ExcelError:
    return _round(rounding.round_toward_zero, number, num_digits)
