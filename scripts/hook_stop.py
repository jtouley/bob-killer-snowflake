"""Claude Code Stop hook: the agent cannot finish while any gate fails (exit 2 blocks).

A blocked stop is appended to the chained .context/hooks.log with the failed gate names.
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


def stop(project_root: Path, repo: Path, gates_cmd: list[str] | None = None) -> int:
    cmd = gates_cmd or [sys.executable, str(project_root / "scripts" / "gates.py")]
    proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return EXIT_OK
    failed = FAILED.findall(proc.stderr)
    append_event(repo / LOG, {"event": "stop_blocked", "failed_gates": failed})
    names = ", ".join(failed) or "unknown"
    print(f"Gates failing: {names}. Fix them before stopping.", file=sys.stderr)
    print(proc.stderr[-4000:], file=sys.stderr)
    return EXIT_BLOCK


def main() -> int:
    return stop(PROJECT_ROOT, repo_root(PROJECT_ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
