"""Batched contract-row inserts: ``INSERT INTO <T> (<cols>) SELECT ... FROM VALUES (?, ...)``.

Every value is a bound parameter; a VARIANT column (a nested model) binds its JSON text and
goes through ``PARSE_JSON``. Column names are the contract field names, unquoted, as the host
DDL creates them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol

from bob_killer.contracts import StrictModel
from bob_killer.hosts.snowflake.ddl import column_type

DEFAULT_BATCH = 1_000


class SqlSession(Protocol):
    def sql(self, query: str, params: Sequence[Any] | None = None) -> Any: ...


def _variant(model: type[StrictModel]) -> set[str]:
    return {n for n, f in model.model_fields.items() if column_type(n, f.annotation) == "VARIANT"}


def insert_rows(
    session: SqlSession,
    model: type[StrictModel],
    rows: Sequence[StrictModel],
    *,
    batch_size: int = DEFAULT_BATCH,
) -> None:
    names = list(model.model_fields)
    variant = _variant(model)
    select = ", ".join(
        f"PARSE_JSON(column{i})" if n in variant else f"column{i}"
        for i, n in enumerate(names, start=1)
    )
    marks = "(" + ", ".join("?" for _ in names) + ")"
    head = f"INSERT INTO {model.table_name.upper()} ({', '.join(n.upper() for n in names)})"
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        params: list[Any] = []
        for row in chunk:
            dumped = row.model_dump(mode="json")
            params += [json.dumps(dumped[n]) if n in variant else dumped[n] for n in names]
        values = ", ".join(marks for _ in chunk)
        session.sql(f"{head} SELECT {select} FROM VALUES {values}", params=params).collect()
