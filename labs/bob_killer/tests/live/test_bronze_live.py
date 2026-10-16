"""Bronze landing, live on Snowflake (host Phase 5 exit): once, idempotent, all-or-nothing."""

from __future__ import annotations

import hashlib

import pytest
from snowflake.snowpark import Session

from bob_killer.contracts.bronze import LandedFile
from bob_killer.hosts.snowflake.bronze import (
    ALREADY_LANDED,
    LANDED,
    BronzeWriter,
    rows_from_workbook,
)
from tests.fixtures.make_bronze_fixtures import WORKBOOKS

RUN_ID = "live-bronze-run"


def _workbook() -> tuple[LandedFile, tuple[object, ...]]:
    data = (WORKBOOKS / "bronze_basic.xlsx").read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    rows = rows_from_workbook(data, file_sha256=sha, run_id=RUN_ID)
    landed = LandedFile(
        file_sha256=sha,
        filename="bronze_basic.xlsx",
        stage_file=f"{sha}.xlsx",
        size_bytes=len(data),
        first_run_id=RUN_ID,
    )
    return landed, rows


def _count(session: Session, table: str, sha: str) -> int:
    (row,) = session.sql(f"SELECT COUNT(*) FROM {table} WHERE FILE_SHA256 = ?", [sha]).collect()
    return int(row[0])


def test_first_landing_writes_every_row_and_a_second_writes_none(bronze_session: Session) -> None:
    landed, rows = _workbook()
    writer = BronzeWriter(bronze_session, batch_size=2)
    assert writer.land(landed, rows) == LANDED  # type: ignore[arg-type]
    assert _count(bronze_session, "BRONZE_ROWS", landed.file_sha256) == len(rows)
    assert writer.land(landed, rows) == ALREADY_LANDED  # type: ignore[arg-type]
    assert _count(bronze_session, "BRONZE_ROWS", landed.file_sha256) == len(rows)
    assert _count(bronze_session, "LANDED_FILES", landed.file_sha256) == len([landed])


def test_a_failure_after_the_claim_leaves_no_rows(bronze_session: Session) -> None:
    landed, rows = _workbook()

    def fail() -> None:
        raise RuntimeError("injected failure after the LANDED_FILES claim")

    with pytest.raises(RuntimeError, match="injected"):
        BronzeWriter(bronze_session, batch_size=2).land(landed, rows, after_claim=fail)  # type: ignore[arg-type]
    assert _count(bronze_session, "BRONZE_ROWS", landed.file_sha256) == len(())
    assert _count(bronze_session, "LANDED_FILES", landed.file_sha256) == len(())
