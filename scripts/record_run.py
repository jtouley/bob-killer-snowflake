"""Run pytest and record the outcome as TDD evidence under <repo>/.context/runs/<run_id>/.

The only writer of run.json (adversarial condition C1). A red commit must include
the record produced here for its exact tests tree.

    uv run python scripts/record_run.py --phase red tests/unit/test_x.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from bk_gates.tdd_common import (
    PROJECT_ROOT,
    digest_tests_tree,
    parse_junit,
    read_worktree_tests,
    repo_root,
)

PHASES = ("red", "green", "refactor")


def record(project_root: Path, context_dir: Path, phase: str, pytest_args: list[str]) -> Path:
    now = datetime.now(UTC)
    run_id = f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    run_dir = context_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    junit = run_dir / "junit.xml"
    subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", f"--junitxml={junit}"]
        + pytest_args,
        cwd=project_root,
        check=False,
    )
    junit_bytes = junit.read_bytes()
    payload = {
        "run_id": run_id,
        "tdd_phase": phase,
        "recorded_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pytest_args": pytest_args,
        "nodes": parse_junit(junit_bytes),
        "tests_tree_sha256": digest_tests_tree(read_worktree_tests(project_root)),
        "junit_sha256": hashlib.sha256(junit_bytes).hexdigest(),
    }
    out = run_dir / "run.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("pytest_args", nargs="*")
    args = parser.parse_args(argv)
    context_dir = repo_root(PROJECT_ROOT) / ".context"
    out = record(PROJECT_ROOT, context_dir, args.phase, args.pytest_args)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
