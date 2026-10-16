"""The Raw layer of workbook.db (SPEC decision 9): DDL generated from contracts, written once."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from bob_killer.contracts.base import StrictModel
from bob_killer.contracts.ddl import schema_ddl
from bob_killer.contracts.raw import (
    RAW_TABLES,
    RawCell,
    RawDefinedName,
    RawSheet,
    RawSource,
    RawTable,
    RawUnsupported,
    RawVbaModule,
    RawWorkbook,
)

# RawWorkbook field -> the row model (and table) that stores it.
_LAYOUT: dict[str, type[StrictModel]] = {
    "sheets": RawSheet,
    "cells": RawCell,
    "defined_names": RawDefinedName,
    "tables": RawTable,
    "vba_modules": RawVbaModule,
    "unsupported": RawUnsupported,
}


class RawLayerWritten(Exception):
    """The Raw layer is immutable after its one write."""


def _insert(
    conn: sqlite3.Connection, model: type[StrictModel], rows: tuple[StrictModel, ...]
) -> None:
    marks = ", ".join("?" * len(model.model_fields))
    conn.executemany(
        f"INSERT INTO {model.table_name} VALUES ({marks})",
        [list(r.model_dump(mode="json").values()) for r in rows],
    )


def write_raw(path: Path, raw: RawWorkbook) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(schema_ddl(RAW_TABLES))
        with conn:
            if conn.execute(f"SELECT 1 FROM {RawSource.table_name}").fetchone():
                raise RawLayerWritten(f"{path} already holds a Raw layer")
            _insert(conn, RawSource, (raw.source,))
            for field, model in _LAYOUT.items():
                _insert(conn, model, getattr(raw, field))
    finally:
        conn.close()


def _load[M: StrictModel](conn: sqlite3.Connection, model: type[M]) -> tuple[M, ...]:
    rows = conn.execute(f"SELECT * FROM {model.table_name} ORDER BY rowid").fetchall()
    return tuple(model.model_validate_json(json.dumps(dict(r))) for r in rows)


def read_raw(path: Path) -> RawWorkbook:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        (source,) = _load(conn, RawSource)
        parts = {field: _load(conn, model) for field, model in _LAYOUT.items()}
    finally:
        conn.close()
    return RawWorkbook.model_validate({"source": source, **parts})
