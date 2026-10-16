"""Create and execute runs. Stages come from ``registry.stages``; an empty pipeline succeeds."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from bob_killer import registry
from bob_killer.contracts import SCHEMA_VERSION
from bob_killer.contracts.runs import Run, RunState, StageState, StageStatus, UploadLimits
from bob_killer.service.uploads import inspect_upload
from bob_killer.store.db import RunStore


def _status(run_id: str, stage: str, state: StageState, detail: str = "") -> StageStatus:
    return StageStatus(run_id=run_id, stage=stage, state=state, detail=detail)


def create_run(store: RunStore, filename: str, data: bytes, limits: UploadLimits) -> Run:
    inspect_upload(data, limits)
    run = Run(
        run_id=uuid.uuid4().hex,
        filename=filename,
        sha256=hashlib.sha256(data).hexdigest(),
        state=RunState.QUEUED,
        created_at=datetime.now(UTC),
        schema_version=SCHEMA_VERSION,
    )
    store.insert_run(run)
    for name in registry.stages.names():
        store.upsert_stage(_status(run.run_id, name, StageState.PENDING))
    return run


def execute_run(store: RunStore, run_id: str) -> RunState:
    store.set_state(run_id, RunState.RUNNING)
    final = RunState.SUCCEEDED
    for name, stage in registry.stages.items():
        store.upsert_stage(_status(run_id, name, StageState.RUNNING))
        try:
            stage(run_id)
        except Exception as exc:  # recorded on the stage, never swallowed silently
            store.upsert_stage(_status(run_id, name, StageState.FAILED, repr(exc)))
            final = RunState.FAILED
            break
        store.upsert_stage(_status(run_id, name, StageState.SUCCEEDED))
    store.set_state(run_id, final)
    return final
