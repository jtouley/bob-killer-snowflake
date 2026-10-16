"""Run and stage records, the API payloads around them, and upload limits."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from bob_killer.contracts.base import StrictModel


class RunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StageState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class Run(StrictModel):
    table_name = "runs"
    primary_key = ("run_id",)

    run_id: str
    filename: str
    sha256: str
    state: RunState
    created_at: datetime
    schema_version: int


class StageStatus(StrictModel):
    table_name = "stage_status"
    primary_key = ("run_id", "stage")

    run_id: str
    stage: str
    state: StageState
    detail: str


class RunCreated(StrictModel):
    run_id: str
    state: RunState


class RunView(StrictModel):
    run: Run
    stages: tuple[StageStatus, ...]


class UploadLimits(StrictModel):
    """Checked against the zip central directory before anything is decompressed."""

    max_compressed_bytes: int = 50 * 1024 * 1024
    max_decompressed_bytes: int = 500 * 1024 * 1024
    max_members: int = 10_000
    max_ratio: int = 100
