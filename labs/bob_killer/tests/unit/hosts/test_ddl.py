"""hosts/snowflake/ddl.py: the snowflake DDL dialect over SNOWFLAKE_TABLES (docs/SPEC.md §6.2)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from bob_killer.contracts import TABLES, StrictModel
from bob_killer.contracts.bronze import BronzePayload, BronzeRow, LandedFile
from bob_killer.contracts.ddl import ddl_dialects
from bob_killer.contracts.runs import RunState
from bob_killer.hosts.snowflake import procedure
from bob_killer.hosts.snowflake.ddl import SNOWFLAKE_TABLES, column_type, table_ddl

GOLDEN = Path(__file__).resolve().parents[3] / "hosts/snowflake/sql/10_tables.sql"


def _lines(model: type[StrictModel]) -> list[str]:
    return [line.strip().rstrip(",") for line in table_ddl(model).splitlines()[1:-1]]


def test_snowflake_tables_extend_the_sqlite_tables_with_bronze() -> None:
    assert SNOWFLAKE_TABLES == (*TABLES, LandedFile, BronzeRow)


def test_dialect_is_registered_and_matches_the_golden_file() -> None:
    assert ddl_dialects["snowflake"](SNOWFLAKE_TABLES) == GOLDEN.read_text(encoding="utf-8")


@pytest.mark.parametrize("model", SNOWFLAKE_TABLES, ids=lambda m: m.__name__)
def test_every_model_column_is_not_null_in_field_order(model: type[StrictModel]) -> None:
    lines = _lines(model)[: len(model.model_fields)]
    assert [line.split()[0] for line in lines] == list(model.model_fields)
    assert all(line.endswith(" NOT NULL") for line in lines)


@pytest.mark.parametrize("model", SNOWFLAKE_TABLES, ids=lambda m: m.__name__)
def test_dialect_columns_and_informational_primary_key(model: type[StrictModel]) -> None:
    seq, written_at, pk = _lines(model)[len(model.model_fields) :]
    assert seq.startswith("_seq NUMBER AUTOINCREMENT ORDER")
    assert written_at.startswith("_written_at TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()")
    assert pk == f"PRIMARY KEY ({', '.join(model.primary_key)})"
    assert table_ddl(model).startswith(f"CREATE TABLE IF NOT EXISTS {model.table_name.upper()} (")


def test_unmapped_type_raises_type_error() -> None:
    class Unmapped(StrictModel):
        table_name = "unmapped"
        primary_key = ("items",)
        items: list[str]

    with pytest.raises(TypeError):
        table_ddl(Unmapped)


_ORACLE = json.loads(
    (Path(__file__).resolve().parents[2] / "oracle" / "snowflake_types.json").read_text("utf-8")
)
_ANNOTATIONS: dict[str, object] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "datetime": datetime,
    "enum": RunState,
    "nested_model": BronzePayload,
}


@pytest.mark.parametrize("kind", sorted(_ORACLE["cases"]))
def test_type_map_row_matches_the_spec(kind: str) -> None:
    assert column_type("c", _ANNOTATIONS[kind]) == _ORACLE["cases"][kind]


COMPILER_OBJECTS = GOLDEN.with_name("20_compiler_objects.sql")
TEARDOWN = GOLDEN.with_name("99_teardown.sql")


def test_compiler_objects_create_the_dbt_source_stage() -> None:
    stage = procedure.DBT_SRC.removeprefix("@")
    assert f"CREATE STAGE IF NOT EXISTS {stage}" in COMPILER_OBJECTS.read_text(encoding="utf-8")


def test_teardown_drops_the_run_output_schemas_with_the_deployment_schema() -> None:
    text = TEARDOWN.read_text(encoding="utf-8")
    assert f"<% schema %>{procedure.RUN_SCHEMA_INFIX}%" in text
