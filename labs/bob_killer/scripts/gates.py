"""Run Bob Killer's anti-cheat gates. Exit 0 only when every selected gate passes.

uv run python scripts/gates.py                    # all PR gates, base = merge-base with main
uv run python scripts/gates.py --only tdd_order --base origin/main
uv run python scripts/gates.py --nightly          # also the nightly-only gates (mutation)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from bk_gates.core import GateContext, Violation, load_gates
from bk_gates.tdd_common import PROJECT_ROOT, repo_root

ZERO_SHA = "0" * 40


def default_base(repo: Path) -> str | None:
    for ref in ("origin/main", "main"):
        out = subprocess.run(
            ["git", "merge-base", "HEAD", ref], cwd=repo, capture_output=True, text=True
        )
        if out.returncode == 0:
            return out.stdout.strip()
    return None


def main(argv: list[str] | None = None) -> int:
    gates = load_gates()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", choices=sorted(gates))
    parser.add_argument("--base", help="base revision for history gates")
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--nightly", action="store_true")
    args = parser.parse_args(argv)

    repo = args.repo_root or repo_root(args.project_root)
    base = args.base if args.base and args.base != ZERO_SHA else default_base(repo)
    ctx = GateContext(repo_root=repo, project_root=args.project_root, base=base)
    selected = args.only or [
        n for n, g in sorted(gates.items()) if args.nightly or not g.nightly_only
    ]

    failed = False
    for name in selected:
        try:
            violations = gates[name].check(ctx)
        except Exception as exc:  # a crashing gate is a failing gate
            violations = [Violation(f"{name}/crashed", f"{type(exc).__name__}: {exc}")]
        if violations:
            failed = True
            print(f"FAIL  {name}", file=sys.stderr)
            for v in violations:
                print(f"  {v.rule}: {v.message}", file=sys.stderr)
        else:
            print(f"OK    {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
