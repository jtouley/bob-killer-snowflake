"""Shared builders and fixtures for unit and integration tests."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from bob_killer.contracts.runs import Run
    from bob_killer.store import RunRepository


@pytest.fixture(autouse=True)
def _empty_stages() -> Iterator[None]:
    """Each test starts from the empty core stage baseline; entries come back after it (G1)."""
    from bob_killer import registry

    with registry.stages.snapshot():
        registry.stages.clear()
        yield


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


def queued_run(store: RunRepository) -> Run:
    """A run created through the service layer, with one pending row per registered stage."""
    from bob_killer.contracts.runs import UploadLimits
    from bob_killer.service.runs import create_run

    return create_run(store, "book.xlsx", workbook_like(), UploadLimits())


def _sqlite_store(tmp_path: Path) -> RunRepository:
    from bob_killer.store.db import RunStore

    return RunStore(tmp_path / "runs.db")


# One store factory per RunRepository implementation; every test that takes the
# ``store`` fixture (the shared contract suite) runs once on each of them.
STORE_FACTORIES: dict[str, Callable[[Path], RunRepository]] = {
    "sqlite": _sqlite_store,
}


@pytest.fixture(params=sorted(STORE_FACTORIES))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> RunRepository:
    return STORE_FACTORIES[request.param](tmp_path)
