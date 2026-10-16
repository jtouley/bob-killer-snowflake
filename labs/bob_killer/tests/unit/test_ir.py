"""contracts/ir.py: the Workbook IR as strict models, its YAML export/import and the wire value."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from tests.unit.conftest import Json, a1, build_ir, cell, num, op, param, sample_ir, sample_ir_json

ORACLE = Path(__file__).parents[1] / "oracle" / "ir_step_kinds.json"


def _step(data: Json, sid: str) -> Json:
    return next(s for s in data["steps"] if s["id"] == sid)


def test_ir_yaml_round_trips_identically() -> None:
    from bob_killer.ir import dump_ir, load_ir

    ir = sample_ir()
    text = dump_ir(ir)
    assert load_ir(text) == ir
    assert dump_ir(load_ir(text)) == text


def test_ir_yaml_is_the_json_shape() -> None:
    from bob_killer.ir import dump_ir, load_ir

    ir = sample_ir()
    reloaded = load_ir(dump_ir(ir))
    assert reloaded.model_dump(mode="json") == sample_ir_json()


def _set(path: tuple[Any, ...], value: Any) -> Any:
    def mutate(data: Json) -> None:
        target: Any = data
        for key in path[:-1]:
            target = target[key] if not callable(key) else key(target)
        target[path[-1]] = value

    return mutate


def _step_field(sid: str, field: str, value: Any) -> Any:
    def mutate(data: Json) -> None:
        _step(data, sid)[field] = value

    return mutate


def _append(section: str, item_from: Any) -> Any:
    def mutate(data: Json) -> None:
        data[section].append(item_from(data))

    return mutate


INVALID = {
    "extra key": _set(("surprise",), 1),
    "wrong schema version": _set(("schema_version",), 999),
    "coerced int": _set(("sheets", 0, "index"), "0"),
    "bad sha256": _set(("source", "sha256"), "xyz"),
    "bad node id": _set(("inputs", 0, "id"), "Units Sold"),
    "bad origin": _set(("inputs", 1, "origin"), ["Summary!B"]),
    "unknown sheet in origin": _set(("inputs", 1, "origin"), [a1("Nowhere", 1, 1)]),
    "unknown step kind": _step_field("tax", "kind", "pivot_expr"),
    "number with text field": _set(("parameters", 0, "default"), {"k": "n", "t": "x"}),
    "non-canonical hex": _set(("parameters", 0, "default"), {"k": "n", "h": "0x1.0p0"}),
    "nan hex": _set(("parameters", 0, "default"), {"k": "n", "h": "nan"}),
    "infinite hex": _set(("parameters", 0, "default"), {"k": "n", "h": "inf"}),
    "parameter default not a number": _set(("parameters", 0, "default"), {"k": "s", "t": "x"}),
    "unknown excel error": _set(("parameters", 0, "default"), {"k": "e", "e": "#OOPS!"}),
    "op arity": _step_field("tax", "expr", op("MUL", cell("Summary", 7, 2))),
    "unknown operator": _step_field("tax", "expr", op("MOD", num(1), num(2))),
    "dangling parameter": _step_field("grown", "expr", param("missing_param")),
    "dangling over input": _step_field("revenue", "over", "missing_input"),
    "dangling lookup": _step_field("east_rate", "lookup", "missing_lookup"),
    "dangling output step": _set(("outputs", 0, "step"), "missing_step"),
    "dangling vba translation": _set(("vba", 0, "translated_to"), "missing_step"),
    "duplicate node id": _append("inputs", lambda d: d["inputs"][1]),
    "input columns do not span the origin": _set(("inputs", 0, "columns"), []),
    "range ends before it starts": _step_field(
        "total_units",
        "expr",
        {
            "type": "call",
            "name": "SUM",
            "args": [
                {"type": "range", "sheet": "Data", "row": 5, "col": 2, "last_row": 2, "last_col": 2}
            ],
        },
    ),
    "scalar step over a range": _step_field("tax", "origin", [a1("Summary", 8, 2, 9, 2)]),
    "column step over two columns": _step_field("revenue", "origin", [a1("Data", 2, 4, 5, 5)]),
}


@pytest.mark.parametrize("mutation", INVALID.values(), ids=INVALID.keys())
def test_invalid_ir_is_rejected(mutation: Any) -> None:
    with pytest.raises(ValidationError):
        sample_ir(mutation)


def test_step_kinds_are_the_closed_registry() -> None:
    from bob_killer import registry
    from bob_killer.contracts.ir import STEP_MODELS

    expected = set(json.loads(ORACLE.read_text())["step_kinds"])
    assert set(registry.step_kinds.names()) == expected
    assert {registry.step_kinds.get(m.model_fields["kind"].default) for m in STEP_MODELS} == set(
        STEP_MODELS
    )
    kinds_in_sample = {s.kind for s in sample_ir().steps}
    assert kinds_in_sample == expected


finite = st.floats(allow_nan=False, allow_infinity=False)
excel_errors = st.sampled_from(["#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A"])


@given(x=finite)
def test_number_wire_is_float_hex(x: float) -> None:
    from bob_killer.contracts.ir import CellValue

    value = CellValue.number(x)
    wire = json.loads(value.wire())
    assert wire["h"] == x.hex()
    assert set(wire) == set(value.model_dump(exclude_none=True))
    assert CellValue.model_validate_json(value.wire()) == value


@given(
    value=st.one_of(
        st.text().map(lambda t: ("text", t)),
        st.booleans().map(lambda b: ("boolean", b)),
        excel_errors.map(lambda e: ("error", e)),
        st.just(("blank", None)),
    )
)
def test_other_wire_kinds_round_trip(value: tuple[str, Any]) -> None:
    from bob_killer.contracts.ir import CellValue, ExcelError

    maker, payload = value
    if maker == "blank":
        cv = CellValue.blank()
    elif maker == "error":
        cv = CellValue.error(ExcelError(payload))
    else:
        cv = getattr(CellValue, maker)(payload)
    assert CellValue.model_validate_json(cv.wire()) == cv
    assert len(json.loads(cv.wire())) == len(cv.model_dump(exclude_none=True))


sheet_names = st.text(
    alphabet=st.characters(blacklist_characters="[]:*?/\\", blacklist_categories=("Cs", "Cc")),
    min_size=1,
    max_size=12,
)


@given(
    sheet=sheet_names,
    row=st.integers(1, 1_048_576),
    col=st.integers(1, 16_384),
    height=st.integers(0, 40),
    width=st.integers(0, 5),
)
def test_a1_ranges_parse(sheet: str, row: int, col: int, height: int, width: int) -> None:
    from bob_killer.contracts.ir import cell_range

    last_row, last_col = min(row + height, 1_048_576), min(col + width, 16_384)
    parsed = cell_range(a1(sheet, row, col, last_row, last_col))
    assert (parsed.sheet, parsed.row, parsed.col, parsed.last_row, parsed.last_col) == (
        sheet,
        row,
        col,
        last_row,
        last_col,
    )
    cells = parsed.cells()
    assert len(cells) == (last_row - row + 1) * (last_col - col + 1)
    assert cells[0].row == row and cells[-1].col == last_col
    single = cell_range(a1(sheet, row, col))
    assert (single.last_row, single.last_col) == (row, col)


def test_unquoted_sheet_names_parse() -> None:
    from bob_killer.contracts.ir import cell_range

    quoted = cell_range(a1("Data", 2, 3, 4, 5))
    assert cell_range(f"{quoted.sheet}!$C$2:E4") == quoted


def test_built_ir_matches_its_json() -> None:
    data = sample_ir_json()
    assert build_ir(data).model_dump(mode="json") == data
