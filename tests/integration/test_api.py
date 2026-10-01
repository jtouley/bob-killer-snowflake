"""POST /runs and GET /runs/{id} on an empty pipeline (SPEC decision 7)."""

from __future__ import annotations

from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bob_killer.api.main import app, get_limits, get_store
from bob_killer.contracts.runs import RunState, UploadLimits
from bob_killer.store.db import RunStore
from tests.conftest import bomb, workbook_like

LIMITS = UploadLimits(
    max_compressed_bytes=64_000, max_decompressed_bytes=1_000_000, max_members=10, max_ratio=50
)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    store = RunStore(tmp_path / "api.db")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_limits] = lambda: LIMITS
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_post_run_accepted_then_succeeds_on_empty_pipeline(client: TestClient) -> None:
    resp = client.post("/runs", files={"workbook": ("book.xlsx", workbook_like())})
    assert resp.status_code == HTTPStatus.ACCEPTED
    run_id = resp.json()["run_id"]
    view = client.get(f"/runs/{run_id}")
    assert view.status_code == HTTPStatus.OK
    assert view.json()["run"]["state"] == RunState.SUCCEEDED
    assert view.json()["stages"] == []


def test_unknown_run_is_404(client: TestClient) -> None:
    assert client.get("/runs/missing").status_code == HTTPStatus.NOT_FOUND


def test_zip_bomb_is_413(client: TestClient) -> None:
    resp = client.post("/runs", files={"workbook": ("book.xlsx", bomb(900_000))})
    assert resp.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_non_zip_is_415(client: TestClient) -> None:
    resp = client.post("/runs", files={"workbook": ("book.xls", b"\xd0\xcf\x11\xe0legacy")})
    assert resp.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
