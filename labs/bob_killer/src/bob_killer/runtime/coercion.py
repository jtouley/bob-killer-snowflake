"""Excel coercion: blank vs zero vs empty text, text to number, logicals as numbers, errors.

Sources: support.microsoft.com "Calculation operators and precedence" (how Excel converts values
in formulas), the N, VALUE and IFERROR function pages.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal

from bob_killer.runtime.rounding import number_to_text
from bob_killer.runtime.values import Arg, CellValue, ExcelError, Range, UnsupportedValue

__all__ = [
    "Arg",
    "CellValue",
    "ExcelError",
    "Range",
    "UnsupportedValue",
    "cell_result",
    "parse_number_text",
    "to_logical",
    "to_number",
    "to_text",
]

# en-US number text: sign, optional $, digits with optional comma grouping, fraction, exponent, %.
_NUMBER_TEXT = re.compile(
    r"\s*(?P<sign>[+-]?)\$?(?=\.?\d)(?P<int>\d{1,3}(?:,\d{3})+|\d*)(?P<frac>\.\d*)?"
    r"(?P<exp>[eE][+-]?\d+)?(?P<pct>%?)\s*"
)
# Text Excel may read as a date or time ("6/1/2001", "16:48:00", "5 Jan 2020", "4 PM").
_DATE_OR_TIME_TEXT = re.compile(
    r"\d\s*[/:-]\s*\d|(?i:\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|\b[ap]m\b)"
)


def _scalar(value: Arg) -> CellValue:
    if isinstance(value, tuple):
        raise UnsupportedValue("an array where one value is expected")  # pragma: no mutate
    return value


def parse_number_text(text: str) -> float | ExcelError:
    """Text as a number, or #VALUE! when it is not number text (VALUE function remarks)."""
    m = _NUMBER_TEXT.fullmatch(text)
    if m is None:
        if re.search(r"\d", text) and _DATE_OR_TIME_TEXT.search(text):
            raise UnsupportedValue(f"date or time text {text!r}")  # pragma: no mutate
        return ExcelError.VALUE
    if m.group("pct"):
        raise UnsupportedValue(f"percent text {text!r}")  # pragma: no mutate
    digits = m.group("int").replace(",", "") + (m.group("frac") or "") + (m.group("exp") or "")
    number = float(Decimal(f"{m.group('sign')}{digits}"))
    if not math.isfinite(number):
        raise UnsupportedValue(f"{text!r} exceeds the largest number")  # pragma: no mutate
    return number


def to_number(value: Arg) -> float | ExcelError:
    """A value where a formula expects a number: blank is 0, TRUE 1, FALSE 0, text is parsed."""
    value = _scalar(value)
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, str):
        return parse_number_text(value)
    return value


def to_text(value: Arg) -> str | ExcelError:
    """A value where a formula expects text: TRUE is "TRUE", numbers use 15 digits."""
    value = _scalar(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return number_to_text(value)
    return value


def to_logical(value: Arg) -> bool | ExcelError:
    """A value where a formula expects TRUE or FALSE: a number is TRUE unless it is 0."""
    value = _scalar(value)
    if value is None:
        return False
    if isinstance(value, float):
        return value != 0
    if isinstance(value, str):
        raise UnsupportedValue(f"text {value!r} where a logical is expected")  # pragma: no mutate
    return value


def cell_result(value: CellValue) -> CellValue:
    """A formula's final value in its cell: a blank result shows as 0 (IF function page)."""
    return 0.0 if value is None else value
