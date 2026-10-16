"""The ``snowflake`` DDL dialect over ``SNOWFLAKE_TABLES`` (docs/SPEC.md §6.2, D2).

Every model column is NOT NULL; the primary key is informational (Snowflake does not enforce it).
Two dialect columns follow the model columns: ``_seq`` (insert order) and ``_written_at``.

uv run python -m bob_killer.hosts.snowflake.ddl   # regenerates hosts/snowflake/sql/10_tables.sql
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from pathlib import Path

from bob_killer.contracts import TABLES, StrictModel
from bob_killer.contracts.bronze import BronzeRow, LandedFile
from bob_killer.contracts.ddl import ddl_dialects

SNOWFLAKE_TABLES: tuple[type[StrictModel], ...] = (*TABLES, LandedFile, BronzeRow)

_SCALARS: dict[object, str] = {
    str: "VARCHAR",
    int: "NUMBER(38,0)",
    float: "FLOAT",
    bool: "BOOLEAN",
    datetime: "TIMESTAMP_TZ",
}
DIALECT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("_seq", "NUMBER AUTOINCREMENT ORDER"),
    ("_written_at", "TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()"),
)
GOLDEN = Path(__file__).resolve().parents[4] / "hosts/snowflake/sql/10_tables.sql"


def column_type(name: str, annotation: object) -> str:
    if annotation in _SCALARS:
        return _SCALARS[annotation]
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "VARCHAR"
    if isinstance(annotation, type) and issubclass(annotation, StrictModel):
        return "VARIANT"
    raise TypeError(f"no Snowflake mapping for {name}: {annotation!r}")


def table_ddl(model: type[StrictModel]) -> str:
    cols = [
        f"{name} {column_type(name, field.annotation)} NOT NULL"
        for name, field in model.model_fields.items()
    ]
    cols += [f"{name} {spec}" for name, spec in DIALECT_COLUMNS]
    cols.append(f"PRIMARY KEY ({', '.join(model.primary_key)})")
    body = ",\n  ".join(cols)
    return f"CREATE TABLE IF NOT EXISTS {model.table_name.upper()} (\n  {body}\n);\n"


def schema_ddl(models: Iterable[type[StrictModel]]) -> str:
    return "\n".join(table_ddl(m) for m in models)


ddl_dialects.setdefault("snowflake", schema_ddl)


def main() -> int:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(schema_ddl(SNOWFLAKE_TABLES), encoding="utf-8")
    print(GOLDEN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
