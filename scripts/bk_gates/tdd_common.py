"""Shared TDD evidence helpers: tests-tree digest, junit parsing, project paths."""

from __future__ import annotations

import hashlib
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_PARTS = frozenset({"__pycache__", ".pytest_cache", ".hypothesis"})


def is_tracked_test_file(rel: str) -> bool:
    parts = rel.split("/")
    return not (EXCLUDED_PARTS & set(parts)) and not rel.endswith(".pyc")


def digest_tests_tree(files: Mapping[str, bytes]) -> str:
    """sha256 over sorted (relative path, sha256(content)) pairs."""
    outer = hashlib.sha256()
    for rel in sorted(files):
        if not is_tracked_test_file(rel):
            continue
        outer.update(rel.encode())
        outer.update(b"\0")
        outer.update(hashlib.sha256(files[rel]).hexdigest().encode())
        outer.update(b"\n")
    return outer.hexdigest()


def read_worktree_tests(project_root: Path) -> dict[str, bytes]:
    tests = project_root / "tests"
    return {
        p.relative_to(tests).as_posix(): p.read_bytes()
        for p in sorted(tests.rglob("*"))
        if p.is_file() and is_tracked_test_file(p.relative_to(tests).as_posix())
    }


def parse_junit(xml_bytes: bytes) -> dict[str, str]:
    """Map ``classname::name`` to passed | failed | error | skipped."""
    root = ET.fromstring(xml_bytes)
    outcomes: dict[str, str] = {}
    for case in root.iter("testcase"):
        node = f"{case.get('classname', '')}::{case.get('name', '')}"
        outcome = "passed"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                outcome = "failed" if child.tag == "failure" else child.tag
                break
        outcomes[node] = outcome
    return outcomes


def repo_root(start: Path) -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())
