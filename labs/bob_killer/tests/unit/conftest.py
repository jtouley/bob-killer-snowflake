"""Shared builders for the extract tests.

Structure fixtures (sheets, formula text, names, tables, detectors) are authored here with
openpyxl at test time, so no binary fixture is committed. openpyxl cannot calculate, so these
workbooks carry no cached formula values. Cached values come only from the Excel-saved golden
workbooks, whose expected values live in ``tests/oracle/extract_golden.json``.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import openpyxl
import pytest
from openpyxl.styles import PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.table import Table

if TYPE_CHECKING:
    from bob_killer.contracts.raw import RawWorkbook

ORACLE_PATH = Path(__file__).resolve().parents[1] / "oracle" / "extract_golden.json"
ORACLE: dict[str, Any] = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))


class Structure:
    """What the structure workbook holds; tests compare extraction against these inputs."""

    sheets = (("Inputs", "visible"), ("Calc", "visible"), ("Lists", "hidden"))
    # cell -> (value written, expected cached type, expected canonical cached text)
    constants = {
        ("Inputs", "A1"): ("qty", "string", "qty"),
        ("Inputs", "A2"): (3, "number", "3.0"),
        ("Inputs", "A3"): (0.1, "number", "0.1"),
        ("Inputs", "B1"): (True, "bool", "TRUE"),
        ("Lists", "A1"): ("north", "string", "north"),
    }
    formulas = {
        ("Calc", "A1"): "=Inputs!A2*2",
        ("Calc", "A2"): "=SUM(Inputs!A2:A3)",
        ("Calc", "A3"): '=IF(Inputs!B1,"yes","no")',
    }
    styled_blank = ("Inputs", "D5")
    plain_constant = ("Inputs", "A2")
    names = (
        ("", "rate", "Inputs!$A$3"),
        ("Calc", "local_total", "Calc!$A$2"),
    )
    tables = (("Prices", "Inputs", "F1:G3"),)


def build_structure() -> bytes:
    wb = openpyxl.Workbook()
    for i, (name, state) in enumerate(Structure.sheets):
        ws = wb.active if i == 0 else wb.create_sheet()
        assert ws is not None
        ws.title = name
        ws.sheet_state = state  # type: ignore[assignment]
    for (sheet, address), (value, _, _) in Structure.constants.items():
        wb[sheet][address] = value
    for (sheet, address), formula in Structure.formulas.items():
        wb[sheet][address] = formula
    sheet, address = Structure.styled_blank
    wb[sheet][address].fill = PatternFill("solid", fgColor="FFFF00")
    for scope, name, refers_to in Structure.names:
        target = wb.defined_names if not scope else wb[scope].defined_names
        target[name] = DefinedName(name, attr_text=refers_to)
    for name, sheet, ref in Structure.tables:
        ws = wb[sheet]
        ws["F1"], ws["G1"] = "region", "price"
        ws.add_table(Table(displayName=name, ref=ref))
    return save(wb)


def save(wb: openpyxl.Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def golden_path(workbook_id: str) -> Path:
    """The golden file pinned by the oracle: golden/ first, else fetched and hash-checked."""
    import fetch_golden
    from bob_killer.contracts.golden import GoldenStatus

    sha256 = ORACLE["workbooks"][workbook_id]["sha256"]
    entry = next(
        e for e in fetch_golden.load_lock(fetch_golden.LOCK_PATH).workbooks if e.id == workbook_id
    )
    assert entry.filename is not None
    path = fetch_golden.DEST / entry.filename
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        pinned = entry.model_copy(update={"sha256": sha256, "status": GoldenStatus.RESOLVED})
        fetch_golden.fetch_entry(pinned, fetch_golden.DEST, accept=False)
    return path


@pytest.fixture(scope="session")
def golden_raw() -> Callable[[str], RawWorkbook]:
    from bob_killer.extract import extract_workbook

    cache: dict[str, RawWorkbook] = {}

    def get(workbook_id: str) -> RawWorkbook:
        if workbook_id not in cache:
            cache[workbook_id] = extract_workbook(golden_path(workbook_id).read_bytes())
        return cache[workbook_id]

    return get


@pytest.fixture(scope="session")
def structure_raw() -> RawWorkbook:
    from bob_killer.extract import extract_workbook

    return extract_workbook(build_structure())
