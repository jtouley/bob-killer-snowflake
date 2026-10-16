"""FastAPI app: job-based runs (SPEC decision 7).

uv run fastapi dev src/bob_killer/api/main.py
"""

from __future__ import annotations

import os
from functools import lru_cache
from http import HTTPStatus
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile

from bob_killer.contracts import SCHEMA_VERSION
from bob_killer.contracts.runs import RunCreated, RunView, UploadLimits
from bob_killer.service.runs import create_run, execute_run
from bob_killer.service.uploads import UploadRejected
from bob_killer.store.db import RunStore

app = FastAPI(title="Bob Killer", version=f"schema-{SCHEMA_VERSION}")


@lru_cache(maxsize=1)
def get_store() -> RunStore:
    return RunStore(Path(os.environ.get("BOB_KILLER_DB", "build/bob_killer.db")))


def get_limits() -> UploadLimits:
    return UploadLimits()


Store = Annotated[RunStore, Depends(get_store)]
Limits = Annotated[UploadLimits, Depends(get_limits)]


@app.post("/runs", status_code=HTTPStatus.ACCEPTED, response_model=RunCreated)
async def post_run(
    workbook: UploadFile, background: BackgroundTasks, store: Store, limits: Limits
) -> RunCreated:
    data = await workbook.read(limits.max_compressed_bytes + 1)
    try:
        run = create_run(store, workbook.filename or "upload", data, limits)
    except UploadRejected as exc:
        raise HTTPException(exc.status, exc.detail) from None
    background.add_task(execute_run, store, run.run_id)
    return RunCreated(run_id=run.run_id, state=run.state)


@app.get("/runs/{run_id}", response_model=RunView)
def get_run(run_id: str, store: Store) -> RunView:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, f"no run {run_id}")
    return RunView(run=run, stages=store.stages(run_id))
