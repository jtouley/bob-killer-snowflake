"""Shared builders and fixtures for unit and integration tests."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


ORACLE_DIR = Path(__file__).parent / "oracle"


def load_oracle(name: str) -> dict[str, Any]:
    """One ``tests/oracle/<name>.json`` file. Every case in it carries ``source`` and ``verified_by``."""
    data: dict[str, Any] = json.loads((ORACLE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return data


def oracle_params(*names: str, key: str = "cases") -> list[Any]:
    """The cases of each oracle file as pytest params, id ``<file>/<case id>``."""
    params = []
    for name in names:
        for case in load_oracle(name)[key]:
            if not (case.get("source") and case.get("verified_by")):
                raise ValueError(f"{name}: case {case.get('id')!r} needs source and verified_by")
            params.append(pytest.param(case, id=f"{name}/{case['id']}"))
    return params


def decode_cell(raw: Any) -> Any:
    """Oracle JSON to a runtime value.

    JSON number -> float (Excel stores doubles), string -> text, bool -> logical, null -> blank,
    ``{"error": "#N/A"}`` -> ``ExcelError``, ``{"range": [...]}`` -> a range (tuple of cells).
    """
    from bob_killer.runtime.coercion import ExcelError

    if isinstance(raw, bool) or raw is None or isinstance(raw, str):
        return raw
    if isinstance(raw, int | float):
        return float(raw)
    if isinstance(raw, dict) and set(raw) == {"error"}:
        return ExcelError(raw["error"])
    if isinstance(raw, dict) and set(raw) == {"range"}:
        return tuple(decode_cell(v) for v in raw["range"])
    raise ValueError(f"cannot decode oracle value {raw!r}")


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
