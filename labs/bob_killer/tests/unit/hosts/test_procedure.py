"""hosts/snowflake/procedure.py: CREATE_RUN and EXECUTE_RUN handlers (docs/SPEC.md §5.2, Phase 6)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from http import HTTPStatus
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from bob_killer import registry
from bob_killer.contracts import SCHEMA_VERSION
from bob_killer.contracts.bronze import BronzeRow, LandedFile
from bob_killer.contracts.runs import (
    Run,
    RunCreated,
    RunRejected,
    RunState,
    RunView,
    StageState,
    UploadLimits,
)
from bob_killer.hosts.snowflake import bronze, procedure
from bob_killer.hosts.snowflake.store import SnowflakeRunStore
from bob_killer.service.uploads import UploadRejected, inspect_upload
from bob_killer.store.db import RunStore
from tests.conftest import bomb, load_oracle, snowflake_tables_session, workbook_like
from tests.fakes.snowpark import FakeSession
from tests.fixtures.make_bronze_fixtures import WORKBOOKS

SNAPSHOT = (
    Path(procedure.__file__).resolve().parents[2]
    / f"contracts/snapshots/v{SCHEMA_VERSION}/schemas.json"
)
SCHEMAS: dict[str, Any] = json.loads(SNAPSHOT.read_text(encoding="utf-8"))


class Recording:
    """Delegates to a real store and logs each method name; ``fail`` names one that raises."""

    def __init__(self, inner: RunStore, fail: str | None = None) -> None:
        self.inner, self.fail, self.log = inner, fail, list[str]()

    def __getattr__(self, name: str) -> Any:
        real = getattr(self.inner, name)

        def call(*args: Any) -> Any:
            self.log.append(name)
            if name == self.fail:
                raise RuntimeError(name)
            return real(*args)

        return call


class Lander:
    def __init__(self) -> None:
        self.calls: list[tuple[LandedFile, bytes]] = []

    def __call__(self, session: object, landed: LandedFile, data: bytes) -> str:
        self.calls.append((landed, data))
        return f"landed {landed.file_sha256}"


class World:
    def __init__(self, tmp_path: Path) -> None:
        self.session = FakeSession()
        self.plain = RunStore(tmp_path / "runs.db")
        self.store = Recording(self.plain)
        self.land = Lander()

    def host(self, session: object) -> procedure.Host:
        assert session is self.session
        return procedure.Host(session=session, store=self.store, land=self.land)

    def stage(self, data: bytes, sha256: str | None = None) -> str:
        sha = sha256 or hashlib.sha256(data).hexdigest()
        self.session.file.staged[procedure.staged_path(sha)] = data
        return sha

    def create(self, sha256: str, stage_file: str | None = None) -> RunCreated | RunRejected:
        return procedure.create_run_handler(
            self.session,
            f"{sha256}.xlsx" if stage_file is None else stage_file,
            "book.xlsx",
            sha256,
            host_factory=self.host,
        )

    def execute(self, run_id: str) -> RunView:
        return procedure.execute_run_handler(self.session, run_id, host_factory=self.host)

    def created(self, data: bytes) -> RunCreated:
        result = self.create(self.stage(data))
        assert isinstance(result, RunCreated)
        return result

    def removes(self) -> list[tuple[str, tuple[object, ...]]]:
        return [s for s in self.session.statements if s[0].upper().startswith("REMOVE")]


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


@pytest.fixture
def registered() -> Iterator[None]:
    procedure.register_stages()
    yield


WORKBOOK = workbook_like()  # zip timestamps vary per build, so build it once
GOOD_SHA = hashlib.sha256(WORKBOOK).hexdigest()
INSERT_RUN, GET_RUN, CLAIM_RUN, SET_STATE, STAGES = (
    m.__name__
    for m in (
        RunStore.insert_run,
        RunStore.get_run,
        RunStore.claim_run,
        RunStore.set_state,
        RunStore.stages,
    )
)


@pytest.mark.parametrize(
    ("sha256", "stage_file"),
    [
        (GOOD_SHA.upper(), None),
        (GOOD_SHA[:-1], None),
        (GOOD_SHA + "0", None),
        ("../" + GOOD_SHA[3:], None),
        (GOOD_SHA, "other.xlsx"),
        (GOOD_SHA, f"{GOOD_SHA}.xlsm"),
        (GOOD_SHA, f"../{GOOD_SHA}.xlsx"),
    ],
    ids=["upper", "short", "long", "traversal", "other-file", "xlsm", "path"],
)
def test_bad_sha_or_stage_file_is_rejected_and_reads_nothing(
    world: World, sha256: str, stage_file: str | None
) -> None:
    world.stage(WORKBOOK)
    result = world.create(sha256, stage_file)
    assert isinstance(result, RunRejected)
    assert result.status == HTTPStatus.BAD_REQUEST
    assert world.session.statements == []
    assert world.session.file.reads == []
    assert world.store.log == []


def test_sha_mismatch_is_rejected_and_the_staged_file_removed(world: World) -> None:
    claimed = hashlib.sha256(b"other bytes").hexdigest()
    world.stage(WORKBOOK, claimed)
    result = world.create(claimed)
    assert result == RunRejected(status=HTTPStatus.BAD_REQUEST, detail=procedure.SHA_MISMATCH)
    assert world.removes() == [(procedure.REMOVE_SQL, (procedure.staged_path(claimed),))]
    assert procedure.REMOVE_SQL.count("?") == len(world.removes()[0][1])
    assert world.session.file.staged == {}
    assert INSERT_RUN not in world.store.log


def _too_large() -> bytes:
    return bytes(UploadLimits().max_compressed_bytes + 1)


@pytest.mark.parametrize(
    "make",
    [lambda: bomb(UploadLimits().max_decompressed_bytes + 1), lambda: b"not a zip", _too_large],
    ids=["zip-bomb", "xls", "51mb"],
)
def test_upload_rejected_maps_to_run_rejected_and_removes_the_file(
    world: World, make: Callable[[], bytes]
) -> None:
    data = make()
    with pytest.raises(UploadRejected) as expected:
        inspect_upload(data, UploadLimits())
    sha = world.stage(data)
    result = world.create(sha)
    assert result == RunRejected(status=expected.value.status, detail=expected.value.detail)
    assert world.removes() == [(procedure.REMOVE_SQL, (procedure.staged_path(sha),))]
    assert world.session.file.staged == {}
    assert INSERT_RUN not in world.store.log


def test_accepted_upload_creates_a_queued_run_and_keeps_the_file(world: World) -> None:
    created = world.created(WORKBOOK)
    run = world.plain.get_run(created.run_id)
    assert run is not None
    assert created.state == run.state == RunState.QUEUED
    assert run.sha256 == GOOD_SHA
    assert world.removes() == []
    assert procedure.staged_path(GOOD_SHA) in world.session.file.staged


def test_register_stages_is_idempotent() -> None:
    procedure.register_stages()
    procedure.register_stages()
    assert registry.stages.names() == (procedure.LANDING_STAGE,)


def test_handlers_register_the_landing_stage_first(world: World) -> None:
    created = world.created(WORKBOOK)
    first, *_ = world.plain.stages(created.run_id)
    assert first.stage == procedure.LANDING_STAGE
    assert first.state == StageState.PENDING


@pytest.mark.usefixtures("registered")
def test_execute_runs_the_landing_stage_and_returns_the_run_view(world: World) -> None:
    created = world.created(WORKBOOK)
    view = world.execute(created.run_id)
    run = world.plain.get_run(created.run_id)
    assert run is not None
    assert view == RunView(run=run, stages=world.plain.stages(created.run_id))
    assert view.run.state == RunState.SUCCEEDED
    ((landed, data),) = world.land.calls
    assert data == WORKBOOK
    assert landed == LandedFile(
        file_sha256=run.sha256,
        filename=run.filename,
        stage_file=f"{run.sha256}.xlsx",
        size_bytes=len(data),
        first_run_id=run.run_id,
    )
    (stage,) = view.stages
    assert stage.detail == world.land(world.session, landed, data)


@pytest.mark.usefixtures("registered")
def test_execute_on_a_run_that_is_not_queued_runs_no_stage(world: World) -> None:
    created = world.created(WORKBOOK)
    first = world.execute(created.run_id)
    landed_once = list(world.land.calls)
    second = world.execute(created.run_id)
    assert second == first
    assert world.land.calls == landed_once


def test_execute_on_a_missing_run_raises_key_error(world: World) -> None:
    with pytest.raises(KeyError):
        world.execute(GOOD_SHA)
    assert world.store.log == [CLAIM_RUN, GET_RUN]


def test_error_after_the_core_call_propagates_and_writes_nothing(world: World) -> None:
    created = world.created(WORKBOOK)
    world.store = Recording(world.plain, fail=STAGES)
    with pytest.raises(RuntimeError):
        world.execute(created.run_id)
    run = world.plain.get_run(created.run_id)
    assert run is not None
    assert run.state == RunState.SUCCEEDED
    log = world.store.log
    last_write = max(i for i, name in enumerate(log) if name in (SET_STATE, CLAIM_RUN))
    assert log[last_write + 1 :] == [GET_RUN, STAGES]
    assert world.session.statements == []


def _schema(model: type) -> Any:
    return SCHEMAS[f"{model.__module__}.{model.__qualname__}"]


def _outcomes(world: World) -> list[tuple[type, dict[str, Any]]]:
    claimed = hashlib.sha256(b"x").hexdigest()
    world.stage(WORKBOOK, claimed)
    rejected = procedure.create_run_handler(
        world.session, f"{claimed}.xlsx", "x.xlsx", claimed, world.host
    ).model_dump(mode="json")
    sha = world.stage(WORKBOOK)
    created = procedure.create_run_handler(
        world.session, f"{sha}.xlsx", "book.xlsx", sha, world.host
    ).model_dump(mode="json")
    view = procedure.execute_run_handler(
        world.session, str(created["run_id"]), world.host
    ).model_dump(mode="json")
    return [(RunRejected, rejected), (RunCreated, created), (RunView, view)]


@pytest.mark.parametrize("index", range(3), ids=["rejected", "created", "view"])
def test_procedure_results_validate_against_the_schema_snapshot(world: World, index: int) -> None:
    model, result = _outcomes(world)[index]
    jsonschema.Draft202012Validator(_schema(model)).validate(result)
    assert model.model_validate_json(json.dumps(result)).model_dump(mode="json") == result


def test_run_contract_is_in_the_snapshot() -> None:
    assert _schema(Run)["title"] == Run.__name__


def test_default_host_lands_a_staged_file_with_the_snowflake_store_and_bronze() -> None:
    """The deployed host, offline: SnowflakeRunStore and BronzeWriter over one FakeSession."""
    oracle = load_oracle("bronze_basic")
    data = (WORKBOOKS / oracle["fixture"]).read_bytes()
    session = snowflake_tables_session()
    session.script_affected(f"MERGE INTO {LandedFile.table_name.upper()}", inserted=1)
    sha = hashlib.sha256(data).hexdigest()
    session.file.staged[procedure.staged_path(sha)] = data
    assert isinstance(procedure.default_host(session).store, SnowflakeRunStore)
    created = procedure.create_run_handler(session, f"{sha}.xlsx", "book.xlsx", sha)
    assert isinstance(created, RunCreated)
    view = procedure.execute_run_handler(session, created.run_id)
    assert view.run.state == RunState.SUCCEEDED
    (stage,) = view.stages
    assert (stage.stage, stage.detail) == (procedure.LANDING_STAGE, bronze.LANDED)
    insert = f"INSERT INTO {BronzeRow.table_name.upper()}"
    binds = [v for q, p in session.statements if q.startswith(insert) for v in p]
    assert len(binds) == oracle["row_count"] * len(BronzeRow.model_fields)
