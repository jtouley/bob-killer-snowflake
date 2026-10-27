"""Throwaway git histories for gate tests (TB-1: one builder, no cloned setups)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from bk_gates.tdd_common import PROJECT_ROOT, digest_tests_tree, parse_junit, read_worktree_tests

if TYPE_CHECKING:
    from bk_gates.core import GateContext

PREFIX = "proj/"


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def junit_xml(nodes: Mapping[str, str]) -> bytes:
    cases = []
    for node, outcome in nodes.items():
        classname, name = node.split("::")
        inner = "" if outcome == "passed" else f"<{'failure' if outcome == 'failed' else outcome}/>"
        cases.append(f'<testcase classname="{classname}" name="{name}">{inner}</testcase>')
    return f"<testsuites><testsuite>{''.join(cases)}</testsuite></testsuites>".encode()


class History:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.project = root / PREFIX.rstrip("/")
        _git(root, "init", "-q", "-b", "main")
        _git(root, "config", "user.email", "t@example.com")
        _git(root, "config", "user.name", "t")
        _git(root, "config", "commit.gpgsign", "false")
        self.base = self.commit({"README.md": "base\n"}, phase=None)

    def write(self, files: Mapping[str, str | None]) -> None:
        for rel, content in files.items():
            path = self.root / rel
            if content is None:
                path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    def commit(
        self,
        files: Mapping[str, str | None],
        phase: str | None,
        trailers: Mapping[str, str] | None = None,
    ) -> str:
        self.write(files)
        lines = [f"TDD-Phase: {phase}"] if phase else []
        lines += [f"{k}: {v}" for k, v in (trailers or {}).items()]
        message = "change\n\n" + "\n".join(lines) if lines else "change"
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--allow-empty", "-m", message)
        return _git(self.root, "rev-parse", "HEAD")

    def record(self, nodes: Mapping[str, str], *, phase: str = "red") -> str:
        """Write an honest run record for the current tests tree; return its repo path."""
        junit = junit_xml(nodes)
        run_id = uuid.uuid4().hex[:8]
        run_dir = self.root / ".context" / "runs" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "junit.xml").write_bytes(junit)
        payload = {
            "run_id": run_id,
            "tdd_phase": phase,
            "nodes": parse_junit(junit),
            "tests_tree_sha256": digest_tests_tree(read_worktree_tests(self.project)),
            "junit_sha256": hashlib.sha256(junit).hexdigest(),
        }
        (run_dir / "run.json").write_text(json.dumps(payload))
        return f".context/runs/{run_id}/run.json"

    def red(self, files: Mapping[str, str | None], nodes: Mapping[str, str]) -> str:
        self.write(files)
        self.record(nodes)
        return self.commit({}, phase="red")

    def context(self) -> GateContext:
        from bk_gates.core import GateContext

        return GateContext(repo_root=self.root, project_root=self.project, base=self.base)


@pytest.fixture
def history(tmp_path: Path) -> History:
    return History(tmp_path)


class Project:
    """A working-tree-only project for static gates (no git history needed)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.project = root / PREFIX.rstrip("/")
        self.project.mkdir()

    def write(self, files: Mapping[str, str]) -> Project:
        for rel, content in files.items():
            path = self.project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return self

    def context(self) -> GateContext:
        from bk_gates.core import GateContext

        return GateContext(repo_root=self.root, project_root=self.project, base=None)


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return Project(tmp_path)


def copy_project(tmp_path: Path, files: Mapping[str, str] | None = None) -> Path:
    """A throwaway copy of this project's src/ and pyproject.toml, with ``files`` written on top.

    Gates that run the real project (contracts, import-linter) mutate the copy, never the repo.
    """
    copy = tmp_path / "proj"
    shutil.copytree(
        PROJECT_ROOT / "src", copy / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy(PROJECT_ROOT / "pyproject.toml", copy / "pyproject.toml")
    for rel, content in (files or {}).items():
        path = copy / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return copy


def lint_imports(copy: Path) -> subprocess.CompletedProcess[str]:
    """Run this environment's import-linter on a ``copy_project`` copy (its own pyproject.toml)."""
    return subprocess.run(
        [str(Path(sys.executable).with_name("lint-imports"))],
        cwd=copy,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(copy / "src")},
    )
