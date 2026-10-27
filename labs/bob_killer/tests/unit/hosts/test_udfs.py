"""hosts/snowflake/udfs.py: one Python UDF per registered runtime function (SPEC-compiler-dbt §4.4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given

import bob_killer.runtime.functions  # noqa: F401  (registers the Excel functions)
from bob_killer.contracts.ir import CellValue
from bob_killer.registry import functions
from bob_killer.runtime import wire
from bob_killer.verify.config import values_equal
from tests.conftest import decode_cell, oracle_params
from tests.fakes.snowpark import FakeSession
from tests.unit.test_runtime import FAMILIES
from tests.unit.test_verify_config import wire_values

SQL = Path(__file__).resolve().parents[3] / "hosts/snowflake/sql/30_udfs.sql"


def _udfs() -> Any:
    from bob_killer.hosts.snowflake import udfs

    return udfs


def _expected_name(function: str) -> str:
    """BK_OP_<op> for a runtime operator OP_<op>, BK_FN_<NAME> (dots as _) for a function."""
    if function.startswith("OP_"):
        return f"BK_OP_{function.removeprefix('OP_')}"
    return f"BK_FN_{function.replace('.', '_')}"


def test_one_udf_per_registered_function_and_the_host_udfs() -> None:
    udfs = _udfs()
    by_name = {u.name: u for u in udfs.udfs()}
    expected = {_expected_name(f) for f in functions.names()}
    assert expected <= set(by_name)
    host = set(by_name) - expected
    assert host == {udfs.VALUES_EQUAL, udfs.WIRE_DECODE_NUMBER}
    assert len(by_name) == len(udfs.udfs())


def test_every_handler_resolves_to_a_module_attribute() -> None:
    udfs = _udfs()
    module = udfs.__name__
    for u in udfs.udfs():
        path, _, attr = u.handler.rpartition(".")
        assert path == module
        assert callable(getattr(udfs, attr)), u.handler


def test_ddl_file_matches_the_registry() -> None:
    assert SQL.read_text(encoding="utf-8") == _udfs().render_ddl()


def test_ddl_creates_python_312_udfs_importing_the_build_zip() -> None:
    udfs = _udfs()
    for u, statement in zip(udfs.udfs(), udfs.statements(), strict=True):
        assert statement.startswith(f"CREATE OR REPLACE FUNCTION {u.name}(")
        assert f"RUNTIME_VERSION = '{udfs.RUNTIME_VERSION}'" in statement
        assert f"IMPORTS = ('{udfs.IMPORTS}')" in statement
        assert f"HANDLER = '{u.handler}'" in statement


def test_create_udfs_runs_every_statement_in_order() -> None:
    udfs = _udfs()
    session = FakeSession()
    udfs.create_udfs(session)
    assert session.sql_texts == list(udfs.statements())


ORACLE = [p for p in oracle_params(*FAMILIES) if p.values[0]["call"] in functions]


@pytest.mark.parametrize("case", ORACLE)
def test_handler_returns_the_runtime_result_as_a_wire_object(case: dict[str, Any]) -> None:
    udfs = _udfs()
    args = [decode_cell(a) for a in case["args"]]
    expected = functions.get(case["call"])(*args)
    handler = getattr(udfs, udfs.handler_name(case["call"]))
    payload = json.loads(json.dumps([wire.encode(a) for a in args]))  # what Snowflake hands over
    got = wire.decode_arg(handler(payload))
    assert values_equal(got, expected)


@given(wire_values, wire_values)
def test_values_equal_udf_is_the_comparator_on_wire_objects(a: CellValue, b: CellValue) -> None:
    udfs = _udfs()
    handler = getattr(udfs, udfs.handler_of(udfs.VALUES_EQUAL))
    assert handler(a.model_dump(mode="json"), b.model_dump(mode="json")) == values_equal(a, b)


@given(wire_values)
def test_wire_decode_number_returns_only_numbers(v: CellValue) -> None:
    udfs = _udfs()
    got = getattr(udfs, udfs.handler_of(udfs.WIRE_DECODE_NUMBER))(v.model_dump(mode="json"))
    if v.h is None:
        assert got is None
    else:
        assert got.hex() == v.h
