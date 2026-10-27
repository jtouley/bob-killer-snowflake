"""Criteria and text patterns of the conditional and lookup functions (SUMIF, VLOOKUP).

Sources: the SUMIF page (criteria as a number, text, or a comparison operator joined to a value
such as ">32"; wildcards ``?`` and ``*``; ``~`` before them makes them literal; ``""`` sums the
cells with no value), the COUNTIF page ("Criteria aren't case sensitive"), the VLOOKUP page
(wildcards in an exact match on text). Anything those pages do not settle is refused.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from bob_killer.runtime import operators
from bob_killer.runtime.coercion import CellValue, ExcelError, UnsupportedValue, parse_number_text

Match = Callable[[CellValue], bool]

_OPERATORS = (("<=", "LE"), (">=", "GE"), ("<>", "NE"), ("<", "LT"), (">", "GT"), ("=", "EQ"))
_TESTS: dict[str, Callable[[int], bool]] = {
    "EQ": lambda c: c == 0,
    "NE": lambda c: c != 0,
    "LT": lambda c: c < 0,
    "GT": lambda c: c > 0,
    "LE": lambda c: c <= 0,
    "GE": lambda c: c >= 0,
}
_WILDCARD = re.compile(r"~[?*]|~|[?*]")


def has_wildcard(pattern: str) -> bool:
    return any(ch in pattern for ch in "?*~")


def _regex(pattern: str) -> re.Pattern[str]:
    parts: list[str] = []
    last = 0
    for m in _WILDCARD.finditer(pattern):
        parts.append(re.escape(pattern[last : m.start()]))
        token = m.group()
        if token == "~":
            raise UnsupportedValue("~ before a character other than ? or *")  # pragma: no mutate
        literal = token.startswith("~")
        parts.append(re.escape(token[1]) if literal else (".*" if token == "*" else "."))
        last = m.end()
    parts.append(re.escape(pattern[last:]))
    return re.compile("".join(parts), re.IGNORECASE | re.ASCII | re.DOTALL)


def text_matches(pattern: str, text: str) -> bool:
    """Whether ``text`` meets the text ``pattern``: wildcards, case ignored (ASCII only)."""
    if not (pattern.isascii() and text.isascii()):
        if pattern == text and not has_wildcard(pattern):
            return True
        raise UnsupportedValue("a text pattern beyond ASCII")  # pragma: no mutate
    return _regex(pattern).fullmatch(text) is not None


def _number_test(test: Callable[[int], bool], number: float) -> Match:
    def match(cell: CellValue) -> bool:
        if isinstance(cell, ExcelError):
            raise UnsupportedValue("an error value in a criteria range")  # pragma: no mutate
        if isinstance(cell, bool):
            raise UnsupportedValue("a logical in a criteria range")  # pragma: no mutate
        if cell is None:
            if test(_order(0.0, number)):
                raise UnsupportedValue("a blank where 0 meets the criteria")  # pragma: no mutate
            return False
        if isinstance(cell, str):
            if is_number_text(cell):
                raise UnsupportedValue("number text in a criteria range")  # pragma: no mutate
            return False
        return test(_order(cell, number))

    return match


def _order(x: float, y: float) -> int:
    order = operators.compare(x, y)
    assert not isinstance(order, ExcelError)  # two numbers never give an error
    return order


def is_number_text(text: str) -> bool:
    """Text a formula would read as a number (or whose number is not established)."""
    try:
        return isinstance(parse_number_text(text), float)
    except UnsupportedValue:
        return True  # a form whose number is not established is not safe to call text


def _text_test(pattern: str) -> Match:
    if pattern.upper() in ("TRUE", "FALSE") or pattern.startswith("#"):
        raise UnsupportedValue(f"criteria {pattern!r}: a logical or an error?")  # pragma: no mutate
    if pattern.isascii():
        _regex(pattern)  # refuse a malformed pattern before any cell is read

    def match(cell: CellValue) -> bool:
        if isinstance(cell, ExcelError):
            raise UnsupportedValue("an error value in a criteria range")  # pragma: no mutate
        if not isinstance(cell, str):
            return False
        if cell == "" and text_matches(pattern, ""):
            raise UnsupportedValue("empty text where the pattern meets it")  # pragma: no mutate
        return cell != "" and text_matches(pattern, cell)

    return match


def _blank_test(cell: CellValue) -> bool:
    if cell == "":
        raise UnsupportedValue('empty text with the criteria ""')  # pragma: no mutate
    if isinstance(cell, ExcelError):
        raise UnsupportedValue("an error value in a criteria range")  # pragma: no mutate
    return cell is None


def criteria(value: CellValue) -> Match:
    """The cell test a SUMIF criteria stands for."""
    if isinstance(value, float) and not isinstance(value, bool):
        return _number_test(_TESTS["EQ"], value)
    if not isinstance(value, str):
        raise UnsupportedValue(f"criteria {value!r}")  # pragma: no mutate
    if value == "":
        return _blank_test
    op = next(((sym, name) for sym, name in _OPERATORS if value.startswith(sym)), None)
    symbol, name = op if op is not None else ("", "EQ")
    rest = value[len(symbol) :]
    if rest == "" or rest != rest.strip():
        raise UnsupportedValue(f"criteria {value!r}")  # pragma: no mutate
    number = parse_number_text(rest)
    if isinstance(number, float):
        return _number_test(_TESTS[name], number)
    if name != "EQ":
        raise UnsupportedValue(f"text criteria with {symbol!r}")  # pragma: no mutate
    return _text_test(rest)
