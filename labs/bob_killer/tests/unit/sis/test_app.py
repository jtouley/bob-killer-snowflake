"""src/bob_killer_sis/streamlit_app.py through AppTest with an injected FakeSession (Phase 7)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import bob_killer_sis.streamlit_app as sis
from bob_killer.contracts import SCHEMA_VERSION
from bob_killer.contracts.runs import RunCreated, RunRejected, RunState
from tests.conftest import workbook_like
from tests.fakes.snowpark import FakeAsyncJob, FakeSession
from tests.unit.sis.conftest import run_row, stage_row

CORE_SNAPSHOT = (
    Path(__file__).resolve().parents[3]
    / f"src/bob_killer/contracts/snapshots/v{SCHEMA_VERSION}/schemas.json"
)
WORKBOOK = workbook_like()
SHA = hashlib.sha256(WORKBOOK).hexdigest()


def test_schemas_json_is_the_core_snapshot_byte_for_byte() -> None:
    assert sis.SCHEMAS_PATH.read_bytes() == CORE_SNAPSHOT.read_bytes()


def _selected(sql: str) -> list[str]:
    return sql.split("SELECT ", 1)[1].split(" FROM ", 1)[0].split(", ")


@pytest.mark.parametrize(
    ("sql", "schema"),
    [
        (sis.RUN_SQL, sis.RUN),
        (sis.RECENT_SQL, sis.RUN),
        (sis.STAGES_SQL, sis.STAGE),
        (sis.REPORT_SQL, sis.REPORT),
    ],
    ids=["run", "recent", "stages", "report"],
)
def test_every_query_names_the_contract_columns(sql: str, schema: str) -> None:
    assert _selected(sql) == list(sis.SCHEMAS[schema]["properties"])


def test_recent_runs_are_the_last_rows_by_insert_order() -> None:
    assert sis.RECENT_SQL.endswith(f" ORDER BY _seq DESC LIMIT {sis.RECENT_LIMIT}")


def _upload(app: AppTest, filename: str) -> AppTest:
    app.run()
    app.file_uploader[0].set_value((filename, WORKBOOK, "application/octet-stream"))
    app.run()
    app.button[0].click()
    return app.run()


@pytest.mark.parametrize("filename", ["book.xlsx", "macro.xlsm"])
def test_upload_stages_by_sha_then_creates_and_starts_the_run(
    app: AppTest, fake: FakeSession, filename: str
) -> None:
    created = RunCreated(run_id="r1", state=RunState.QUEUED)
    fake.call_results[sis.CREATE_RUN] = json.dumps(created.model_dump(mode="json"))
    fake.call_results[sis.EXECUTE_RUN] = FakeAsyncJob(None, done=False)
    fake.script(sis.RUN_SQL, [run_row(run_id=created.run_id)])
    _upload(app, filename)
    assert not app.exception
    assert fake.file.puts == [
        (f"{sis.UPLOADS}/{SHA}.xlsx", dict(auto_compress=False, overwrite=False))
    ]
    assert fake.file.staged[f"{sis.UPLOADS}/{SHA}.xlsx"] == WORKBOOK
    assert fake.calls == [
        (sis.CREATE_RUN, (f"{SHA}.xlsx", filename, SHA), dict(block=True)),
        (sis.EXECUTE_RUN, (created.run_id,), dict(block=False)),
    ]
    assert (sis.RUN_SQL, (created.run_id,)) in fake.statements
    assert (sis.STAGES_SQL, (created.run_id,)) in fake.statements


def test_upload_previews_the_first_rows_of_each_sheet(app: AppTest, fake: FakeSession) -> None:
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for i in range(sis.PREVIEW_ROWS + 3):
        ws.append([i, f"row {i}"])
    buf = io.BytesIO()
    wb.save(buf)
    app.run()
    app.file_uploader[0].set_value(("book.xlsx", buf.getvalue(), "application/octet-stream"))
    app.run()
    assert not app.exception
    (frame,) = app.dataframe
    assert len(frame.value) == sis.PREVIEW_ROWS
    assert fake.calls == []


def test_rejected_upload_shows_the_detail_and_starts_nothing(
    app: AppTest, fake: FakeSession
) -> None:
    rejected = RunRejected(status=415, detail="not an .xlsx/.xlsm zip container")
    fake.call_results[sis.CREATE_RUN] = json.dumps(rejected.model_dump(mode="json"))
    _upload(app, "book.xlsx")
    assert not app.exception
    assert any(rejected.detail in e.value for e in app.error)
    assert [c[0] for c in fake.calls] == [sis.CREATE_RUN]


def _watch(app: AppTest, fake: FakeSession, state: str, *, done: bool) -> AppTest:
    row = run_row(state=state)
    fake.script(sis.RUN_SQL, [row])
    fake.script(sis.STAGES_SQL, [stage_row(row["RUN_ID"])])
    app.session_state[sis.JOBS_KEY] = {row["RUN_ID"]: FakeAsyncJob(None, done=done)}
    return app.run()


def test_a_row_that_fails_the_json_schema_shows_an_error(app: AppTest, fake: FakeSession) -> None:
    _watch(app, fake, "bogus", done=False)
    assert not app.exception
    assert any(sis.INVALID_ROW in e.value for e in app.error)


def test_a_timestamp_row_passes_after_isoformat(app: AppTest, fake: FakeSession) -> None:
    _watch(app, fake, RunState.RUNNING.value, done=False)
    assert not app.exception
    assert not app.error
    assert any(RunState.RUNNING.value in m.value for m in app.markdown)


def test_a_finished_job_whose_run_is_not_final_shows_the_run_id(
    app: AppTest, fake: FakeSession
) -> None:
    row = run_row()
    _watch(app, fake, row["STATE"], done=True)
    assert any(row["RUN_ID"] in e.value and sis.STUCK in e.value for e in app.error)


def test_a_finished_job_with_a_final_run_shows_no_error(app: AppTest, fake: FakeSession) -> None:
    _watch(app, fake, RunState.SUCCEEDED.value, done=True)
    assert not app.error


def test_recent_runs_lists_the_rows_for_all_users(app: AppTest, fake: FakeSession) -> None:
    rows = [run_row(run_id=f"r{i}") for i in range(3)]
    fake.script(sis.RECENT_SQL, rows)
    app.run()
    assert not app.exception
    assert sis.RECENT_LABEL in [h.value for h in app.subheader]
    shown = " ".join(m.value for m in app.markdown)
    assert all(r["RUN_ID"] in shown for r in rows)
    assert (sis.RECENT_SQL, ()) in fake.statements


# --- RUN_PIPELINE and the equivalence report ------------------------------------------------------


def test_an_upload_starts_the_whole_pipeline() -> None:
    from bob_killer.hosts.snowflake import run_pipeline

    assert sis.EXECUTE_RUN == run_pipeline.NAME


def _report(run_id: str, mismatched: int) -> dict[str, object]:
    """A WB_REPORTS row as Snowpark returns it: upper-case names, the VARIANT as JSON text."""
    from bob_killer.contracts.ir import CellValue
    from bob_killer.contracts.report import CellMismatch, EquivalenceReport, Mismatches

    cells = tuple(
        CellMismatch(
            sheet="S",
            cell_row=n + 1,
            cell_col=n + 1,
            expected=CellValue.number(n),
            actual=CellValue.number(n + 1),
        )
        for n in range(mismatched)
    )
    total = 7
    report = EquivalenceReport(
        run_id=run_id,
        workbook_sha256=SHA,
        denominator=total,
        cells_checked=total,
        cells_matched=total - mismatched,
        mismatches=Mismatches(cells=cells),
        parity_test_failures=mismatched,
        channels_agree=True,
        steps_generated=total,
        steps_total=total,
        unsupported=0,
    )
    row = {k.upper(): v for k, v in report.model_dump(mode="json").items()}
    row["MISMATCHES"] = json.dumps(row["MISMATCHES"], indent=2)
    return row


REPORT_RUN = SHA[: len(SHA) // 2]  # a run id of the contract's form


def _watch_run(app: AppTest, fake: FakeSession, run_id: str) -> AppTest:
    fake.script(sis.RUN_SQL, [run_row(state=RunState.SUCCEEDED.value, run_id=run_id)])
    fake.script(sis.STAGES_SQL, [stage_row(run_id)])
    app.session_state[sis.JOBS_KEY] = {run_id: FakeAsyncJob(None, done=True)}
    return app.run()


@pytest.mark.parametrize("mismatched", [0, 2])
def test_the_report_shows_counts_mismatches_and_the_docs_path(
    app: AppTest, fake: FakeSession, mismatched: int
) -> None:
    run_id = REPORT_RUN
    report = _report(run_id, mismatched)
    fake.script(sis.REPORT_SQL, [report])
    _watch_run(app, fake, run_id)
    assert not app.exception
    assert not app.error
    shown = {m.label: m.value for m in app.metric}
    for key in ("CELLS_MATCHED", "CELLS_CHECKED", "DENOMINATOR"):
        assert str(report[key]) in shown.values(), key
    assert any(sis.DOCS_PATH.format(run_id=run_id) in m.value for m in app.markdown)
    assert len(app.dataframe) == len([None] * bool(mismatched))
    if mismatched:
        (frame,) = app.dataframe
        assert len(frame.value) == mismatched
    assert (sis.REPORT_SQL, (run_id,)) in fake.statements


def test_a_report_row_that_fails_the_json_schema_shows_an_error(
    app: AppTest, fake: FakeSession
) -> None:
    run_id = REPORT_RUN
    report = _report(run_id, 0)
    report["CELLS_CHECKED"] = "every one"
    fake.script(sis.REPORT_SQL, [report])
    _watch_run(app, fake, run_id)
    assert not app.exception
    report_name = sis.REPORT.rsplit(".", 1)[1]
    assert any(sis.INVALID_ROW in e.value and report_name in e.value for e in app.error)
    assert not app.metric
