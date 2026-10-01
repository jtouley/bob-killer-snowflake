"""golden.lock: the pinned golden workbook set (never committed; fetched and hash-checked)."""

from __future__ import annotations

from enum import StrEnum

from bob_killer.contracts.base import StrictModel


class GoldenStatus(StrEnum):
    RESOLVED = "resolved"  # direct URL and pinned sha256
    PENDING_HASH = "pending-hash"  # direct URL known, hash not yet accepted
    UNRESOLVED = "unresolved"  # only a landing page is known


class GoldenEntry(StrictModel):
    id: str
    complexity: str
    title: str
    source_page: str
    url: str | None
    filename: str | None
    sha256: str | None
    status: GoldenStatus
    note: str


class GoldenLock(StrictModel):
    lock_version: int
    workbooks: tuple[GoldenEntry, ...]
