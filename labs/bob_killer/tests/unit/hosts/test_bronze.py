"""hosts/snowflake/bronze.py: rows_from_workbook, BronzeWriter and the land_bronze stage (Phase 5).

Expected rows come from ``tests/oracle/bronze_basic.json``; the fixture comes from
``tests/fixtures/make_bronze_fixtures.py``.
"""

from __future__ import annotations

import io
import json
import math
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from bob_killer import registry
from bob_killer.contracts.bronze import BronzeRow, LandedFile
from bob_killer.hosts.snowflake.bronze import (
    ALREADY_LANDED,
    LANDED,
    PARSE_JSON,
    STAGE_NAME,
    BronzeContext,
    BronzeWriter,
    landing_context,
    register_stages,
    rows_from_workbook,
)
from bob_killer.hosts.snowflake.store import SnowflakeRunStore
from tests.conftest import load_oracle, sample_run, snowflake_tables_session
from tests.fakes.snowpark import FakeSession
from tests.fixtures.make_bronze_fixtures import EMPTY_SHEET, FIXTURES, WORKBOOKS, write

ORACLE = load_oracle("bronze_basic")
SHA = "cd" * 32
RUN_ID = "r1"
BATCH = 2


def _fixture_bytes() -> bytes:
    return (WORKBOOKS / ORACLE["fixture"]).read_bytes()


def _cell_xml(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {
            n: zf.read(n)
            for n in zf.namelist()
            if n.startswith("xl/worksheets/") or n == "xl/sharedStrings.xml"
        }


def _expected_rows(sha: str = SHA, run_id: str = RUN_ID) -> tuple[BronzeRow, ...]:
    return tuple(
        BronzeRow.model_validate_json(json.dumps({**r, "file_sha256": sha, "run_id": run_id}))
        for r in ORACLE["rows"]
    )


def _json(rows: Sequence[BronzeRow]) -> list[str]:
    return [r.model_dump_json() for r in rows]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_fixture_script_regenerates_the_committed_cell_xml(name: str, tmp_path: Path) -> None:
    committed = (WORKBOOKS / f"{name}.xlsx").read_bytes()
    assert _cell_xml(write(name, tmp_path).read_bytes()) == _cell_xml(committed)


def test_rows_from_workbook_match_the_oracle_exactly() -> None:
    rows = rows_from_workbook(_fixture_bytes(), file_sha256=SHA, run_id=RUN_ID)
    assert _json(rows) == _json(_expected_rows())
    assert len(rows) == ORACLE["row_count"]
    assert not [r for r in rows if r.sheet == EMPTY_SHEET]


def _landed(size: int = len(b"bytes")) -> LandedFile:
    return LandedFile(
        file_sha256=SHA,
        filename="book.xlsx",
        stage_file=f"{SHA}.xlsx",
        size_bytes=size,
        first_run_id=RUN_ID,
    )


def _session(inserted: int) -> FakeSession:
    session = FakeSession()
    session.script_affected("MERGE", inserted=inserted)
    return session


def _kinds(session: FakeSession) -> list[str]:
    return [q.split()[0] for q in session.sql_texts]


def _expected_kinds(batches: int, end: str) -> list[str]:
    return ["BEGIN", "MERGE", *["INSERT"] * batches, end]


def _batch_rows(session: FakeSession) -> list[tuple[Any, ...]]:
    insert = f"INSERT INTO {BronzeRow.table_name.upper()}"
    params = [list(p or ()) for q, p in session.statements if q.startswith(insert)]
    flat = [v for p in params for v in p]
    width = len(BronzeRow.model_fields)
    return [tuple(flat[i : i + width]) for i in range(0, len(flat), width)]


def test_land_runs_begin_merge_hook_batches_commit_with_bound_values() -> None:
    session, hook_at = _session(inserted=1), []
    rows = _expected_rows()
    result = BronzeWriter(session, batch_size=BATCH).land(
        _landed(), rows, after_claim=lambda: hook_at.append(len(session.statements))
    )
    kinds = _kinds(session)
    assert result == LANDED
    assert kinds == _expected_kinds(math.ceil(len(rows) / BATCH), "COMMIT")
    assert hook_at == [kinds.index("MERGE") + 1]
    merge_sql, merge_params = session.statements[kinds.index("MERGE")]
    assert merge_sql.startswith(f"MERGE INTO {LandedFile.table_name.upper()}")
    assert tuple(merge_params or ()) == tuple(_landed().model_dump(mode="json").values())
    assert _batch_rows(session) == [
        (r.file_sha256, r.sheet, r.row_number, r.run_id, r.payload.model_dump_json()) for r in rows
    ]
    assert all(f"{PARSE_JSON}(" in q for q in session.sql_texts if q.startswith("INSERT"))
    assert not any(SHA in q for q in session.sql_texts)


def test_a_merge_that_inserts_nothing_is_already_landed_with_no_batch() -> None:
    session, hook_at = _session(inserted=0), []
    result = BronzeWriter(session, batch_size=BATCH).land(
        _landed(), _expected_rows(), after_claim=lambda: hook_at.append(len(session.statements))
    )
    assert result == ALREADY_LANDED
    assert _kinds(session) == _expected_kinds(0, "COMMIT")
    assert not hook_at


def test_an_error_in_a_batch_rolls_back_and_raises() -> None:
    session, calls = _session(inserted=1), []

    def fail_second(params: Sequence[Any] | None) -> list[dict[str, Any]]:
        calls.append(params)
        if len(calls) > 1:
            raise RuntimeError("batch failed")
        return []

    session.script_handler("INSERT", fail_second)
    with pytest.raises(RuntimeError):
        BronzeWriter(session, batch_size=BATCH).land(_landed(), _expected_rows())
    assert _kinds(session) == _expected_kinds(len(calls), "ROLLBACK")


def test_register_stages_is_idempotent_and_land_bronze_is_the_first_stage() -> None:
    register_stages()
    register_stages()
    assert registry.stages.names() == (STAGE_NAME,)


def test_land_bronze_lands_the_staged_file_of_the_run() -> None:
    session = snowflake_tables_session()
    session.script_affected(f"MERGE INTO {LandedFile.table_name.upper()}", inserted=1)
    run = sample_run()
    SnowflakeRunStore(session).insert_run(run)
    read: list[str] = []

    def reader(stage_file: str) -> bytes:
        read.append(stage_file)
        return _fixture_bytes()

    register_stages()
    with landing_context(BronzeContext(session=session, read_file=reader, batch_size=BATCH)):
        detail = registry.stages.get(STAGE_NAME)(run.run_id)
    assert detail == LANDED
    assert read == [f"{run.sha256}.xlsx"]
    merge = next(p for q, p in session.statements if q.startswith("MERGE"))
    landed = LandedFile(
        file_sha256=run.sha256,
        filename=run.filename,
        stage_file=f"{run.sha256}.xlsx",
        size_bytes=len(_fixture_bytes()),
        first_run_id=run.run_id,
    )
    assert tuple(merge or ()) == tuple(landed.model_dump(mode="json").values())
    assert len(_batch_rows(session)) == ORACLE["row_count"]


def test_land_bronze_on_a_missing_run_raises_key_error() -> None:
    session = snowflake_tables_session()
    with (
        landing_context(BronzeContext(session=session, read_file=lambda _: b"", batch_size=BATCH)),
        pytest.raises(KeyError),
    ):
        register_stages()
        registry.stages.get(STAGE_NAME)(sample_run().run_id)
