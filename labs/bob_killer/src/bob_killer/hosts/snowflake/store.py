"""SnowflakeRunStore: the RunRepository over a Snowpark session (docs/SPEC.md §5.2, §6.2).

Table and column names come from the contracts; every value is bound. Reads name their
columns (no ``SELECT *``, so ``_seq`` and ``_written_at`` never come back) and validate each
row strictly in JSON mode, so a bad enum value from the database raises.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from typing import Any, Protocol

from bob_killer.contracts import StrictModel
from bob_killer.contracts.runs import Run, RunState, StageStatus


class Frame(Protocol):
    def collect(self) -> Any: ...


class SqlSession(Protocol):
    """The part of ``snowflake.snowpark.Session`` the host uses."""

    def sql(self, query: str, params: Sequence[object] | None = ...) -> Frame: ...


def run_sql(session: SqlSession, query: str, params: Sequence[object] = ()) -> list[Any]:
    return list(session.sql(query, params=list(params)).collect())


# Column names of Snowflake's DML result row.
ROWS_INSERTED = "number of rows inserted"
ROWS_UPDATED = "number of rows updated"


def affected(rows: Sequence[Any], column: str) -> int:
    """A rows-affected count from a DML result (0 when the result has no row)."""
    return int(rows[0][column]) if rows else 0


def _json(value: object) -> object:
    return value.isoformat() if isinstance(value, datetime | date | time) else value


def load[M: StrictModel](model: type[M], row: Any) -> M:
    data: Mapping[str, object] = row.as_dict()
    return model.model_validate_json(json.dumps({k.lower(): _json(v) for k, v in data.items()}))


def _values(model: StrictModel) -> list[object]:
    return list(model.model_dump(mode="json").values())


def _table(model: type[StrictModel]) -> str:
    return model.table_name.upper()


def _cols(model: type[StrictModel]) -> str:
    return ", ".join(model.model_fields)


def _marks(model: type[StrictModel]) -> str:
    return ", ".join("?" * len(model.model_fields))


def merge_sql(model: type[StrictModel]) -> str:
    """Upsert one row on the model's primary key; a match updates the other columns in place."""
    names = tuple(model.model_fields)
    source = ", ".join(f"? AS {n}" for n in names)
    on = " AND ".join(f"t.{k} = s.{k}" for k in model.primary_key)
    updates = ", ".join(f"{n} = s.{n}" for n in names if n not in model.primary_key)
    values = ", ".join(f"s.{n}" for n in names)
    return (
        f"MERGE INTO {_table(model)} t USING (SELECT {source}) s ON {on} "
        f"WHEN MATCHED THEN UPDATE SET {updates} "
        f"WHEN NOT MATCHED THEN INSERT ({_cols(model)}) VALUES ({values})"
    )


class SnowflakeRunStore:
    def __init__(self, session: SqlSession) -> None:
        self._session = session

    def _sql(self, query: str, params: Sequence[object]) -> list[Any]:
        return run_sql(self._session, query, params)

    def insert_run(self, run: Run) -> None:
        self._sql(f"INSERT INTO {_table(Run)} ({_cols(Run)}) VALUES ({_marks(Run)})", _values(run))

    def get_run(self, run_id: str) -> Run | None:
        rows = self._sql(f"SELECT {_cols(Run)} FROM {_table(Run)} WHERE run_id = ?", (run_id,))
        return load(Run, rows[0]) if rows else None

    def set_state(self, run_id: str, state: RunState) -> None:
        self._sql(f"UPDATE {_table(Run)} SET state = ? WHERE run_id = ?", (state.value, run_id))

    def claim_run(self, run_id: str) -> bool:
        rows = self._sql(
            f"UPDATE {_table(Run)} SET state = '{RunState.RUNNING.value}' "
            f"WHERE run_id = ? AND state = '{RunState.QUEUED.value}'",
            (run_id,),
        )
        return affected(rows, ROWS_UPDATED) == 1

    def upsert_stage(self, status: StageStatus) -> None:
        self._sql(merge_sql(StageStatus), _values(status))

    def stages(self, run_id: str) -> tuple[StageStatus, ...]:
        rows = self._sql(
            f"SELECT {_cols(StageStatus)} FROM {_table(StageStatus)} "
            "WHERE run_id = ? ORDER BY _seq",
            (run_id,),
        )
        return tuple(load(StageStatus, r) for r in rows)
