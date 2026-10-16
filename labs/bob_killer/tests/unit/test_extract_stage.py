"""The extract stage: the Raw layer of workbook.db, written once, and its registration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bob_killer import registry
from bob_killer.contracts.raw import RAW_TABLES
from bob_killer.contracts.runs import RunState, StageState, UploadLimits
from bob_killer.extract import extract_workbook
from bob_killer.extract.raw_db import RawLayerWritten, read_raw, write_raw
from bob_killer.extract.stage import STAGE, bind_inputs, register_stages
from bob_killer.service.runs import create_run, execute_run
from bob_killer.store.db import RunStore
from tests.unit.conftest import FEATURES, build_structure, build_with_feature


@pytest.fixture
def stages(monkeypatch: pytest.MonkeyPatch) -> registry.Registry[registry.Stage]:
    """A private stage registry, so no test leaks a stage into the shared pipeline."""
    fresh: registry.Registry[registry.Stage] = registry.Registry("stages")
    monkeypatch.setattr(registry, "stages", fresh)
    return fresh


def _books() -> list[bytes]:
    return [build_structure(), *(build_with_feature(kind)[0] for kind in sorted(FEATURES))]


@pytest.mark.parametrize("data", _books())
def test_raw_layer_round_trips(tmp_path: Path, data: bytes) -> None:
    raw = extract_workbook(data)
    write_raw(tmp_path / "workbook.db", raw)
    assert read_raw(tmp_path / "workbook.db") == raw


def test_raw_tables_follow_the_contracts(tmp_path: Path) -> None:
    write_raw(tmp_path / "workbook.db", extract_workbook(build_structure()))
    conn = sqlite3.connect(tmp_path / "workbook.db")
    for model in RAW_TABLES:
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({model.table_name})")]
        assert cols == list(model.model_fields), model.table_name


def test_raw_layer_is_written_once(tmp_path: Path) -> None:
    raw = extract_workbook(build_structure())
    write_raw(tmp_path / "workbook.db", raw)
    with pytest.raises(RawLayerWritten):
        write_raw(tmp_path / "workbook.db", raw)
    assert read_raw(tmp_path / "workbook.db") == raw


def test_importing_extract_registers_no_stage() -> None:
    import bob_killer.extract.stage  # noqa: F401

    assert STAGE not in registry.stages


def test_register_stages_is_idempotent(stages: registry.Registry[registry.Stage]) -> None:
    register_stages()
    register_stages()
    assert stages.names() == (STAGE,)


def test_extract_stage_runs_inside_execute_run(
    tmp_path: Path, stages: registry.Registry[registry.Stage]
) -> None:
    register_stages()
    store = RunStore(tmp_path / "runs.db")
    data = build_structure()
    run = create_run(store, "book.xlsx", data, UploadLimits())
    db_path = tmp_path / run.run_id / "workbook.db"
    with bind_inputs(read_workbook=lambda run_id: data, raw_db=lambda run_id: db_path):
        state = execute_run(store, run.run_id)
    assert state is RunState.SUCCEEDED
    assert [(s.stage, s.state) for s in store.stages(run.run_id)] == [(STAGE, StageState.SUCCEEDED)]
    assert read_raw(db_path) == extract_workbook(data)


def test_extract_stage_without_inputs_fails_the_run(
    tmp_path: Path, stages: registry.Registry[registry.Stage]
) -> None:
    register_stages()
    store = RunStore(tmp_path / "runs.db")
    run = create_run(store, "book.xlsx", build_structure(), UploadLimits())
    assert execute_run(store, run.run_id) is RunState.FAILED
    (status,) = store.stages(run.run_id)
    assert status.state is StageState.FAILED
    assert bind_inputs.__name__ in status.detail
