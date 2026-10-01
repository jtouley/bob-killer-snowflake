"""Shared builders for unit and integration tests."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob_killer.contracts.runs import Run


def make_zip(members: Mapping[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def workbook_like() -> bytes:
    """A small zip shaped like an .xlsx container (content is irrelevant to upload checks)."""
    return make_zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>"})


def bomb(size: int) -> bytes:
    return make_zip({"xl/sharedStrings.xml": bytes(size)})


def sample_run(run_id: str = "r1") -> Run:
    from bob_killer.contracts.base import SCHEMA_VERSION
    from bob_killer.contracts.runs import Run, RunState

    return Run(
        run_id=run_id,
        filename="book.xlsx",
        sha256="ab" * 32,
        state=RunState.QUEUED,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        schema_version=SCHEMA_VERSION,
    )
