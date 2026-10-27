"""ODCS v3.2.0 data contract for the Snowflake tables (docs/SPEC.md D13).

Generated from the contract models and the ``snowflake`` DDL dialect, so there is no second type
definition. Logical types come from each model's JSON Schema; physical types from the dialect.

uv run python -m bob_killer.hosts.snowflake.odcs   # regenerates the committed YAML
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bob_killer.contracts import SCHEMA_VERSION, StrictModel
from bob_killer.hosts.snowflake.ddl import DIALECT_COLUMNS, SNOWFLAKE_TABLES, column_type

GOLDEN = Path(__file__).resolve().parents[4] / "hosts/snowflake/contracts/bob_killer_app.odcs.yaml"

_FORMATS = {"date-time": "timestamp"}
_DIALECT_LOGICAL = {"NUMBER": "integer", "TIMESTAMP_TZ": "timestamp"}
_DIALECT_DESCRIPTIONS = {
    "_seq": "Insert order (dialect column).",
    "_written_at": "Write time; landed_at for LANDED_FILES (dialect column).",
}


def _logical(schema: dict[str, Any], field: dict[str, Any]) -> str:
    if "$ref" in field:
        field = schema["$defs"][field["$ref"].rsplit("/", 1)[-1]]
    return str(_FORMATS.get(field.get("format", ""), field["type"]))


def _nested(model: type[StrictModel]) -> list[dict[str, Any]]:
    schema = model.model_json_schema()
    out = []
    for name, field in model.model_fields.items():
        prop: dict[str, Any] = {
            "name": name,
            "logicalType": _logical(schema, schema["properties"][name]),
            "required": field.is_required(),
            "description": field.description or f"{model.__name__}.{name}",
        }
        if prop["logicalType"] == "array":
            prop["items"] = {"logicalType": _logical(schema, schema["properties"][name]["items"])}
        out.append(prop)
    return out


def _properties(model: type[StrictModel]) -> list[dict[str, Any]]:
    schema = model.model_json_schema()
    out = []
    for name, field in model.model_fields.items():
        prop: dict[str, Any] = {
            "name": name,
            "logicalType": _logical(schema, schema["properties"][name]),
            "physicalType": column_type(name, field.annotation),
            "required": field.is_required(),
            "primaryKey": name in model.primary_key,
            "description": field.description or f"{model.__name__}.{name}",
        }
        if name in model.primary_key:
            prop["primaryKeyPosition"] = model.primary_key.index(name) + 1
        if isinstance(field.annotation, type) and issubclass(field.annotation, StrictModel):
            prop["properties"] = _nested(field.annotation)
        out.append(prop)
    for name, spec in DIALECT_COLUMNS:
        physical = spec.split()[0]
        out.append(
            {
                "name": name,
                "logicalType": _DIALECT_LOGICAL[physical],
                "physicalType": physical,
                "required": False,
                "primaryKey": False,
                "description": _DIALECT_DESCRIPTIONS[name],
            }
        )
    return out


def build_contract() -> dict[str, Any]:
    return {
        "apiVersion": "v3.2.0",
        "kind": "DataContract",
        "id": "bob_killer_app",
        "name": "Bob Killer app tables",
        "version": f"{SCHEMA_VERSION}.0.0",
        "status": "active",
        "servers": [
            {
                "server": "bob_killer_app",
                "type": "snowflake",
                # The account is set at deploy time; it is read from no file.
                "account": "${SNOWFLAKE_ACCOUNT}",
                "database": "BOB_KILLER",
                "schema": "APP",
            }
        ],
        "schema": [
            {
                "name": model.table_name,
                "physicalName": model.table_name.upper(),
                "physicalType": "table",
                "logicalType": "object",
                "description": (model.__doc__ or model.__name__).strip().splitlines()[0],
                "properties": _properties(model),
            }
            for model in SNOWFLAKE_TABLES
        ],
    }


def render() -> str:
    return yaml.safe_dump(build_contract(), sort_keys=False, allow_unicode=True)


def main() -> int:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(render(), encoding="utf-8")
    print(GOLDEN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
