"""runtime/: Excel semantics match the oracle files exactly (tests/oracle/runtime_*.json)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

import bob_killer.runtime.functions  # noqa: F401  (registers the Excel functions)
from bob_killer.registry import functions
from bob_killer.runtime import coercion, dates, rounding
from bob_killer.runtime.coercion import UnsupportedValue
from bob_killer.verify.config import values_equal
from tests.conftest import decode_cell, oracle_params

MODULES = {"coercion": coercion, "rounding": rounding}
FAMILIES = ("runtime_aggregate", "runtime_round", "runtime_logical", "runtime_coercion")


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
        ("rounding.number_to_text", [1e-7]),  # General-format notation unknown below 1E-5
        ("AVERAGE", [True]),  # the AVERAGE page says typed logicals are "not counted"
        ("SUM", [None]),  # an omitted argument
        ("ROUND", [(2.5,), 0]),  # an array where a scalar is expected
        ("IF", [(True,), 1, 2]),
        ("NOT", [(True,)]),
        ("AND", [(1.0,)]),  # numbers inside a reference: not documented
    ],
)
def test_unsupported_input_is_refused_not_guessed(call: str, args: list[Any]) -> None:
    with pytest.raises(UnsupportedValue):
        resolve(call)(*args)
