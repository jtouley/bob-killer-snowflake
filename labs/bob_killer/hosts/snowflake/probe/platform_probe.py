"""Platform probe procedure (docs/SPEC.md §4 F2, F5, F6). A throwaway check, not a deploy path.

``platform_probe(session, stage_path)`` imports the core contracts, builds a ``Run``, and returns
the Python version, the current schema, and the SHA-256 of the staged file read with
``session.file.get_stream``.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime
from typing import Any

from bob_killer.contracts import SCHEMA_VERSION
from bob_killer.contracts.runs import Run, RunState


def platform_probe(session: Any, stage_path: str) -> dict[str, Any]:
    run = Run(
        run_id="probe",
        filename="probe.xlsx",
        sha256="0" * 64,
        state=RunState.QUEUED,
        created_at=datetime.now(UTC),
        schema_version=SCHEMA_VERSION,
    )
    (row,) = session.sql("SELECT CURRENT_SCHEMA()").collect()
    data = session.file.get_stream(stage_path).read() if stage_path else b""
    return {
        "sys_version": sys.version,
        "run_state": run.state.value,
        "current_schema": row[0],
        "sha256": hashlib.sha256(data).hexdigest(),
    }
