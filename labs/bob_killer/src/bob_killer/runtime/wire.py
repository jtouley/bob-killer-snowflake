"""The wire codec (D21): runtime values to and from the JSON of the contract ``CellValue``.

A scalar is a ``CellValue`` dump (``{"k":"n","h":"<float.hex()>"}``, ...). A range with its shape
(an ``Area``) is ``{"cols": <columns>, "cells": [<wire>, ...]}``, cells row by row. A range without
a shape is a JSON array of wire objects. This is how values cross SQL into and out of the BK_*
UDFs; no double ever crosses as a bare number.
"""

from __future__ import annotations

import json
from typing import Any

from bob_killer.contracts.ir import CellValue as Wire
from bob_killer.contracts.ir import ExcelError as WireError
from bob_killer.contracts.ir import ValueKind
from bob_killer.runtime.values import Area, Arg, CellValue, ExcelError

COLUMNS = "cols"
CELLS = "cells"


def to_wire(value: CellValue) -> Wire:
    if value is None:
        return Wire.blank()
    if isinstance(value, bool):
        return Wire.boolean(value)
    if isinstance(value, int | float):
        return Wire.number(float(value))
    if isinstance(value, str):
        return Wire.text(value)
    return Wire.error(WireError(value.value))


def from_wire(value: Wire) -> CellValue:
    match value.k:
        case ValueKind.NUMBER:
            return float.fromhex(value.h)  # type: ignore[arg-type]
        case ValueKind.TEXT:
            return value.t
        case ValueKind.BOOLEAN:
            return value.b
        case ValueKind.ERROR:
            return ExcelError(value.e.value)  # type: ignore[union-attr]
    return None


def encode(value: Arg) -> Any:
    if isinstance(value, Area):
        return {COLUMNS: value.columns, CELLS: [encode(v) for v in value]}
    if isinstance(value, tuple):
        return [encode(v) for v in value]
    return to_wire(value).model_dump()  # enum members are str: json.dumps gives the D21 text


def decode_arg(obj: Any) -> Arg:
    if isinstance(obj, list):
        return tuple(_scalar(v) for v in obj)
    if isinstance(obj, dict) and CELLS in obj:
        return Area((_scalar(v) for v in obj[CELLS]), columns=int(obj[COLUMNS]))
    return _scalar(obj)


def _scalar(obj: Any) -> CellValue:
    return from_wire(Wire.model_validate_json(json.dumps(obj)))  # strict: JSON mode
