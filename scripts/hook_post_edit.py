"""Claude Code PostToolUse hook: an edit under src/ runs the tests and logs the run.

Writes .context/runs/<run_id>/{junit.xml,hook-run.json} and appends a chained event to
.context/hooks.log. Exit 2 feeds a failing summary back to the agent.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bk_gates.hook_log import LOG, append_event
from bk_gates.tdd_common import PROJECT_ROOT, parse_junit, repo_root

EXIT_OK = 0
EXIT_FEEDBACK = 2
SUITES = ("tests/unit", "tests/integration")


def post_edit(payload: dict[str, Any], project_root: Path, repo: Path) -> int:
    raw = str(payload.get("tool_input", {}).get("file_path", ""))
    try:
        rel = Path(raw).resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return EXIT_OK
    if not rel.startswith("src/"):
        return EXIT_OK

    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    run_dir = repo / ".context" / "runs" / run_id
    run_dir.mkdir(parents=True)
    junit = run_dir / "junit.xml"
    suites = [s for s in SUITES if (project_root / s).is_dir()]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"]
        + suites,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    result = "passed" if proc.returncode == 0 else "failed"
    nodes = parse_junit(junit.read_bytes()) if junit.is_file() else {}
    record = {"run_id": run_id, "trigger": rel, "result": result, "nodes": nodes}
    (run_dir / "hook-run.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    append_event(
        repo / LOG, {"event": "post_edit", "file": rel, "run_id": run_id, "result": result}
    )
    if result == "failed":
        print("\n".join(proc.stdout.splitlines()[-15:]), file=sys.stderr)
        return EXIT_FEEDBACK
    return EXIT_OK


def main() -> int:
    return post_edit(json.load(sys.stdin), PROJECT_ROOT, repo_root(PROJECT_ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
