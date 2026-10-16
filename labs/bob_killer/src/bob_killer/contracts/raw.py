"""The Raw layer of workbook.db (SPEC decision 9): what Extract read, before any interpretation.

Written once by stage 1 and immutable after. Every row model is also a table (``RAW_TABLES``).
Cached values are kept as canonical text so the SQLite DDL stays one column per field:

- ``number``: ``repr(float(v))``, which round-trips the IEEE-754 double exactly;
- ``string``: the text itself (a formula that returned ``""`` is ``string`` with empty text);
- ``bool``: ``TRUE`` or ``FALSE``;
- ``error``: the error literal, for example ``#N/A``;
- ``date``: ISO 8601, as openpyxl converts date-formatted numbers;
- ``blank``: an empty cell (it exists in the file, usually for its style);
- ``missing``: a formula cell with no cached result (the file was never calculated by Excel).
"""

from __future__ import annotations

from enum import StrEnum

from bob_killer.contracts.base import StrictModel


class SheetState(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"
    VERY_HIDDEN = "veryHidden"


class CachedType(StrEnum):
    NUMBER = "number"
    STRING = "string"
    BOOL = "bool"
    ERROR = "error"
    DATE = "date"
    BLANK = "blank"
    MISSING = "missing"


class VbaModuleKind(StrEnum):
    STANDARD = "standard"
    DOCUMENT = "document"
    CLASS = "class"
    DESIGNER = "designer"


class VbaSourceStatus(StrEnum):
    NEEDS_OLETOOLS = "needs_oletools"


class RawSource(StrictModel):
    table_name = "source"
    primary_key = ("sha256",)

    sha256: str


class RawSheet(StrictModel):
    table_name = "sheets"
    primary_key = ("name",)

    name: str
    position: int
    state: SheetState


class RawCell(StrictModel):
    table_name = "cells"
    primary_key = ("sheet", "address")

    sheet: str
    address: str
    formula: str  # "" for a constant cell
    cached_value: str
    cached_type: CachedType
    style_id: int


class RawDefinedName(StrictModel):
    table_name = "defined_names"
    primary_key = ("scope", "name")

    scope: str  # "" for workbook scope, else the sheet name
    name: str
    refers_to: str


class RawTable(StrictModel):
    table_name = "tables"
    primary_key = ("name",)

    name: str
    sheet: str
    ref: str


class RawVbaModule(StrictModel):
    table_name = "vba_modules"
    primary_key = ("name",)

    name: str
    kind: VbaModuleKind
    source_status: VbaSourceStatus


class RawUnsupported(StrictModel):
    table_name = "unsupported"
    primary_key = ("kind", "origin")

    kind: str  # the registered detector name, for example ``pivot_table``
    origin: str
    reason: str


class RawWorkbook(StrictModel):
    source: RawSource
    sheets: tuple[RawSheet, ...]
    cells: tuple[RawCell, ...]
    defined_names: tuple[RawDefinedName, ...]
    tables: tuple[RawTable, ...]
    vba_modules: tuple[RawVbaModule, ...]
    unsupported: tuple[RawUnsupported, ...]


RAW_TABLES: tuple[type[StrictModel], ...] = (
    RawSource,
    RawSheet,
    RawCell,
    RawDefinedName,
    RawTable,
    RawVbaModule,
    RawUnsupported,
)
