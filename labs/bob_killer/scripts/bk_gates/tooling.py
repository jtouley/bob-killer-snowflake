"""Tool-backed gates: types_lint (ruff + mypy --strict), boundaries (import-linter), coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from bk_gates.core import GateContext, Violation, gate
from bk_gates.tdd_order import is_trivial_module

MIN_COVERAGE = 90.0
BIN = Path(sys.executable).parent


def _run(cmd: list[str], cwd: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, env={**os.environ, **env}, check=False
    )


def _tail(proc: subprocess.CompletedProcess[str], lines: int = 8) -> str:
    return " | ".join((proc.stdout + proc.stderr).strip().splitlines()[-lines:])


def _existing(root: Path, *names: str) -> list[str]:
    return [n for n in names if (root / n).is_dir()]


@gate("types_lint")
def types_lint(ctx: GateContext) -> list[Violation]:
    root = ctx.project_root
    lint_targets = _existing(root, "src", "scripts", "tests")
    type_targets = _existing(root, "src", "scripts")
    checks = [
        ("types_lint/ruff", [str(BIN / "ruff"), "check", *lint_targets]),
        ("types_lint/format", [str(BIN / "ruff"), "format", "--check", *lint_targets]),
        ("types_lint/mypy", [str(BIN / "mypy"), "--strict", *type_targets]),
    ]
    out = []
    for rule, cmd in checks:
        proc = _run(cmd, root)
        if proc.returncode != 0:
            out.append(Violation(rule, _tail(proc)))
    return out


@gate("boundaries")
def boundaries(ctx: GateContext) -> list[Violation]:
    root = ctx.project_root
    proc = _run([str(BIN / "lint-imports")], root, PYTHONPATH=str(root / "src"))
    return [] if proc.returncode == 0 else [Violation("boundaries/broken", _tail(proc))]


def has_statements(src: Path) -> bool:
    modules = (p for p in src.rglob("*.py") if "__pycache__" not in p.parts)
    return any(not is_trivial_module(p.read_bytes()) for p in modules)


@gate("coverage")
def coverage(ctx: GateContext) -> list[Violation]:
    root = ctx.project_root
    if not has_statements(root / "src"):
        return []  # vacuous: nothing to cover yet (G10)
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "coverage.json"
        proc = _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--cov=src",
                f"--cov-report=json:{report}",
                "--cov-fail-under=0",
            ],
            root,
        )
        if proc.returncode != 0:
            return [Violation("coverage/tests-failed", _tail(proc))]
        totals = json.loads(report.read_text())["totals"]
    percent = float(totals["percent_covered"])
    if percent < MIN_COVERAGE:
        return [
            Violation("coverage/below-threshold", f"{percent:.1f}% of src/ < {MIN_COVERAGE:.0f}%")
        ]
    return []
