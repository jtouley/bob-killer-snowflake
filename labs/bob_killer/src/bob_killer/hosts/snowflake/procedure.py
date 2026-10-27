"""Stored-procedure handlers CREATE_RUN and EXECUTE_RUN (docs/SPEC.md §5.2, D1, D4).

Only this module gets a session from Snowpark; the store and the bronze writer receive it.
SQL text never holds user data: the staged path is a bound value built from a checked sha256.
The landing stage is ``bronze.land_bronze``; each EXECUTE_RUN binds it to this call's host
through ``bronze.landing_context``. RUN_PIPELINE adds the compiler stages (``register_pipeline``):
they run against the run's workbook.db in the host's workspace, and the handler puts workbook.db
and ir.yaml on ``@DBT_SRC/<run_id>/`` after the run.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

from snowflake.snowpark import Session

from bob_killer.contracts.bronze import LandedFile
from bob_killer.contracts.runs import RunCreated, RunRejected, RunView, UploadLimits
from bob_killer.extract import stage as extract_stage
from bob_killer.generate import stage as generate_stage
from bob_killer.graph import stage as graph_stage
from bob_killer.hosts.snowflake import bronze
from bob_killer.hosts.snowflake.compiler import CompilerIO
from bob_killer.hosts.snowflake.store import SnowflakeRunStore
from bob_killer.lift import stage as lift_stage
from bob_killer.service import workspace
from bob_killer.service.runs import create_run, execute_run
from bob_killer.service.uploads import UploadRejected
from bob_killer.service.workspace import Workspace
from bob_killer.store import RunRepository

UPLOADS = bronze.UPLOADS
LANDING_STAGE = bronze.STAGE_NAME
SHA_MISMATCH = "sha256 mismatch"
BAD_INPUT = "sha256 must be 64 lowercase hex digits and stage_file must be <sha256>.xlsx"
REMOVE_SQL = "REMOVE ?"
RETURNS = "VARIANT"
DBT_SRC = "@DBT_SRC"
RUN_SCHEMA_INFIX = "__R_"  # a run's dbt output schema is <deployment schema>__R_<run id>
WORKBOOK_DB = workspace.WORKBOOK_DB
IR_YAML = workspace.IR_YAML
PERSISTED = (WORKBOOK_DB, IR_YAML)
_SHA256 = re.compile(r"[0-9a-f]{64}")

Lander = Callable[[Session, LandedFile, bytes], str]
"""Land one staged file into bronze; the returned text is the stage detail."""


def default_workspace() -> Workspace:
    return Workspace(Path(tempfile.gettempdir()) / "bob_killer")


@dataclass(frozen=True)
class Host:
    """One handler call's session, run store, bronze lander and local run workspace."""

    session: Session
    store: RunRepository
    land: Lander
    limits: UploadLimits = field(default_factory=UploadLimits)
    workspace: Workspace = field(default_factory=default_workspace)


def default_host(session: Session) -> Host:
    """The deployed host: SnowflakeRunStore and the BronzeWriter landing over the session."""
    return Host(session=session, store=SnowflakeRunStore(session), land=bronze.land_file)


HostFactory = Callable[[Session], Host]


def staged_path(sha256: str) -> str:
    return f"{UPLOADS}/{sha256}.xlsx"


def _remove(session: Session, sha256: str) -> None:
    session.sql(REMOVE_SQL, params=[staged_path(sha256)]).collect()


def register_stages() -> None:
    """Add the landing stage once; safe to call at import and at every handler entry (D4)."""
    bronze.register_stages()


class _Bound:
    """A stage IO that resolves to the object bound for the current handler call."""

    def __init__(self, var: ContextVar[Any]) -> None:
        self._var = var

    def __getattr__(self, name: str) -> Any:
        return getattr(self._var.get(), name)


_workspace: ContextVar[Workspace] = ContextVar("workspace")
_compiler: ContextVar[CompilerIO] = ContextVar("compiler")
_BOUND = _Bound(_workspace)
_BOUND_COMPILER = _Bound(_compiler)


def register_pipeline() -> None:
    """Landing, then the compiler stages, each once (D4, docs/SPEC-compiler-dbt.md §3.1)."""
    register_stages()
    extract_stage.register_stages()
    graph_stage.register_stages(_BOUND)
    lift_stage.register_stages(_BOUND)
    generate_stage.register_stages(_BOUND_COMPILER)


def create_run_handler(
    session: Session,
    stage_file: str,
    filename: str,
    sha256: str,
    host_factory: HostFactory = default_host,
) -> RunCreated | RunRejected:
    register_stages()
    if not _SHA256.fullmatch(sha256) or stage_file != f"{sha256}.xlsx":
        return RunRejected(status=400, detail=BAD_INPUT)
    host = host_factory(session)
    data = bronze.stage_reader(session)(stage_file)
    if hashlib.sha256(data).hexdigest() != sha256:
        _remove(session, sha256)
        return RunRejected(status=400, detail=SHA_MISMATCH)
    try:
        run = create_run(host.store, filename, data, host.limits)
    except UploadRejected as exc:
        _remove(session, sha256)
        return RunRejected.model_validate({"status": int(exc.status), "detail": exc.detail})
    return RunCreated(run_id=run.run_id, state=run.state)


def _landing(host: Host) -> bronze.BronzeContext:
    return bronze.BronzeContext(
        session=host.session,
        read_file=bronze.stage_reader(host.session),
        store=host.store,
        land=partial(host.land, host.session),
    )


def execute_run_handler(
    session: Session, run_id: str, host_factory: HostFactory = default_host
) -> RunView:
    register_stages()
    host = host_factory(session)
    with bronze.landing_context(_landing(host)):
        execute_run(host.store, run_id)
    run = host.store.get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    return RunView(run=run, stages=host.store.stages(run_id))


def _read_upload(host: Host) -> Callable[[str], bytes]:
    def read(run_id: str) -> bytes:
        run = host.store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return bronze.stage_reader(host.session)(f"{run.sha256}.xlsx")

    return read


@contextmanager
def _compiler_context(host: Host) -> Iterator[None]:
    token = _workspace.set(host.workspace)
    compiler = _compiler.set(CompilerIO(host.session, host.workspace))
    try:
        with extract_stage.bind_inputs(
            read_workbook=_read_upload(host), raw_db=host.workspace.raw_db
        ):
            yield
    finally:
        _compiler.reset(compiler)
        _workspace.reset(token)


def _persist(host: Host, run_id: str) -> None:
    """Put the run's workbook.db and ir.yaml, where they exist, on @DBT_SRC/<run_id>/."""
    for name in PERSISTED:
        path = host.workspace.path(run_id, name)
        if path.is_file():
            with path.open("rb") as f:
                host.session.file.put_stream(
                    f, f"{DBT_SRC}/{run_id}/{name}", auto_compress=False, overwrite=True
                )


def run_pipeline_handler(
    session: Session, run_id: str, host_factory: HostFactory = default_host
) -> RunView:
    register_pipeline()
    host = host_factory(session)
    host.workspace.path(run_id, "").mkdir(parents=True, exist_ok=True)
    try:
        with bronze.landing_context(_landing(host)), _compiler_context(host):
            execute_run(host.store, run_id)
    finally:
        _persist(host, run_id)
    run = host.store.get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    return RunView(run=run, stages=host.store.stages(run_id))


SESSION_PARAMETER = "session"  # Snowflake passes the Snowpark session as the first handler argument


def create_run_procedure(
    session: Session,
    stage_file: str,
    filename: str,
    sha256: str,
) -> dict[str, Any]:
    """CREATE_RUN(VARCHAR, VARCHAR, VARCHAR) RETURNS VARIANT."""
    result = create_run_handler(session, stage_file, filename, sha256, default_host)
    return result.model_dump(mode="json")


def execute_run_procedure(session: Session, run_id: str) -> dict[str, Any]:
    """EXECUTE_RUN(VARCHAR) RETURNS VARIANT."""
    return execute_run_handler(session, run_id, default_host).model_dump(mode="json")


register_stages()
