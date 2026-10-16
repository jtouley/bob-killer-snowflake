"""Shared builders and fixtures for unit and integration tests."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from bob_killer.contracts.runs import Run
    from bob_killer.store import RunRepository
    from tests.fakes.snowpark import FakeSession


@pytest.fixture(autouse=True)
def _empty_stages() -> Iterator[None]:
    """Each test starts from the empty core stage baseline; entries come back after it (G1)."""
    from bob_killer import registry

    with registry.stages.snapshot():
        registry.stages.clear()
        yield


ORACLE_DIR = Path(__file__).parent / "oracle"


def load_oracle(name: str) -> dict[str, Any]:
    """One ``tests/oracle/<name>.json`` file. Every case in it carries ``source`` and ``verified_by``."""
    data: dict[str, Any] = json.loads((ORACLE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return data


def oracle_params(*names: str, key: str = "cases") -> list[Any]:
    """The cases of each oracle file as pytest params, id ``<file>/<case id>``."""
    params = []
    for name in names:
        for case in load_oracle(name)[key]:
            if not (case.get("source") and case.get("verified_by")):
                raise ValueError(f"{name}: case {case.get('id')!r} needs source and verified_by")
            params.append(pytest.param(case, id=f"{name}/{case['id']}"))
    return params


def decode_cell(raw: Any) -> Any:
    """Oracle JSON to a runtime value.

    JSON number -> float (Excel stores doubles), string -> text, bool -> logical, null -> blank,
    ``{"error": "#N/A"}`` -> ``ExcelError``, ``{"range": [...]}`` -> a range (tuple of cells),
    ``{"range": [...], "columns": n}`` -> a rectangular ``Area`` of n columns (cells row by row).
    """
    from bob_killer.runtime.coercion import ExcelError

    if isinstance(raw, bool) or raw is None or isinstance(raw, str):
        return raw
    if isinstance(raw, int | float):
        return float(raw)
    if isinstance(raw, dict) and set(raw) == {"error"}:
        return ExcelError(raw["error"])
    if isinstance(raw, dict) and set(raw) == {"range"}:
        return tuple(decode_cell(v) for v in raw["range"])
    if isinstance(raw, dict) and set(raw) == {"range", "columns"}:
        from bob_killer.runtime.values import Area

        return Area((decode_cell(v) for v in raw["range"]), columns=raw["columns"])
    raise ValueError(f"cannot decode oracle value {raw!r}")


def make_zip(members: Mapping[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def workbook_like() -> bytes:
    """A small zip shaped like an .xlsx container (content is irrelevant to upload checks)."""
    return make_zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>"})


def bomb(size: int) -> bytes:
    return make_zip({"xl/sharedStrings.xml": bytes(size)})


def sample_run(run_id: str = "r1") -> Run:
    from bob_killer.contracts.base import SCHEMA_VERSION
    from bob_killer.contracts.runs import Run, RunState

    return Run(
        run_id=run_id,
        filename="book.xlsx",
        sha256="ab" * 32,
        state=RunState.QUEUED,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        schema_version=SCHEMA_VERSION,
    )


def queued_run(store: RunRepository) -> Run:
    """A run created through the service layer, with one pending row per registered stage."""
    from bob_killer.contracts.runs import UploadLimits
    from bob_killer.service.runs import create_run

    return create_run(store, "book.xlsx", workbook_like(), UploadLimits())


def _sqlite_store(tmp_path: Path) -> RunRepository:
    from bob_killer.store.db import RunStore

    return RunStore(tmp_path / "runs.db")


def snowflake_tables_session() -> FakeSession:
    """A FakeSession that keeps RUNS and STAGE_STATUS in memory, rows in ``_seq`` order.

    Each script is the start of one SnowflakeRunStore statement; binds follow model field order.
    Rows come back with upper-case column names, as Snowflake returns them.
    """
    from bob_killer.contracts.runs import Run, RunState, StageStatus
    from tests.fakes.snowpark import ROWS_INSERTED, ROWS_UPDATED, FakeSession, Params

    runs: list[dict[str, Any]] = []
    stage_rows: list[dict[str, Any]] = []
    run_cols, stage_cols = tuple(Run.model_fields), tuple(StageStatus.model_fields)
    runs_t, stages_t = Run.table_name.upper(), StageStatus.table_name.upper()

    def bound(p: Params) -> list[Any]:
        return list(p or ())

    def out(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{k.upper(): v for k, v in r.items()} for r in rows]

    def affected(inserted: int = 0, updated: int = 0) -> list[dict[str, Any]]:
        return [{ROWS_INSERTED: inserted, ROWS_UPDATED: updated}]

    def insert_run(p: Params) -> list[dict[str, Any]]:
        runs.append(dict(zip(run_cols, bound(p), strict=True)))
        return affected(inserted=1)

    def get_run(p: Params) -> list[dict[str, Any]]:
        return out([r for r in runs if r["run_id"] == bound(p)[0]])

    def set_state(p: Params) -> list[dict[str, Any]]:
        state, run_id = bound(p)
        hit = [r for r in runs if r["run_id"] == run_id]
        for r in hit:
            r["state"] = state
        return affected(updated=len(hit))

    def claim(p: Params) -> list[dict[str, Any]]:
        (run_id,) = bound(p)
        hit = [r for r in runs if r["run_id"] == run_id and r["state"] == RunState.QUEUED.value]
        for r in hit:
            r["state"] = RunState.RUNNING.value
        return affected(updated=len(hit))

    def merge_stage(p: Params) -> list[dict[str, Any]]:
        new = dict(zip(stage_cols, bound(p), strict=True))
        hit = [r for r in stage_rows if all(r[k] == new[k] for k in StageStatus.primary_key)]
        for r in hit:
            r.update(new)
        if not hit:
            stage_rows.append(new)
        return affected(inserted=0 if hit else 1, updated=len(hit))

    def get_stages(p: Params) -> list[dict[str, Any]]:
        return out([r for r in stage_rows if r["run_id"] == bound(p)[0]])

    session = FakeSession()
    for prefix, handler in {
        f"INSERT INTO {runs_t}": insert_run,
        f"SELECT {', '.join(run_cols)} FROM {runs_t}": get_run,
        f"UPDATE {runs_t} SET state = ?": set_state,
        f"UPDATE {runs_t} SET state = '{RunState.RUNNING.value}'": claim,
        f"MERGE INTO {stages_t}": merge_stage,
        f"SELECT {', '.join(stage_cols)} FROM {stages_t}": get_stages,
    }.items():
        session.script_handler(prefix, handler)
    return session


def _snowflake_store(tmp_path: Path) -> RunRepository:
    from bob_killer.hosts.snowflake.store import SnowflakeRunStore

    return SnowflakeRunStore(snowflake_tables_session())


# One store factory per RunRepository implementation; every test that takes the
# ``store`` fixture (the shared contract suite) runs once on each of them.
STORE_FACTORIES: dict[str, Callable[[Path], RunRepository]] = {
    "sqlite": _sqlite_store,
    "snowflake": _snowflake_store,
}


@pytest.fixture(params=sorted(STORE_FACTORIES))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> RunRepository:
    return STORE_FACTORIES[request.param](tmp_path)
