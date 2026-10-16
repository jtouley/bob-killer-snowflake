"""Host Phase 1 gate changes (docs/SPEC.md §1.6): each test names the cheat it must stop."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from bk_gates.core import GateContext, load_gates
from bk_gates.tdd_common import PROJECT_ROOT
from hook_stop import EXIT_BLOCK, EXIT_OK, stop
from tests.gates.conftest import History, Project
from tests.gates.test_hooks import FAILING_GATES, _events
from tests.gates.test_static_gates import BASE

BLOCKED = ".context/coco/BLOCKED"


def _rules(gate: str, ctx: GateContext) -> set[str]:
    return {v.rule for v in load_gates()[gate].check(ctx)}


# §1.6 item 4: live tests may not hard-code expected values either.
def test_literal_in_live_test_is_rejected(project: Project) -> None:
    project.write({**BASE, "tests/live/test_c.py": "def test_c():\n    assert f() == 6.0\n"})
    assert "no_oracle_literals/literal" in _rules("no_oracle_literals", project.context())


# §1.6 item 8: a red commit under the host test tree is an ordinary red commit.
def test_red_commit_under_host_tests_passes_tdd_order(history: History) -> None:
    history.red(
        {"proj/tests/unit/hosts/test_store.py": "def test_x() -> None:\n    assert f()\n"},
        {"tests.unit.hosts.test_store::test_x": "failed"},
    )
    assert not _rules("tdd_order", history.context())


# §1.6 item 8: a green commit may not weaken an assertion in a live test.
def test_green_edit_of_live_assertion_is_rejected(history: History) -> None:
    live = "proj/tests/live/test_l.py"
    history.commit({live: "def test_l() -> None:\n    assert f() == g()\n"}, phase="scaffold")
    history.commit({live: "def test_l() -> None:\n    assert True\n"}, phase="green")
    assert any(
        r.startswith("assertions_frozen/") for r in _rules("assertions_frozen", history.context())
    )


# §1.6 item 0 (G5): CoCo may stop blocked with a marker; without it, failing gates still refuse.
def test_stop_with_blocked_marker_is_allowed_and_logged(project: Project) -> None:
    marker = project.root / BLOCKED
    marker.parent.mkdir(parents=True)
    marker.write_text("false platform fact F3\n")
    assert stop(project.project, project.root, FAILING_GATES) == EXIT_OK
    (event,) = _events(project.root)
    assert event["event"] == "stop_allowed_blocked"
    assert event["failed_gates"] == ["tdd_order"]


def test_stop_without_marker_still_refuses(project: Project) -> None:
    assert stop(project.project, project.root, FAILING_GATES) == EXIT_BLOCK
    (event,) = _events(project.root)
    assert event["event"] == "stop_blocked"


# §1.6 item 3: a new contracts module is found without editing the gate.
def test_new_contract_module_is_discovered(tmp_path: Path) -> None:
    copy = tmp_path / "proj"
    shutil.copytree(
        PROJECT_ROOT / "src", copy / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    (copy / "src" / "bob_killer" / "contracts" / "extra_probe.py").write_text(
        "from bob_killer.contracts.base import StrictModel\n\n\n"
        "class ExtraProbe(StrictModel):\n    name: str\n"
    )
    ctx = GateContext(repo_root=tmp_path, project_root=copy, base=None)
    assert "contracts_versioned/drift" in _rules("contracts_versioned", ctx)


# §1.6 item 1: the Streamlit app package never imports the core.
def _lint_imports(project_root: Path) -> subprocess.CompletedProcess[str]:
    exe = Path(sys.executable).with_name("lint-imports")
    return subprocess.run(
        [str(exe)],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(project_root / "src")},
    )


def test_app_package_importing_core_is_rejected(tmp_path: Path) -> None:
    copy = tmp_path / "proj"
    shutil.copytree(
        PROJECT_ROOT / "src", copy / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy(PROJECT_ROOT / "pyproject.toml", copy / "pyproject.toml")
    sis = copy / "src" / "bob_killer_sis"
    sis.mkdir(exist_ok=True)
    (sis / "__init__.py").write_text('"""App package."""\n')
    (sis / "leak.py").write_text("import bob_killer.contracts\n")
    proc = _lint_imports(copy)
    assert proc.returncode != 0, proc.stdout
    assert "bob_killer_sis" in proc.stdout
