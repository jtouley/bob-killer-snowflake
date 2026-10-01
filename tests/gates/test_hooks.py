"""Claude Code hooks: PostToolUse runs tests and logs; Stop blocks while any gate fails."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bk_gates.hook_log import verify_chain
from hook_post_edit import post_edit
from hook_stop import EXIT_BLOCK, EXIT_OK, stop
from tests.gates.conftest import Project

LOG = ".context/hooks.log"
PASSING_GATES = [sys.executable, "-c", "print('OK    tdd_order')"]
FAILING_GATES = [
    sys.executable,
    "-c",
    "import sys; print('FAIL  tdd_order', file=sys.stderr); sys.exit(1)",
]


def _events(root: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (root / LOG).read_text().splitlines()]


def _project(project: Project) -> Project:
    return project.write(
        {
            "pyproject.toml": '[tool.pytest.ini_options]\npythonpath = ["src"]\n',
            "src/app/__init__.py": "",
            "tests/unit/test_ok.py": "def test_ok() -> None:\n    assert True\n",
        }
    )


def test_edit_outside_src_is_ignored(project: Project) -> None:
    p = _project(project)
    payload = {"tool_input": {"file_path": str(p.project / "README.md")}}
    assert post_edit(payload, p.project, p.root) == EXIT_OK
    assert not (p.root / LOG).exists()


def test_edit_under_src_runs_tests_and_logs(project: Project) -> None:
    p = _project(project)
    payload = {"tool_input": {"file_path": str(p.project / "src/app/__init__.py")}}
    assert post_edit(payload, p.project, p.root) == EXIT_OK
    (event,) = _events(p.root)
    assert event["event"] == post_edit.__name__
    assert event["file"] == "src/app/__init__.py"
    assert (p.root / ".context" / "runs" / str(event["run_id"]) / "junit.xml").is_file()
    assert verify_chain((p.root / LOG).read_text()) is None


def test_stop_blocks_and_logs_failed_gates(project: Project) -> None:
    p = _project(project)
    assert stop(p.project, p.root, FAILING_GATES) == EXIT_BLOCK
    (event,) = _events(p.root)
    assert event["failed_gates"] == ["tdd_order"]
    assert verify_chain((p.root / LOG).read_text()) is None


def test_stop_allows_when_gates_pass(project: Project) -> None:
    p = _project(project)
    assert stop(p.project, p.root, PASSING_GATES) == EXIT_OK
    assert not (p.root / LOG).exists()
