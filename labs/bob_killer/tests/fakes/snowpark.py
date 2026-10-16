"""The one fake Snowpark session (docs/SPEC.md §8 Phase 2, P7 F2). Later phases extend this class.

It records every statement as ``(sql, params)`` in call order and answers each statement with the
scripted rows of the longest matching statement prefix (case-insensitive, leading space ignored).
A statement with no script returns no rows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from snowflake.snowpark import Row

# Column names Snowflake uses for DML results.
ROWS_INSERTED = "number of rows inserted"
ROWS_UPDATED = "number of rows updated"


class FakeDataFrame:
    def __init__(self, rows: list[Row]) -> None:
        self._rows = rows

    def collect(self) -> list[Row]:
        return list(self._rows)


class FakeSession:
    def __init__(self) -> None:
        self.statements: list[tuple[str, Sequence[Any] | None]] = []
        self._scripts: dict[str, list[Row]] = {}

    def script(self, prefix: str, rows: Sequence[Mapping[str, Any]]) -> None:
        """Answer statements that start with ``prefix`` with ``rows`` (one mapping per row)."""
        self._scripts[prefix.upper()] = [Row(**dict(r)) for r in rows]

    def script_affected(self, prefix: str, *, inserted: int = 0, updated: int = 0) -> None:
        """Answer a MERGE / INSERT / UPDATE with Snowflake's rows-affected result row."""
        self.script(prefix, [{ROWS_INSERTED: inserted, ROWS_UPDATED: updated}])

    def sql(self, query: str, params: Sequence[Any] | None = None) -> FakeDataFrame:
        self.statements.append((query, params))
        key = query.lstrip().upper()
        matches = [p for p in self._scripts if key.startswith(p)]
        return FakeDataFrame(self._scripts[max(matches, key=len)] if matches else [])

    @property
    def sql_texts(self) -> list[str]:
        return [s for s, _ in self.statements]

    @staticmethod
    def rows_affected(row: Row, column: str = ROWS_INSERTED) -> int:
        return int(row[column])
