"""workbook.db / run store: typed repository over the DDL generated from contracts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from bob_killer.contracts import TABLES, StrictModel
from bob_killer.contracts.ddl import schema_ddl
from bob_killer.contracts.runs import Run, RunState, StageStatus


def _row(model: StrictModel) -> list[object]:
    return list(model.model_dump(mode="json").values())


def _load[M: StrictModel](model: type[M], row: sqlite3.Row) -> M:
    # JSON-mode validation parses ISO datetimes and enum values without lax coercion.
    return model.model_validate_json(json.dumps(dict(row)))


class RunStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(schema_ddl(TABLES))

    def insert_run(self, run: Run) -> None:
        marks = ", ".join("?" * len(Run.model_fields))
        with self._conn:
            self._conn.execute(f"INSERT INTO {Run.table_name} VALUES ({marks})", _row(run))

    def get_run(self, run_id: str) -> Run | None:
        row = self._conn.execute(
            f"SELECT * FROM {Run.table_name} WHERE run_id = ?", (run_id,)
        ).fetchone()
        return None if row is None else _load(Run, row)

    def set_state(self, run_id: str, state: RunState) -> None:
        with self._conn:
            self._conn.execute(
                f"UPDATE {Run.table_name} SET state = ? WHERE run_id = ?", (state.value, run_id)
            )

    def upsert_stage(self, status: StageStatus) -> None:
        marks = ", ".join("?" * len(StageStatus.model_fields))
        with self._conn:
            self._conn.execute(
                f"INSERT OR REPLACE INTO {StageStatus.table_name} VALUES ({marks})", _row(status)
            )

    def stages(self, run_id: str) -> tuple[StageStatus, ...]:
        rows = self._conn.execute(
            f"SELECT * FROM {StageStatus.table_name} WHERE run_id = ? ORDER BY rowid", (run_id,)
        ).fetchall()
        return tuple(_load(StageStatus, r) for r in rows)
