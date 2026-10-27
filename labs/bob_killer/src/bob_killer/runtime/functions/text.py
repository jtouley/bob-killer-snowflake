"""TEXT (support.microsoft.com TEXT page: TEXT(value, format_text)).

Only an empty format_text is supported: a number with an empty (or omitted) format_text is
empty text, the value golden mt_dot_budget COSTS!F15 (=TEXT(E15,)) caches. Number format codes
are not implemented; any other format_text, and a value that is not a number, is refused.
"""

from __future__ import annotations

from bob_killer.registry import excel_function
from bob_killer.runtime.coercion import Arg, ExcelError, UnsupportedValue
from bob_killer.runtime.operators import operand


@excel_function("TEXT")
def text(value: Arg, format_text: Arg) -> str | ExcelError:
    v, fmt = operand(value), operand(format_text)
    for arg in (v, fmt):
        if isinstance(arg, ExcelError):
            return arg
    if fmt not in (None, ""):
        raise UnsupportedValue("a TEXT format_text other than empty")  # pragma: no mutate
    if not isinstance(v, float) or isinstance(v, bool):
        raise UnsupportedValue("TEXT of a value that is not a number")  # pragma: no mutate
    return ""
