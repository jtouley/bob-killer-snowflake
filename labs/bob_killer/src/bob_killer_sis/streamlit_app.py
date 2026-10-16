"""Bob Killer upload app for Streamlit in Snowflake (container runtime, Python 3.11; §5.2).

It never imports bob_killer. Every row it reads is checked against schemas.json, the copy of
the core JSON Schema snapshot (D8). Every query names its columns (G7).
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import date, datetime
from itertools import islice
from pathlib import Path
from typing import Any

import jsonschema
import openpyxl
import streamlit as st

SCHEMAS_PATH = Path(__file__).with_name("schemas.json")
SCHEMAS: dict[str, Any] = json.loads(SCHEMAS_PATH.read_text(encoding="utf-8"))

RUN = "bob_killer.contracts.runs.Run"
STAGE = "bob_killer.contracts.runs.StageStatus"
CREATED = "bob_killer.contracts.runs.RunCreated"
REJECTED = "bob_killer.contracts.runs.RunRejected"

UPLOADS = "@UPLOADS"
CREATE_RUN = "CREATE_RUN"
EXECUTE_RUN = "EXECUTE_RUN"
SESSION_KEY = "snowpark_session"
JOBS_KEY = "jobs"
PREVIEW_ROWS = 5
RECENT_LIMIT = 20
RECENT_LABEL = "recent runs"
POLL_SECONDS = 2
FINAL_STATES = ("succeeded", "failed")
INVALID_ROW = "row does not match the contract"
STUCK = "the run job ended but the run state is not final"


def columns(schema: str) -> str:
    return ", ".join(SCHEMAS[schema]["properties"])


RUN_SQL = f"SELECT {columns(RUN)} FROM RUNS WHERE run_id = ?"
STAGES_SQL = f"SELECT {columns(STAGE)} FROM STAGE_STATUS WHERE run_id = ? ORDER BY _seq"
RECENT_SQL = f"SELECT {columns(RUN)} FROM RUNS ORDER BY _seq DESC LIMIT {RECENT_LIMIT}"


def session() -> Any:
    """The Snowpark session; tests inject a fake under SESSION_KEY."""
    if SESSION_KEY not in st.session_state:
        from snowflake.snowpark.context import get_active_session

        st.session_state[SESSION_KEY] = get_active_session()
    return st.session_state[SESSION_KEY]


def _json_value(value: object) -> object:
    return value.isoformat() if isinstance(value, datetime | date) else value


def checked(schema: str, row: dict[str, Any]) -> dict[str, Any] | None:
    """The row with lowercased keys and ISO datetimes, or None (and an error) if invalid."""
    doc = {k.lower(): _json_value(v) for k, v in row.items()}
    errors = list(jsonschema.Draft202012Validator(SCHEMAS[schema]).iter_errors(doc))
    if errors:
        st.error(f"{INVALID_ROW} ({schema.rsplit('.', 1)[1]}): {errors[0].message}")
        return None
    return doc


def query(schema: str, sql: str, *params: object) -> list[dict[str, Any]]:
    rows = session().sql(sql, params=list(params)).collect()
    return [doc for doc in (checked(schema, r.as_dict()) for r in rows) if doc is not None]


def preview(data: bytes) -> None:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # the procedure decides acceptance; the preview only informs
        st.warning(f"no preview: {exc}")
        return
    for ws in wb.worksheets:
        rows = [list(r) for r in islice(ws.iter_rows(values_only=True), PREVIEW_ROWS)]
        st.caption(ws.title)
        st.dataframe(rows)
    wb.close()


def submit(filename: str, data: bytes) -> None:
    sha = hashlib.sha256(data).hexdigest()
    s = session()
    s.file.put_stream(
        io.BytesIO(data), f"{UPLOADS}/{sha}.xlsx", auto_compress=False, overwrite=False
    )
    raw = s.call(CREATE_RUN, f"{sha}.xlsx", filename, sha)
    result = json.loads(raw) if isinstance(raw, str) else raw
    if "status" in result:
        doc = checked(REJECTED, result)
        if doc is not None:
            st.error(f"{filename} rejected ({doc['status']}): {doc['detail']}")
        return
    doc = checked(CREATED, result)
    if doc is None:
        return
    job = s.call(EXECUTE_RUN, doc["run_id"], block=False)
    st.session_state.setdefault(JOBS_KEY, {})[doc["run_id"]] = job


def show_run(run_id: str, job: Any) -> None:
    runs = query(RUN, RUN_SQL, run_id)
    stages = query(STAGE, STAGES_SQL, run_id)
    for run in runs:
        st.markdown(f"**{run['filename']}** `{run['run_id']}`: {run['state']}")
        for stage in stages:
            st.markdown(f"- {stage['stage']}: {stage['state']} {stage['detail']}")
        if job.is_done() and run["state"] not in FINAL_STATES:
            st.error(f"{STUCK}: run {run_id}")


@st.fragment(run_every=POLL_SECONDS)
def watch() -> None:
    for run_id, job in st.session_state.get(JOBS_KEY, {}).items():
        show_run(run_id, job)


def recent() -> None:
    st.subheader(RECENT_LABEL)
    for run in query(RUN, RECENT_SQL):
        st.markdown(f"`{run['run_id']}` {run['filename']}: {run['state']} ({run['created_at']})")


def main() -> None:
    st.title("Bob Killer")
    files = st.file_uploader("Workbooks", type=["xlsx", "xlsm"], accept_multiple_files=True)
    uploads = [(f.name, f.getvalue()) for f in files or []]
    for name, data in uploads:
        st.subheader(name)
        preview(data)
    if uploads and st.button("Start runs"):
        for name, data in uploads:
            submit(name, data)
    watch()
    recent()


if __name__ == "__main__":
    main()
