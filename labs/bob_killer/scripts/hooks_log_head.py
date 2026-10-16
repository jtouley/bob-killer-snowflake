"""Print the current .context/hooks.log chain head, for the Hooks-Log-Head commit trailer.

git commit --trailer "Hooks-Log-Head=$(uv run python scripts/hooks_log_head.py)"
"""

from __future__ import annotations

from bk_gates.hook_log import LOG, chain_head
from bk_gates.tdd_common import PROJECT_ROOT, repo_root


def main() -> int:
    path = repo_root(PROJECT_ROOT) / LOG
    print(chain_head(path.read_text(encoding="utf-8") if path.is_file() else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
