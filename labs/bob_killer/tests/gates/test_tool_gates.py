"""Tool-backed gates on throwaway projects: types_lint, boundaries, coverage, mutation."""

from __future__ import annotations

import pytest

from bk_gates.core import GateContext, load_gates
from bk_gates.mutation import MIN_KILLED, mutation_violations
from tests.gates.conftest import Project

PYPROJECT = """
[tool.mypy]
strict = true
explicit_package_bases = true
mypy_path = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]

[tool.importlinter]
root_packages = ["app"]

[[tool.importlinter.contracts]]
name = "layers"
type = "layers"
layers = ["app.high", "app.low"]
"""
TYPED = "def double(x: int) -> int:\n    return x * 2\n"
TEST_TYPED = "from app.calc import double\n\n\ndef test_double() -> None:\n    assert double(2) == double(1) * 2\n"


def _base(project: Project) -> Project:
    return project.write(
        {
            "pyproject.toml": PYPROJECT,
            "src/app/__init__.py": "from app import high  # noqa: F401  (keeps layers covered)\n",
            "src/app/high.py": "from app import low\n\nX = low.Y\n",
            "src/app/low.py": "Y = 1\n",
            "src/app/calc.py": TYPED,
            "tests/test_calc.py": TEST_TYPED,
        }
    )


def _rules(gate: str, ctx: GateContext) -> set[str]:
    return {v.rule for v in load_gates()[gate].check(ctx)}


@pytest.mark.parametrize("gate", ["types_lint", "boundaries", "coverage"])
def test_clean_project_passes(project: Project, gate: str) -> None:
    assert _rules(gate, _base(project).context()) == set()


@pytest.mark.parametrize(
    ("files", "gate", "rule"),
    [
        (
            {"src/app/calc.py": "def double(x):\n    return x * 2\n"},
            "types_lint",
            "types_lint/mypy",
        ),
        ({"src/app/calc.py": "import os\n" + TYPED}, "types_lint", "types_lint/ruff"),
        (
            {"src/app/calc.py": "def double(x: int) -> int:\n    return x*2\n"},
            "types_lint",
            "types_lint/format",
        ),
        ({"src/app/low.py": "from app import high\n\nY = 1\n"}, "boundaries", "boundaries/broken"),
        (
            {
                "src/app/calc.py": TYPED
                + "\n\ndef unused(x: int) -> int:\n    if x:\n        return 1\n    return 2\n"
            },
            "coverage",
            "coverage/below-threshold",
        ),
        (
            {"tests/test_calc.py": TEST_TYPED.replace("* 2", "* 3")},
            "coverage",
            "coverage/tests-failed",
        ),
    ],
    ids=["untyped", "unused-import", "unformatted", "layer-violation", "uncovered", "failing-test"],
)
def test_cheat_is_rejected(project: Project, files: dict[str, str], gate: str, rule: str) -> None:
    ctx = _base(project).write(files).context()
    assert rule in _rules(gate, ctx)


def test_coverage_vacuous_on_empty_package(project: Project) -> None:
    project.write({"pyproject.toml": PYPROJECT, "src/app/__init__.py": '"""empty."""\n'})
    assert _rules("coverage", project.context()) == set()


def test_mutation_vacuous_without_runtime_code(project: Project) -> None:
    project.write({"src/bob_killer/runtime/__init__.py": '"""Runtime."""\n'})
    assert _rules("mutation", project.context()) == set()


def test_mutation_is_nightly_only() -> None:
    assert load_gates()["mutation"].nightly_only


@pytest.mark.parametrize(
    ("killed", "survived", "rule"),
    [
        (8, 2, None),
        (7, 3, "mutation/below-threshold"),
        (0, 0, None),
    ],
)
def test_mutation_threshold(killed: int, survived: int, rule: str | None) -> None:
    stats = {"killed": killed, "survived": survived, "total": killed + survived}
    rules = {v.rule for v in mutation_violations(stats)}
    assert rules == ({rule} if rule else set())


def test_threshold_matches_spec() -> None:
    assert MIN_KILLED * 10 == 8
