"""runtime/: Excel semantics match the oracle files exactly (tests/oracle/runtime_*.json)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

import bob_killer.runtime.functions  # noqa: F401  (registers the Excel functions)
from bob_killer.contracts.ir import Operator
from bob_killer.registry import functions
from bob_killer.runtime import coercion, dates, rounding
from bob_killer.runtime.coercion import UnsupportedValue
from bob_killer.verify.config import values_equal
from tests.conftest import decode_cell, oracle_params

MODULES = {"coercion": coercion, "rounding": rounding}
FAMILIES = (
    "runtime_aggregate",
    "runtime_round",
    "runtime_logical",
    "runtime_coercion",
    "runtime_operators",
    "runtime_information",
    "runtime_lookup",
)
# Oracle files whose "refused" list holds inputs no fetched source settles (never guessed).
REFUSALS = ("runtime_aggregate", "runtime_information", "runtime_lookup")


def resolve(call: str) -> Callable[..., Any]:
    """``SUM`` -> the registered Excel function; ``coercion.to_number`` -> a runtime helper."""
    module, _, name = call.rpartition(".")
    fn: Callable[..., Any] = getattr(MODULES[module], name) if module else functions.get(call)
    return fn


@pytest.mark.parametrize("case", oracle_params(*FAMILIES))
def test_matches_oracle(case: dict[str, Any]) -> None:
    args = [decode_cell(a) for a in case["args"]]
    expected = decode_cell(case["expected"])
    actual = resolve(case["call"])(*args)
    assert values_equal(expected, actual), f"{case['call']}{tuple(args)} = {actual!r}"


@pytest.mark.parametrize("case", oracle_params(*REFUSALS, key="refused"))
def test_oracle_refusal_is_not_guessed(case: dict[str, Any]) -> None:
    args = [decode_cell(a) for a in case["args"]]
    with pytest.raises(UnsupportedValue):
        resolve(case["call"])(*args)


@pytest.mark.parametrize("op", list(Operator))
def test_every_ir_operator_resolves_to_a_runtime_function(op: Operator) -> None:
    # The dbt generator renders bk_op('<op.value>'), the BK_OP_<op.value> UDF (SPEC-compiler-dbt §4.4).
    assert f"OP_{op.value}" in functions


@pytest.mark.parametrize("case", oracle_params("runtime_dates", key="serials"))
def test_date_serial_both_ways(case: dict[str, Any]) -> None:
    year, month, day = case["ymd"]
    serial = float(case["serial"])
    system = case["date1904"]
    assert values_equal(serial, dates.ymd_to_serial(year, month, day, date1904=system))
    assert dates.serial_to_ymd(serial, date1904=system) == (year, month, day)


@pytest.mark.parametrize("case", oracle_params("runtime_dates", key="out_of_range"))
def test_date_serial_outside_excel_range(case: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="date"):
        dates.serial_to_ymd(float(case["serial"]), date1904=case["date1904"])


@pytest.mark.parametrize(
    ("call", "args"),
    [
        ("coercion.to_number", ["16:48:00"]),  # time text: VALUE accepts it, we do not yet
        ("coercion.to_number", ["6/1/2001"]),  # date text: locale-dependent
        ("coercion.to_number", ["50%"]),  # percent text: not on a fetched page yet
        ("coercion.to_number", ["1e400"]),  # beyond 9.99999999999999E+307
        ("coercion.to_logical", ["TRUE"]),  # text where a logical is expected
        ("rounding.number_to_text", [1e-7]),  # General-format notation unknown below 1E-5
        ("AVERAGE", [True]),  # the AVERAGE page says typed logicals are "not counted"
        ("SUM", [None]),  # an omitted argument
        ("ROUND", [(2.5,), 0]),  # an array where a scalar is expected
        ("IF", [(True,), 1, 2]),
        ("NOT", [(True,)]),
        ("AND", [(1.0,)]),  # numbers inside a reference: not documented
        ("coercion.to_number", ["\u00a012"]),  # CHAR(160) is not number white space in Excel
        ("coercion.to_number", ["\uff11\uff12"]),  # fullwidth digits: Excel result not established
        (
            "coercion.to_number",
            ["(5)"],
        ),  # accounting parentheses: Excel reads a negative; not on a fetched page
        # + and - results at or very close to zero: Excel 97+ compensates, threshold undocumented
        ("OP_SUB", [1.333 + 1.225 - 1.333, 1.225]),
        ("OP_ADD", [0.1, -0.1 + 2e-17]),
        ("OP_MUL", [1e308, 10.0]),  # beyond the largest double: operator result not documented
        ("OP_POW", [0.0, 0.0]),  # 0^0, 0^-1, (-8)^(1/3): not on the POWER page
        ("OP_POW", [0.0, -1.0]),
        ("OP_POW", [-8.0, 1 / 3]),
        ("OP_ADD", [(1.0, 2.0), 1.0]),  # a multi-cell reference: implicit intersection or array
        ("OP_EQ", [0.1 + 0.2, 0.3]),  # equal at 15 digits, unequal as doubles: undocumented
        ("OP_LT", ["a", "_"]),  # punctuation order in comparisons is not documented
        ("OP_EQ", [None, False]),  # blank against a logical: not documented
        ("OP_EQ", ["\u00e9", "\u00c9"]),  # case folding beyond ASCII: not documented
        ("OP_CONCAT", ["a" * 32767, "b"]),  # beyond 32 767 characters in a cell
    ],
)
def test_unsupported_input_is_refused_not_guessed(call: str, args: list[Any]) -> None:
    with pytest.raises(UnsupportedValue):
        resolve(call)(*args)


# --- the wire codec (D21): runtime values <-> CellValue wire objects -------------------------------


def _wire_cases() -> list[Any]:
    return [
        pytest.param(arg, id=f"{case['id']}/{i}")
        for case in (p.values[0] for p in oracle_params(*FAMILIES))
        for i, arg in enumerate([*case["args"], case.get("expected")])
    ]


@pytest.mark.parametrize("raw", _wire_cases())
def test_wire_round_trips_every_oracle_value(raw: Any) -> None:
    from bob_killer.runtime import wire

    value = decode_cell(raw)
    back = wire.decode_arg(json.loads(json.dumps(wire.encode(value))))
    assert type(back) is type(value)
    if isinstance(value, tuple):
        assert len(back) == len(value)
        assert all(values_equal(x, y) for x, y in zip(back, value, strict=True))
        assert getattr(back, "columns", None) == getattr(value, "columns", None)
    else:
        assert values_equal(back, value)


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_wire_keeps_every_double_bit_for_bit(x: float) -> None:
    from bob_killer.contracts.ir import CellValue
    from bob_killer.runtime import wire

    encoded = wire.encode(x)
    assert CellValue.model_validate(encoded) == CellValue.number(x)
    assert wire.decode_arg(encoded).hex() == x.hex()  # type: ignore[union-attr]


@pytest.mark.parametrize("error", list(coercion.ExcelError))
def test_wire_maps_each_runtime_error_to_the_contract_error(error: coercion.ExcelError) -> None:
    from bob_killer.contracts.ir import CellValue, ExcelError
    from bob_killer.runtime import wire

    assert CellValue.model_validate(wire.encode(error)) == CellValue.error(ExcelError(error.value))
    assert wire.decode_arg(wire.encode(error)) is error
