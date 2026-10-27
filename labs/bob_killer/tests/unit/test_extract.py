"""Extract (SPEC stage 1): openpyxl twice, nothing evaluated, everything into a RawWorkbook."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

import pytest

from bob_killer import registry
from bob_killer.contracts.raw import (
    CachedType,
    RawCell,
    RawUnsupported,
    RawWorkbook,
    SheetState,
    VbaModuleKind,
    VbaSourceStatus,
)
from bob_killer.extract import extract_workbook
from tests.unit.conftest import (
    EXTERNAL_LINK,
    FEATURES,
    ORACLE,
    VBA_PART,
    VBA_PROJECT,
    VBA_SOURCE,
    Structure,
    build_structure,
    build_with_feature,
    build_with_vba_part,
)

GoldenRaw = Callable[[str], RawWorkbook]


def _cells(raw: RawWorkbook) -> dict[tuple[str, str], RawCell]:
    return {(c.sheet, c.address): c for c in raw.cells}


def _golden(key: str) -> list[tuple[str, dict[str, Any]]]:
    return [(wid, row) for wid, book in ORACLE["workbooks"].items() for row in book[key]]


def _golden_id(case: object) -> str:
    if isinstance(case, dict):
        return "!".join(
            str(case[k]) for k in ("sheet", "address", "scope", "name", "origin") if k in case
        )
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


def _unsupported(raw: RawWorkbook) -> dict[tuple[str, str], str]:
    return {(u.kind, u.origin): u.reason for u in raw.unsupported}


@pytest.mark.parametrize("kind", sorted(FEATURES))
def test_unsupported_feature_is_reported_with_its_origin(kind: str) -> None:
    data, origin = build_with_feature(kind)
    found = _unsupported(extract_workbook(data))
    assert (kind, origin) in found
    assert found[(kind, origin)]


def test_detectors_run_through_the_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "detectors", registry.Registry("detectors"))
    marker = RawUnsupported(kind="test_marker", origin="Inputs!A1", reason="registered by a test")
    registry.detectors.add(marker.kind, lambda wb: (marker,))
    raw = extract_workbook(build_structure())
    assert marker in raw.unsupported
    assert set(FEATURES) <= set(registry.detectors.names())


def test_a_plain_workbook_has_no_unsupported_rows(structure_raw: RawWorkbook) -> None:
    assert not structure_raw.unsupported
    assert not structure_raw.vba_modules


def test_unreadable_vba_project_is_reported_not_raised() -> None:
    raw = extract_workbook(build_with_vba_part(b"not an OLE compound file"))
    assert not raw.vba_modules
    assert (VBA_PROJECT, VBA_PART) in _unsupported(raw)


@pytest.mark.parametrize(("workbook_id", "expected"), _golden("external_links"), ids=_golden_id)
def test_golden_external_link(
    golden_raw: GoldenRaw, workbook_id: str, expected: dict[str, str]
) -> None:
    reason = _unsupported(golden_raw(workbook_id))[(EXTERNAL_LINK, expected["origin"])]
    assert expected["target"] in reason


@pytest.mark.parametrize("workbook_id", sorted(ORACLE["workbooks"]))
def test_golden_vba_inventory_in_project_order(golden_raw: GoldenRaw, workbook_id: str) -> None:
    raw = golden_raw(workbook_id)
    expected = ORACLE["workbooks"][workbook_id]["vba_modules"]
    assert [(m.name, m.kind) for m in raw.vba_modules] == [
        (e["name"], VbaModuleKind(e["kind"])) for e in expected
    ]
    # Source needs oletools, which is not a dependency: each module is listed as unsupported.
    found = _unsupported(raw)
    for module in raw.vba_modules:
        assert module.source_status is VbaSourceStatus.NEEDS_OLETOOLS
        assert (VBA_SOURCE, module.name) in found
