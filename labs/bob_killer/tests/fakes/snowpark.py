"""The one fake Snowpark session (docs/SPEC.md §8 Phase 2, P7 F2). Later phases extend this class.

It records every statement as ``(sql, params)`` in call order and answers each statement with the
scripted rows of the longest matching statement prefix (case-insensitive, leading space ignored).
A statement with no script returns no rows. A handler script (``script_handler``) computes the
rows from the bound params per statement, so a test can keep table state or raise (fault injection).
Bound params are recorded as a tuple (``()`` when none). It also fakes the stage file API
(``session.file``; ``REMOVE ?`` deletes the bound path) and ``session.call`` (``block=False``
returns a ``FakeAsyncJob``).
"""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping, Sequence
from typing import IO, Any

from snowflake.snowpark import Row

# Column names Snowflake uses for DML results.
ROWS_INSERTED = "number of rows inserted"
ROWS_UPDATED = "number of rows updated"

type Params = Sequence[Any] | None
type Handler = Callable[[Params], Sequence[Mapping[str, Any]]]


class FakeDataFrame:
    def __init__(self, rows: list[Row]) -> None:
        self._rows = rows

    def collect(self) -> list[Row]:
        return list(self._rows)


class FakeFileOperation:
    """``session.file``: staged paths (``@STAGE/name``) to bytes; reads and puts are recorded."""

    def __init__(self) -> None:
        self.staged: dict[str, bytes] = {}
        self.reads: list[str] = []
        self.puts: list[tuple[str, dict[str, object]]] = []

    def get_stream(self, stage_location: str, decompress: bool = False) -> IO[bytes]:
        self.reads.append(stage_location)
        return io.BytesIO(self.staged[stage_location])

    def put_stream(self, input_stream: IO[bytes], stage_location: str, **options: object) -> None:
        self.puts.append((stage_location, options))
        data = input_stream.read()
        if options.get("overwrite", False) or stage_location not in self.staged:
            self.staged[stage_location] = data


class FakeAsyncJob:
    """What ``session.call(..., block=False)`` returns."""

    def __init__(self, result: object, *, done: bool = True) -> None:
        self._result = result
        self.done = done

    def is_done(self) -> bool:
        return self.done

    def result(self) -> object:
        return self._result


class FakeSession:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self._scripts: dict[str, list[Row] | Handler] = {}
        self.file = FakeFileOperation()
        self.call_results: dict[str, object] = {}
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def script(self, prefix: str, rows: Sequence[Mapping[str, Any]]) -> None:
        """Answer statements that start with ``prefix`` with ``rows`` (one mapping per row)."""
        self._scripts[prefix.upper()] = [Row(**dict(r)) for r in rows]

    def script_affected(self, prefix: str, *, inserted: int = 0, updated: int = 0) -> None:
        """Answer a MERGE / INSERT / UPDATE with Snowflake's rows-affected result row."""
        self.script(prefix, [{ROWS_INSERTED: inserted, ROWS_UPDATED: updated}])

    def script_handler(self, prefix: str, handler: Handler) -> None:
        """Answer statements that start with ``prefix`` with ``handler(params)``, per statement."""
        self._scripts[prefix.upper()] = handler

    def sql(self, query: str, params: Sequence[Any] | None = None) -> FakeDataFrame:
        self.statements.append((query, tuple(params or ())))
        key = query.lstrip().upper()
        if key.startswith("REMOVE ") and params:
            self.file.staged.pop(str(params[0]), None)
        matches = [p for p in self._scripts if key.startswith(p)]
        if not matches:
            return FakeDataFrame([])
        scripted = self._scripts[max(matches, key=len)]
        if callable(scripted):
            return FakeDataFrame([Row(**dict(r)) for r in scripted(params)])
        return FakeDataFrame(scripted)

    @property
    def sql_texts(self) -> list[str]:
        return [s for s, _ in self.statements]

    @staticmethod
    def rows_affected(row: Row, column: str = ROWS_INSERTED) -> int:
        return int(row[column])

    def call(self, name: str, *args: object, block: bool = True, **kwargs: Any) -> object:
        """``call_results[name]`` (a value, or a callable of the args); a job when not blocking."""
        self.calls.append((name, args, {"block": block, **kwargs}))
        result = self.call_results.get(name)
        value = result(*args) if callable(result) else result
        if block or isinstance(value, FakeAsyncJob):
            return value
        return FakeAsyncJob(value)
