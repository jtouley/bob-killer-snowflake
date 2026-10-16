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
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import openpyxl
import pytest
from openpyxl.chart import BarChart, Reference
from openpyxl.packaging.relationship import Relationship
from openpyxl.pivot.cache import CacheDefinition, CacheField, CacheSource, WorksheetSource
from openpyxl.pivot.record import RecordList
from openpyxl.pivot.table import Location, TableDefinition
from openpyxl.styles import PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.workbook.external_link.external import ExternalBook, ExternalLink
from openpyxl.worksheet.formula import DataTableFormula
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


def structure_workbook() -> openpyxl.Workbook:
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
    return wb


def build_structure() -> bytes:
    return save(structure_workbook())


def save(wb: openpyxl.Workbook, extra_parts: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    if extra_parts:
        with zipfile.ZipFile(buf, "a") as zf:
            for name, data in extra_parts.items():
                zf.writestr(name, data)
    return buf.getvalue()


# Unsupported-feature kinds: the names detectors register under, plus the VBA inventory's.
CHART = "chart"
PIVOT_TABLE = "pivot_table"
EXTERNAL_LINK = "external_link"
DATA_TABLE = "data_table"
VBA_SOURCE = "vba_source"
VBA_PROJECT = "vba_project"
VBA_PART = "xl/vbaProject.bin"


def _add_chart(wb: openpyxl.Workbook) -> str:
    ws = wb["Inputs"]
    chart = BarChart()
    chart.add_data(Reference(ws, min_col=1, min_row=1, max_row=3))
    ws.add_chart(chart, "J5")
    return "Inputs!J5"


def _add_pivot_table(wb: openpyxl.Workbook) -> str:
    source = WorksheetSource(ref="A1:A3", sheet="Inputs")
    cache = CacheDefinition(
        cacheSource=CacheSource(type="worksheet", worksheetSource=source),
        cacheFields=[CacheField(name="qty")],
    )
    cache.records = RecordList()
    location = Location(ref="L1:M3", firstHeaderRow=1, firstDataRow=1, firstDataCol=1)
    pivot = TableDefinition(name="P1", cacheId=1, dataCaption="Values", location=location)
    pivot.cache = cache
    wb["Calc"]._pivots.append(pivot)
    return "Calc!L1:M3"


def _add_external_link(wb: openpyxl.Workbook) -> str:
    link = ExternalLink(externalBook=ExternalBook(id="rId1"))
    link.file_link = Relationship(
        type="externalLinkPath", Target="other.xlsx", TargetMode="External"
    )
    wb._external_links.append(link)
    return "[1]"


def _add_data_table(wb: openpyxl.Workbook) -> str:
    wb["Calc"]["C1"] = DataTableFormula(ref="C1:C3", dt2D=False, dtr=False, r1="A1")
    return "Calc!C1:C3"


FEATURES: dict[str, Callable[[openpyxl.Workbook], str]] = {
    CHART: _add_chart,
    PIVOT_TABLE: _add_pivot_table,
    EXTERNAL_LINK: _add_external_link,
    DATA_TABLE: _add_data_table,
}


def build_with_feature(kind: str) -> tuple[bytes, str]:
    """The structure workbook plus one unsupported feature; returns (bytes, expected origin)."""
    wb = structure_workbook()
    origin = FEATURES[kind](wb)
    return save(wb), origin


def build_with_vba_part(data: bytes) -> bytes:
    return save(structure_workbook(), {VBA_PART: data})


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
