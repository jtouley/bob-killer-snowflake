"""Compiler gate changes (docs/SPEC-compiler-dbt.md §8, gate and dependency prep).

Each test names the cheat it must stop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bk_gates.contracts_versioned import generate_for, snapshot_dir
from bk_gates.core import GateContext, Violation, load_gates
from bk_gates.tdd_common import PROJECT_ROOT
from tests.gates.conftest import Project, copy_project, lint_imports
from tests.gates.test_static_gates import BASE

CONTRACTS_INIT = "src/bob_killer/contracts/__init__.py"
WORKBOOK_PROBE = "src/bob_killer/contracts/workbook_probe.py"


def _violations(gate: str, ctx: GateContext) -> list[Violation]:
    return load_gates()[gate].check(ctx)


# no_oracle_literals: generated-output snapshot tests (D32) may not hard-code expected values.
@pytest.mark.parametrize(
    "scope", ["tests/unit", "tests/integration", "tests/live", "tests/snapshot"]
)
def test_literal_in_scoped_test_is_rejected(project: Project, scope: str) -> None:
    project.write({**BASE, f"{scope}/test_c.py": "def test_c():\n    assert f() == 6.0\n"})
    rules = {v.rule for v in _violations("no_oracle_literals", project.context())}
    assert "no_oracle_literals/literal" in rules


# import-linter (§3.5): a generator reads registry.functions; it never evaluates Excel semantics.
@pytest.mark.parametrize(
    ("leak", "source"),
    [
        pytest.param("src/bob_killer/generate/leak.py", "import bob_killer.runtime\n", id="pkg"),
        pytest.param(
            "src/bob_killer/generate/docs/leak.py",
            "from bob_killer.runtime import functions\n",
            id="subpkg",
        ),
    ],
)
def test_generate_importing_runtime_is_rejected(tmp_path: Path, leak: str, source: str) -> None:
    proc = lint_imports(copy_project(tmp_path, {leak: source}))
    assert proc.returncode != 0, proc.stdout
    assert "bob_killer.generate" in proc.stdout


def _workbook_probe(fields: str) -> str:
    return (
        "from bob_killer.contracts.base import StrictModel\n\n\n"
        "class WbProbe(StrictModel):\n"
        '    table_name = "wb_probe"\n'
        '    primary_key = ("run_id",)\n\n'
        f"{fields}"
    )


# contracts_versioned (D31): a workbook.db model change without a SCHEMA_VERSION bump fails,
# because workbook_ddl.sql (from WORKBOOK_TABLES) is part of the snapshot.
def test_workbook_model_change_without_bump_fails(tmp_path: Path) -> None:
    init = (PROJECT_ROOT / CONTRACTS_INIT).read_text(encoding="utf-8")
    wired = (
        f"{init}\nfrom bob_killer.contracts.workbook_probe import WbProbe  # noqa: E402\n\n"
        "WORKBOOK_TABLES = (WbProbe,)\n"
    )
    copy = copy_project(
        tmp_path, {CONTRACTS_INIT: wired, WORKBOOK_PROBE: _workbook_probe("    run_id: str\n")}
    )
    ctx = GateContext(repo_root=tmp_path, project_root=copy, base=None)
    version, generated = generate_for(copy)
    for name, text in generated.items():  # the reviewed snapshot of the current contracts
        (snapshot_dir(copy, version) / name).write_text(text, encoding="utf-8")
    assert _violations("contracts_versioned", ctx) == []

    (copy / WORKBOOK_PROBE).write_text(_workbook_probe("    run_id: str\n    sheet: str\n"))
    drifted = {v.message.split()[0] for v in _violations("contracts_versioned", ctx)}
    assert "workbook_ddl.sql" in drifted
