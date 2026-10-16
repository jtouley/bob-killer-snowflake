"""Generate SQLite DDL (STRICT tables) from contract models. Unmapped types fail loudly."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import Enum

from bob_killer.contracts.base import StrictModel

_SCALARS: dict[type, str] = {str: "TEXT", int: "INTEGER", float: "REAL", datetime: "TEXT"}


def _column(name: str, annotation: object) -> str:
    if annotation is bool:
        return f"{name} INTEGER NOT NULL CHECK ({name} IN (0, 1))"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        allowed = ", ".join(f"'{m.value}'" for m in annotation)
        return f"{name} TEXT NOT NULL CHECK ({name} IN ({allowed}))"
    if isinstance(annotation, type) and annotation in _SCALARS:
        return f"{name} {_SCALARS[annotation]} NOT NULL"
    raise TypeError(f"no SQLite mapping for {name}: {annotation!r}")


def table_ddl(model: type[StrictModel]) -> str:
    cols = [_column(name, field.annotation) for name, field in model.model_fields.items()]
    cols.append(f"PRIMARY KEY ({', '.join(model.primary_key)})")
    body = ",\n  ".join(cols)
    return f"CREATE TABLE IF NOT EXISTS {model.table_name} (\n  {body}\n) STRICT;\n"


def schema_ddl(models: Iterable[type[StrictModel]]) -> str:
    return "\n".join(table_ddl(m) for m in models)
