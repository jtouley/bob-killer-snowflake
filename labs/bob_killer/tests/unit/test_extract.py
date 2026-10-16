"""Extract (SPEC stage 1): openpyxl twice, nothing evaluated, everything into a RawWorkbook."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

import pytest

from bob_killer.contracts.raw import CachedType, RawCell, RawWorkbook, SheetState
from bob_killer.extract import extract_workbook
from tests.unit.conftest import ORACLE, Structure, build_structure

GoldenRaw = Callable[[str], RawWorkbook]


def _cells(raw: RawWorkbook) -> dict[tuple[str, str], RawCell]:
    return {(c.sheet, c.address): c for c in raw.cells}


def _golden(key: str) -> list[tuple[str, dict[str, Any]]]:
    return [(wid, row) for wid, book in ORACLE["workbooks"].items() for row in book[key]]


def _golden_id(case: object) -> str:
    if isinstance(case, dict):
        return "!".join(str(case[k]) for k in ("sheet", "address", "scope", "name") if k in case)
    return str(case)


def test_source_is_the_sha256_of_the_bytes() -> None:
    data = build_structure()
    assert extract_workbook(data).source.sha256 == hashlib.sha256(data).hexdigest()


def test_sheets_keep_workbook_order_and_state(structure_raw: RawWorkbook) -> None:
    assert [(s.name, s.state) for s in structure_raw.sheets] == [
        (name, SheetState(state)) for name, state in Structure.sheets
    ]
    assert [s.position for s in structure_raw.sheets] == list(range(len(Structure.sheets)))


@pytest.mark.parametrize("key", sorted(Structure.formulas), ids=_golden_id)
def test_formula_text_is_kept_and_never_evaluated(
    structure_raw: RawWorkbook, key: tuple[str, str]
) -> None:
    cell = _cells(structure_raw)[key]
    assert cell.formula == Structure.formulas[key]
    # openpyxl wrote the file, so Excel never cached a result: nothing is computed in its place.
    assert cell.cached_type is CachedType.MISSING
    assert not cell.cached_value


@pytest.mark.parametrize("key", sorted(Structure.constants), ids=_golden_id)
def test_constant_is_its_own_cached_value(structure_raw: RawWorkbook, key: tuple[str, str]) -> None:
    _, cached_type, cached_value = Structure.constants[key]
    cell = _cells(structure_raw)[key]
    assert not cell.formula
    assert cell.cached_type is CachedType(cached_type)
    assert cell.cached_value == cached_value


def test_styled_blank_cell_is_kept_with_its_style(structure_raw: RawWorkbook) -> None:
    cells = _cells(structure_raw)
    blank = cells[Structure.styled_blank]
    assert blank.cached_type is CachedType.BLANK
    assert not blank.formula
    assert not blank.cached_value
    assert blank.style_id != cells[Structure.plain_constant].style_id


def test_defined_names_keep_scope(structure_raw: RawWorkbook) -> None:
    found = {(n.scope, n.name, n.refers_to) for n in structure_raw.defined_names}
    assert found == set(Structure.names)


def test_tables(structure_raw: RawWorkbook) -> None:
    assert {(t.name, t.sheet, t.ref) for t in structure_raw.tables} == set(Structure.tables)


@pytest.mark.parametrize("workbook_id", sorted(ORACLE["workbooks"]))
def test_golden_source_hash(golden_raw: GoldenRaw, workbook_id: str) -> None:
    assert golden_raw(workbook_id).source.sha256 == ORACLE["workbooks"][workbook_id]["sha256"]


@pytest.mark.parametrize(("workbook_id", "expected"), _golden("sheets"), ids=_golden_id)
def test_golden_sheet_state(
    golden_raw: GoldenRaw, workbook_id: str, expected: dict[str, str]
) -> None:
    states = {s.name: s.state for s in golden_raw(workbook_id).sheets}
    assert states[expected["name"]] is SheetState(expected["state"])


@pytest.mark.parametrize(("workbook_id", "expected"), _golden("cells"), ids=_golden_id)
def test_golden_cell_matches_excel(
    golden_raw: GoldenRaw, workbook_id: str, expected: dict[str, str]
) -> None:
    cell = _cells(golden_raw(workbook_id))[(expected["sheet"], expected["address"])]
    assert cell.formula == expected["formula"]
    assert cell.cached_type is CachedType(expected["cached_type"])
    assert cell.cached_value == expected["cached_value"]


@pytest.mark.parametrize(("workbook_id", "expected"), _golden("defined_names"), ids=_golden_id)
def test_golden_defined_name(
    golden_raw: GoldenRaw, workbook_id: str, expected: dict[str, str]
) -> None:
    found = {(n.scope, n.name): n.refers_to for n in golden_raw(workbook_id).defined_names}
    assert found[(expected["scope"], expected["name"])] == expected["refers_to"]
