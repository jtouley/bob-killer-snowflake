"""hosts/snowflake/odcs.py: the ODCS v3.2.0 contract generated from SNOWFLAKE_TABLES (D13)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from bob_killer.contracts import StrictModel
from bob_killer.hosts.snowflake.ddl import DIALECT_COLUMNS, SNOWFLAKE_TABLES, column_type
from bob_killer.hosts.snowflake.odcs import GOLDEN, build_contract, render

ORACLE = Path(__file__).resolve().parents[2] / "oracle"
ODCS_SCHEMA = json.loads((ORACLE / "odcs-json-schema-v3.2.0.json").read_text(encoding="utf-8"))
JSON_TO_LOGICAL = {"date-time": "timestamp"}


def _validate(document: object) -> None:
    jsonschema.validators.validator_for(ODCS_SCHEMA)(ODCS_SCHEMA).validate(document)


def _table(model: type[StrictModel]) -> dict[str, Any]:
    (table,) = [t for t in build_contract()["schema"] if t["name"] == model.table_name]
    return table


def _prop(model: type[StrictModel], name: str) -> dict[str, Any]:
    (prop,) = [p for p in _table(model)["properties"] if p["name"] == name]
    return prop


def _logical(model: type[StrictModel], name: str) -> str:
    """The ODCS logical type the model's own JSON Schema implies for one field."""
    schema = model.model_json_schema()
    field = schema["properties"][name]
    if "$ref" in field:
        field = schema["$defs"][field["$ref"].rsplit("/", 1)[-1]]
    return JSON_TO_LOGICAL.get(field.get("format", ""), field["type"])


FIELDS = [(m, n) for m in SNOWFLAKE_TABLES for n in m.model_fields]


def test_generated_contract_validates_against_the_vendored_odcs_schema() -> None:
    _validate(build_contract())


def test_committed_yaml_is_the_generated_contract() -> None:
    text = GOLDEN.read_text(encoding="utf-8")
    assert text == render()
    _validate(yaml.safe_load(text))


@pytest.mark.parametrize("model", SNOWFLAKE_TABLES, ids=lambda m: m.__name__)
def test_one_schema_object_per_table_with_dialect_columns(model: type[StrictModel]) -> None:
    table = _table(model)
    assert table["physicalName"] == model.table_name.upper()
    names = [p["name"] for p in table["properties"]]
    assert names == [*model.model_fields, *(name for name, _ in DIALECT_COLUMNS)]


@pytest.mark.parametrize(("model", "name"), FIELDS, ids=lambda v: getattr(v, "__name__", v))
def test_property_matches_the_model_field_and_the_dialect(
    model: type[StrictModel], name: str
) -> None:
    prop = _prop(model, name)
    assert prop["physicalType"] == column_type(name, model.model_fields[name].annotation)
    assert prop["logicalType"] == _logical(model, name)
    assert prop["required"] is model.model_fields[name].is_required()
    assert prop["primaryKey"] is (name in model.primary_key)
    if name in model.primary_key:
        assert prop["primaryKeyPosition"] == model.primary_key.index(name) + 1
    nested = model.model_fields[name].annotation
    if isinstance(nested, type) and issubclass(nested, StrictModel):
        assert [p["name"] for p in prop["properties"]] == list(nested.model_fields)
        for sub in prop["properties"]:
            assert sub["logicalType"] == _logical(nested, sub["name"])
