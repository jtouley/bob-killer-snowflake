"""hosts/snowflake/snowflake.yml: the procedure and app entities (docs/SPEC.md §6.3, F1, F2, F7)."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from bob_killer.hosts.snowflake import procedure

PROJECT = Path(__file__).resolve().parents[3] / "hosts/snowflake"
DEFINITION: dict[str, Any] = yaml.safe_load((PROJECT / "snowflake.yml").read_text())
APP_DIR = PROJECT.parents[1] / "src/bob_killer_sis"
PROCEDURES = {
    "CREATE_RUN": procedure.create_run_procedure,
    "EXECUTE_RUN": procedure.execute_run_procedure,
}


# The Phase 2 platform probes that tests/live/test_platform.py deploys; not deploy entities.
PROBES = frozenset({"platform_probe", "hello_eai", "hello_no_eai"})


def _entities(kind: str) -> dict[str, dict[str, Any]]:
    return {
        e["identifier"]["name"]: e
        for key, e in DEFINITION["entities"].items()
        if e["type"] == kind and key not in PROBES
    }


def test_the_procedure_entities_are_exactly_the_handlers() -> None:
    assert sorted(_entities("procedure")) == sorted(PROCEDURES)


@pytest.mark.parametrize("name", sorted(PROCEDURES))
def test_procedure_entity_resolves_to_its_handler(name: str) -> None:
    entity = _entities("procedure")[name]
    handler = PROCEDURES[name]
    assert entity["handler"] == f"{handler.__module__}.{handler.__qualname__}"
    params = list(inspect.signature(PROCEDURES[name]).parameters)
    # Snowflake: a handler takes the session and exactly the declared arguments (seen live:
    # error 100357 "defined with 5 arguments (including session), but ... contains 3").
    assert params[0] == procedure.SESSION_PARAMETER
    assert params[1:] == [p["name"] for p in entity["signature"]]
    assert entity["runtime"] == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert entity["execute_as_caller"] is False
    assert entity["returns"].upper() == procedure.RETURNS


def test_app_entity_ships_the_sis_package_on_the_container_runtime() -> None:
    (app,) = _entities("streamlit").values()
    sources = {PROJECT / a["src"] for a in app["artifacts"]}
    assert all(src.resolve().is_file() for src in sources)
    assert {src.resolve() for src in sources} == {
        APP_DIR / name for name in ("streamlit_app.py", "schemas.json", "pyproject.toml")
    }
    assert app["main_file"] in {a["dest"] for a in app["artifacts"]}
    assert app["compute_pool"]
    assert app["external_access_integrations"]
    assert app["query_warehouse"]
