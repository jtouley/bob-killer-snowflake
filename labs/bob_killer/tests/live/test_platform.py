"""Snowflake platform facts (docs/SPEC.md §4 F1-F9), checked in this account (host Phase 2).

Every command and its output is appended to ``.context/evidence/snowflake_platform_<date>.md``.
Expected values come from the project files (``snowflake.yml``, ``requirements.txt``) or from the
data the test wrote, never from literals. Names are qualified with the TEST_ schema.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from snowflake.connector.errors import Error as ConnectorError
from snowflake.snowpark import AsyncJob, Row, Session
from snowflake.snowpark.exceptions import SnowparkSQLException

from bob_killer.contracts.runs import RunState
from bob_killer.hosts.snowflake import session as sf
from tests.conftest import workbook_like
from tests.live.conftest import CONNECTION

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parents[1]
HOST = PROJECT / "hosts" / "snowflake"
EVIDENCE = REPO / ".context" / "evidence" / f"snowflake_platform_{datetime.now(UTC):%Y%m%d}.md"
BUILD_LEFTOVERS = (PROJECT / "src.zip", HOST / "requirements.snowflake.txt")

# F3: the 3.12 import set (spec §4), with a required version prefix ("" = any version).
F3_PACKAGES = [
    ("pydantic", "2.11."),
    ("pydantic-core", ""),
    ("annotated-types", ""),
    ("typing-extensions", ""),
    ("typing-inspection", ""),
    ("openpyxl", ""),
    ("et_xmlfile", ""),  # conda name of PyPI et-xmlfile
    ("snowflake-snowpark-python", ""),
]


def record(title: str, body: str) -> None:
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    with EVIDENCE.open("a", encoding="utf-8") as f:
        f.write(
            f"\n## {title}\n\n_{datetime.now(UTC).isoformat()}_\n\n```text\n{body.rstrip()}\n```\n"
        )


def project_yaml(project: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((project / "snowflake.yml").read_text())
    return loaded


def snow(*args: str, project: Path) -> str:
    cmd = ["uv", "run", "--project", str(REPO), "snow", *args, "-c", CONNECTION, "--project"]
    proc = subprocess.run(
        [*cmd, str(project)], cwd=PROJECT, capture_output=True, text=True, check=False
    )
    shown = " ".join([*cmd[4:], str(project.relative_to(PROJECT))])
    record(f"$ {shown}", f"exit {proc.returncode}\n{proc.stdout}{proc.stderr}")
    proc.check_returncode()
    return proc.stdout


def hello_entities() -> dict[str, dict[str, Any]]:
    entities: dict[str, dict[str, Any]] = project_yaml(HOST)["entities"]
    return {k: v for k, v in entities.items() if v["type"] == "streamlit"}


def rows(session: Session, query: str, params: list[Any] | None = None) -> list[Row]:
    return session.sql(query, params).collect()


def dump(found: list[Row]) -> str:
    return json.dumps([r.as_dict() for r in found], indent=2, default=str)


def sql_file(path: Path, **variables: str) -> list[str]:
    text = "\n".join(ln for ln in path.read_text().splitlines() if not ln.lstrip().startswith("--"))
    for key, value in variables.items():
        text = text.replace(f"<% {key} %>", value)
    return [s.strip() for s in text.split(";") if s.strip()]


@pytest.fixture(scope="module")
def deployed(session: Session, schema: str) -> str:
    """F8: `snow snowpark build` then `snow snowpark deploy` into the TEST_ schema."""
    record("hosts/snowflake/snowflake.yml", (HOST / "snowflake.yml").read_text())
    record("hosts/snowflake/requirements.txt", (HOST / "requirements.txt").read_text())
    try:
        snow("snowpark", "build", project=HOST)
        snow("snowpark", "deploy", "--schema", schema, project=HOST)
    finally:
        for leftover in BUILD_LEFTOVERS:
            leftover.unlink(missing_ok=True)
    return schema


@pytest.fixture(scope="module")
def staged(session: Session, schema: str) -> tuple[str, bytes]:
    """F6: put a fixture on an internal stage with auto_compress=False, overwrite=False."""
    data = workbook_like()
    stage = f'"{schema}".UPLOADS'
    rows(
        session,
        f"CREATE STAGE {stage} DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')",
    )
    path = f"@{stage}/{hashlib.sha256(data).hexdigest()}.xlsx"
    session.file.put_stream(io.BytesIO(data), path, auto_compress=False, overwrite=False)
    return path, data


@pytest.fixture(scope="module")
def probe(session: Session, deployed: str, staged: tuple[str, bytes]) -> dict[str, Any]:
    raw = session.call(f'"{deployed}".PLATFORM_PROBE', staged[0])
    result: dict[str, Any] = json.loads(raw)
    record("CALL PLATFORM_PROBE(<staged file>)", json.dumps(result, indent=2))
    return result


def test_f2_core_runs_in_a_312_procedure(probe: dict[str, Any]) -> None:
    runtime = project_yaml(HOST)["entities"]["platform_probe"]["runtime"]
    assert probe["sys_version"].startswith(f"{runtime}.")
    assert probe["run_state"] == RunState.QUEUED.value


@pytest.mark.parametrize(("package", "version_prefix"), F3_PACKAGES)
def test_f3_package_resolves_on_the_anaconda_channel_for_312(
    session: Session, package: str, version_prefix: str
) -> None:
    found = rows(
        session,
        "SELECT package_name, version FROM information_schema.packages"
        " WHERE language = 'python' AND runtime_version = '3.12' AND package_name = ?",
        [package],
    )
    versions = sorted(r["VERSION"] for r in found)
    record(f"F3 {package} (3.12, Anaconda channel)", ", ".join(versions) or "MISSING")
    assert any(v.startswith(version_prefix) for v in versions)


def test_f4_primary_key_is_not_enforced_and_not_null_is(session: Session, schema: str) -> None:
    table = f'"{schema}".F4_PROBE'
    rows(session, f"CREATE TABLE {table} (id NUMBER NOT NULL PRIMARY KEY, v VARCHAR NOT NULL)")
    inserts = [[1, "a"], [1, "a"]]
    for values in inserts:
        rows(session, f"INSERT INTO {table} (id, v) VALUES (?, ?)", values)
    ((count,),) = rows(session, f"SELECT COUNT(*) FROM {table}")
    with pytest.raises((SnowparkSQLException, ConnectorError)) as err:
        rows(session, f"INSERT INTO {table} (id, v) VALUES (?, ?)", [inserts[0][0], None])
    record(
        "F4 duplicate PK + NULL into NOT NULL",
        f"rows after 2 duplicate inserts: {count}\n{err.value}",
    )
    assert count == len(inserts)


def test_f5_owners_rights_procedure_runs_in_its_own_schema(
    probe: dict[str, Any], deployed: str
) -> None:
    assert probe["current_schema"] == deployed


def test_f6_staged_bytes_are_stored_uncompressed(
    session: Session, staged: tuple[str, bytes], probe: dict[str, Any]
) -> None:
    path, data = staged
    stage, name = path.rsplit("/", 1)
    listed = rows(session, f"LIST {stage}")
    record("F6 LIST @UPLOADS", dump(listed))
    (entry,) = [r for r in listed if r["name"].endswith(f"/{name}")]
    assert entry["size"] == len(data)
    assert probe["sha256"] == hashlib.sha256(data).hexdigest()


def test_f8_deploy_ships_the_build_zip_and_packages(session: Session, deployed: str) -> None:
    spec = project_yaml(HOST)
    entity = spec["entities"]["platform_probe"]
    found = rows(session, f'DESCRIBE PROCEDURE "{deployed}".PLATFORM_PROBE(VARCHAR)')
    record("F8 DESCRIBE PROCEDURE PLATFORM_PROBE(VARCHAR)", dump(found))
    props = {r["property"]: r["value"] for r in found}
    for artifact in spec["mixins"]["snowpark_shared"]["artifacts"]:
        assert artifact["dest"] in props["imports"]
    # snow 3.29 resolves requirements.txt through the artifact repository (F3 path).
    declared = props["packages"] + props["artifact_repository_packages"]
    for requirement in (HOST / "requirements.txt").read_text().split():
        assert re.split(r"[<>=!~ ]", requirement)[0] in declared
    assert props["runtime_version"] == entity["runtime"]
    assert props["execute as"] == ("CALLER" if entity["execute_as_caller"] else "OWNER")


def test_f9_call_without_blocking_returns_an_async_job(
    session: Session, deployed: str, staged: tuple[str, bytes]
) -> None:
    job = session.call(f'"{deployed}".PLATFORM_PROBE', staged[0], block=False)
    assert isinstance(job, AsyncJob)
    result = job.result()
    record(
        "F9 session.call(..., block=False)",
        f"{type(job).__name__} is_done={job.is_done()}\n{result}",
    )
    assert job.is_done()


@pytest.fixture(scope="module")
def hello(session: Session) -> Iterator[tuple[str, dict[str, dict[str, Any]]]]:
    """F1, F7: deploy the hello app with and without the PyPI integration into its own TEST_ schema."""
    with sf.test_schema(session) as hello_schema:
        described: dict[str, dict[str, Any]] = {}
        for entity_id, entity in hello_entities().items():
            snow("streamlit", "deploy", entity_id, "--schema", hello_schema, project=HOST)
            name = entity["identifier"]["name"]
            (row,) = rows(session, f'DESCRIBE STREAMLIT "{hello_schema}".{name}')
            described[entity_id] = row.as_dict()
            record(f"F1/F7 DESCRIBE STREAMLIT {name}", dump([row]))
        yield hello_schema, described


def test_f1_hello_app_uses_the_container_runtime_and_pool(
    hello: tuple[str, dict[str, dict[str, Any]]],
) -> None:
    shared = project_yaml(HOST)["mixins"]["hello_shared"]
    for described in hello[1].values():
        assert described["runtime_name"] == shared["runtime_name"]
        assert described["compute_pool"] == shared["compute_pool"]


def test_f7_pypi_integration_is_attached_only_where_declared(
    hello: tuple[str, dict[str, dict[str, Any]]],
) -> None:
    entities = hello_entities()
    every = {e for ent in entities.values() for e in ent.get("external_access_integrations", [])}
    assert every
    for entity_id, entity in entities.items():
        attached = hello[1][entity_id]["external_access_integrations"] or ""
        for integration in every:
            declared = integration in entity.get("external_access_integrations", [])
            assert (integration in attached) is declared


def test_hello_pool_suspends_and_teardown_drops_the_schema(
    session: Session, hello: tuple[str, dict[str, dict[str, Any]]]
) -> None:
    hello_schema = hello[0]
    pool = project_yaml(HOST)["mixins"]["hello_shared"]["compute_pool"]
    (before,) = rows(session, f"SHOW COMPUTE POOLS LIKE '{pool}'")
    rows(session, f"ALTER COMPUTE POOL {pool} SUSPEND")
    (after,) = rows(session, f"SHOW COMPUTE POOLS LIKE '{pool}'")
    record(f"Compute pool {pool} before and after ALTER ... SUSPEND", dump([before, after]))
    for statement in sql_file(HOST / "sql" / "99_teardown.sql", schema=hello_schema):
        record("99_teardown.sql", f"{statement}\n{dump(rows(session, statement))}")
    names = [r["name"] for r in rows(session, "SHOW SCHEMAS")]
    assert hello_schema not in names
