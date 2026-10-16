"""hosts/snowflake/snowflake.yml: the procedure and app entities (docs/SPEC.md §6.3, F1, F2, F7)."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from bob_killer.hosts.snowflake import procedure

PROJECT = Path(__file__).resolve().parents[3] / "hosts/snowflake"
DEFINITION: dict[str, Any] = yaml.safe_load((PROJECT / "snowflake.yml").read_text())
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
    module, _, attr = entity["handler"].rpartition(".")
    assert getattr(importlib.import_module(module), attr) is PROCEDURES[name]
    params = list(inspect.signature(PROCEDURES[name]).parameters)
    assert [p["name"] for p in entity["signature"]] == params[1:-1]
    assert entity["runtime"] == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert entity["execute_as_caller"] is False
    assert entity["returns"].upper() == procedure.RETURNS
