"""Evasions found by the Phase 0 cheat demo (.context/evidence/*_cheat-rejections.txt)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bk_gates.core import GateContext, load_gates
from bk_gates.tdd_common import PROJECT_ROOT
from tests.gates.conftest import Project
from tests.gates.test_static_gates import BASE


@pytest.mark.parametrize(
    "source",
    [
        "@__import__('pytest').mark.xfail\ndef test_c():\n    assert f()\n",
        "import importlib\n\n\ndef test_c():\n    assert f() == importlib.import_module('pytest').approx(g())\n",
        "def test_c():\n    __import__('pytest').skip('later')\n",
    ],
    ids=["dunder-import-xfail", "import-module-approx", "dunder-import-skip"],
)
def test_dynamic_import_skips_rejected(project: Project, source: str) -> None:
    project.write({**BASE, "tests/unit/test_c.py": source})
    rules = {v.rule for v in load_gates()["no_silent_skips"].check(project.context())}
    assert rules & {"no_silent_skips/unallowed", "no_silent_skips/dynamic-import"}


def test_contracts_gate_reads_the_checked_project_not_the_installed_one(tmp_path: Path) -> None:
    copy = tmp_path / "proj"
    shutil.copytree(
        PROJECT_ROOT / "src", copy / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    runs = copy / "src" / "bob_killer" / "contracts" / "runs.py"
    runs.write_text(
        runs.read_text().replace(
            "    schema_version: int\n", "    schema_version: int\n    owner: str\n", 1
        )
    )
    ctx = GateContext(repo_root=tmp_path, project_root=copy, base=None)
    rules = {v.rule for v in load_gates()["contracts_versioned"].check(ctx)}
    assert "contracts_versioned/drift" in rules
