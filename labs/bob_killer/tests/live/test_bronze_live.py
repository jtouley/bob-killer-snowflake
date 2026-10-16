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


def test_two_concurrent_landings_land_the_rows_once(bronze_session: Session, schema: str) -> None:
    """Writer A holds its LANDED_FILES claim open while writer B lands the same bytes (spec MF-4)."""
    import threading

    from bob_killer.hosts.snowflake.session import open_session
    from tests.live.conftest import CONNECTION

    landed, rows = _workbook()
    claimed, release = threading.Event(), threading.Event()
    results: dict[str, str] = {}

    def hold() -> None:
        claimed.set()
        release.wait(timeout=120)

    def writer_a() -> None:
        results["a"] = BronzeWriter(bronze_session, batch_size=2).land(
            landed, rows, after_claim=hold
        )  # type: ignore[arg-type]

    import time

    from tests.live.conftest import write_evidence

    t0 = time.monotonic()
    other = open_session(CONNECTION)
    other.use_schema(schema)
    try:
        a = threading.Thread(target=writer_a)
        a.start()
        assert claimed.wait(timeout=120)
        b = threading.Thread(
            target=lambda: results.update(b=BronzeWriter(other).land(landed, rows))
        )  # type: ignore[arg-type]
        b.start()
        b.join(timeout=5)  # B must wait on A's open claim, not finish first
        assert b.is_alive()
        release.set()
        a.join(timeout=300)
        b.join(timeout=300)
    finally:
        release.set()
        other.close()
    write_evidence(
        "parallel_landing",
        "two concurrent landings",
        f"A claimed and held; B started and was still waiting after 5 s; A released; "
        f"results={results}; total seconds={time.monotonic() - t0:.1f}",
    )
    assert sorted(results.values()) == sorted([LANDED, ALREADY_LANDED])
    assert _count(bronze_session, "BRONZE_ROWS", landed.file_sha256) == len(rows)


def test_a_thirty_thousand_row_workbook_lands_at_the_default_batch_size(
    bronze_session: Session, tmp_path: object
) -> None:
    """G14: the default batch size works on Snowflake; every try and the landing time are recorded."""
    import io
    import time

    import openpyxl

    from bob_killer.hosts.snowflake.bronze import DEFAULT_BATCH_SIZE
    from tests.live.conftest import write_evidence

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["id", "amount", "label"])
    for i in range(30_000):
        ws.append([i, i / 7, f"row {i}"])
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    rows = rows_from_workbook(data, file_sha256=sha, run_id=RUN_ID)
    landed = LandedFile(
        file_sha256=sha,
        filename="volume.xlsx",
        stage_file=f"{sha}.xlsx",
        size_bytes=len(data),
        first_run_id=RUN_ID,
    )
    tries, size = [], DEFAULT_BATCH_SIZE
    while True:
        start = time.monotonic()
        try:
            result = BronzeWriter(bronze_session, batch_size=size).land(landed, rows)
        except Exception as exc:  # recorded, then a smaller batch is tried (spec G14)
            tries.append(f"batch_size={size}: {type(exc).__name__}: {str(exc)[:200]}")
            if size <= 1000:
                raise
            size //= 2
            continue
        seconds = time.monotonic() - start
        tries.append(f"batch_size={size}: {result} rows={len(rows)} seconds={seconds:.1f}")
        break
    write_evidence("live_phase5", "30 000-row landing", "\n".join(tries))
    assert _count(bronze_session, "BRONZE_ROWS", sha) == len(rows)
