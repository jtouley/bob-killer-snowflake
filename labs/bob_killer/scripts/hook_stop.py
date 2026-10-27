"""Claude Code Stop hook: the agent cannot finish while any gate fails (exit 2 blocks).

A blocked stop is appended to the chained .context/hooks.log with the failed gate names.
An agent that cannot go on (a false platform fact, a spec conflict) writes its reason to
.context/coco/BLOCKED; the stop is then allowed and logged as stop_allowed_blocked, so the
orchestrator sees the blocked call instead of a call that runs until its turn limit.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from bk_gates.hook_log import LOG, append_event
from bk_gates.tdd_common import PROJECT_ROOT, repo_root

EXIT_OK = 0
EXIT_BLOCK = 2
FAILED = re.compile(r"^FAIL\s+(\S+)", re.M)
BLOCKED_MARKER = Path(".context") / "coco" / "BLOCKED"


def stop(project_root: Path, repo: Path, gates_cmd: list[str] | None = None) -> int:
    cmd = gates_cmd or [sys.executable, str(project_root / "scripts" / "gates.py")]
    proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return EXIT_OK
    failed = FAILED.findall(proc.stderr)
    if (repo / BLOCKED_MARKER).is_file():
        append_event(repo / LOG, {"event": "stop_allowed_blocked", "failed_gates": failed})
        print(f"Stop allowed: {BLOCKED_MARKER} names the block.", file=sys.stderr)
        return EXIT_OK
    append_event(repo / LOG, {"event": "stop_blocked", "failed_gates": failed})
    names = ", ".join(failed) or "unknown"
    print(f"Gates failing: {names}. Fix them before stopping.", file=sys.stderr)
    print(proc.stderr[-4000:], file=sys.stderr)
    return EXIT_BLOCK


def main() -> int:
    return stop(PROJECT_ROOT, repo_root(PROJECT_ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
