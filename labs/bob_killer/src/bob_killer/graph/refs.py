"""A1 reference text: anchors, sheet prefixes, ranges and defined names."""

from __future__ import annotations

import re

from bob_killer.contracts.graph import (
    MAX_COLUMNS,
    MAX_ROWS,
    Anchor,
    CellRef,
    NameRef,
    RangeRef,
    Reference,
)

_CELL = re.compile(r"(\$?)([A-Za-z]{1,3})(\$?)([0-9]{1,7})")
_COLUMN = re.compile(r"(\$?)([A-Za-z]{1,3})")
_ROW = re.compile(r"(\$?)([0-9]{1,7})")
_NAME = re.compile(r"[A-Za-z_\\][A-Za-z0-9_.\\?]*")


class FormulaError(ValueError):
    """The formula cannot be parsed, or uses a reference form this stage does not support."""


def column_number(letters: str) -> int:
    number = 0
    for ch in letters.upper():
        number = number * 26 + ord(ch) - ord("A") + 1
    return number


def column_letters(number: int) -> str:
    letters = ""
    while number:
        number, rest = divmod(number - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def _in_sheet(column: int | None, row: int | None) -> bool:
    return (column is None or 1 <= column <= MAX_COLUMNS) and (row is None or 1 <= row <= MAX_ROWS)


def cell_anchor(text: str) -> Anchor | None:
    """The anchor of ``A1``/``$A$1`` inside the sheet, else None."""
    m = _CELL.fullmatch(text)
    if m is None:
        return None
    column, row = column_number(m[2]), int(m[4])
    if not _in_sheet(column, row):
        return None
    return Anchor(column=column, row=row, column_absolute=bool(m[1]), row_absolute=bool(m[3]))


def _line_anchor(text: str) -> Anchor | None:
    """A whole-column (``$A``) or whole-row (``$3``) corner."""
    if m := _COLUMN.fullmatch(text):
        column = column_number(m[2])
        return (
            Anchor(column=column, column_absolute=bool(m[1])) if _in_sheet(column, None) else None
        )
    if m := _ROW.fullmatch(text):
        row = int(m[2])
        return Anchor(row=row, row_absolute=bool(m[1])) if _in_sheet(None, row) else None
    return None


def _split_sheet(text: str) -> tuple[str | None, str]:
    if text.startswith("'"):
        i = 1
        while i < len(text):
            if text[i] == "'":
                if text[i + 1 : i + 2] == "'":
                    i += 2
                    continue
                break
            i += 1
        if text[i + 1 : i + 2] != "!":
            raise FormulaError(f"bad sheet prefix in {text!r}")
        return text[1:i].replace("''", "'"), text[i + 2 :]
    if "!" in text:
        sheet, rest = text.split("!", 1)
        return sheet, rest
    return None, text


def parse_reference(text: str) -> Reference:
    if text.startswith("["):
        raise FormulaError(f"external workbook reference {text!r} is not supported")
    sheet, rest = _split_sheet(text)
    if sheet is not None and ":" in sheet:  # Excel sheet names cannot contain ':'
        raise FormulaError(f"3D reference {text!r} is not supported")
    if "[" in rest or "#" in rest:
        raise FormulaError(f"reference {text!r} is not supported")
    if ":" in rest:
        return _range(sheet, rest, text)
    if (anchor := cell_anchor(rest)) is not None:
        return CellRef(sheet=sheet, at=anchor)
    if _NAME.fullmatch(rest):
        return NameRef(sheet=sheet, name=rest)
    raise FormulaError(f"unrecognised reference {text!r}")


def _range(sheet: str | None, rest: str, text: str) -> RangeRef:
    first, second = rest.split(":", 1)
    if "!" in second or second.startswith("'"):
        other, second = _split_sheet(second)
        if other != sheet:
            raise FormulaError(f"range {text!r} spans two sheets")
    start, end = cell_anchor(first), cell_anchor(second)
    if start is None or end is None:
        start, end = _line_anchor(first), _line_anchor(second)
    if start is None or end is None or (start.column is None) != (end.column is None):
        raise FormulaError(f"unrecognised range {text!r}")
    return RangeRef(sheet=sheet, start=start, end=end)
