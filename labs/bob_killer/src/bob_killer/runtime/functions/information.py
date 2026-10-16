"""ISBLANK, ISERROR, ISNA (support.microsoft.com "IS functions").

The value is not converted: the text "#N/A" is text and "" is not an empty cell. A single-cell
reference is its cell; a larger one is refused (implicit intersection or an array).
"""

from __future__ import annotations

from bob_killer.registry import excel_function
from bob_killer.runtime.coercion import Arg, ExcelError
from bob_killer.runtime.operators import operand


@excel_function("ISBLANK")
def isblank(value: Arg) -> bool:
    return operand(value) is None


@excel_function("ISERROR")
def iserror(value: Arg) -> bool:
    return isinstance(operand(value), ExcelError)


@excel_function("ISNA")
def isna(value: Arg) -> bool:
    return operand(value) is ExcelError.NA
