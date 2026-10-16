"""Tests actually bite: mutmut on runtime/ must kill at least 80% of mutants (nightly)."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from bk_gates.core import GateContext, Violation, gate
from bk_gates.tooling import has_statements

MIN_KILLED = 0.8
RUNTIME = Path("src/bob_killer/runtime")
STATS = Path("mutants/mutmut-cicd-stats.json")


def mutation_violations(stats: Mapping[str, int]) -> list[Violation]:
    killed = stats.get("killed", 0)
    scored = killed + stats.get("survived", 0) + stats.get("no_tests", 0)
    if scored == 0:
        return []  # vacuous: no mutants (G10)
    score = killed / scored
    if score < MIN_KILLED:
        return [
            Violation(
                "mutation/below-threshold",
                f"{killed}/{scored} mutants killed ({score:.0%} < {MIN_KILLED:.0%})",
            )
        ]
    return []


@gate("mutation", nightly_only=True)
def check(ctx: GateContext) -> list[Violation]:
    root = ctx.project_root
    if not (root / RUNTIME).is_dir() or not has_statements(root / RUNTIME):
        return []
    mutmut = str(Path(sys.executable).parent / "mutmut")
    subprocess.run([mutmut, "run"], cwd=root, check=False, capture_output=True)
    subprocess.run([mutmut, "export-cicd-stats"], cwd=root, check=True, capture_output=True)
    return mutation_violations(json.loads((root / STATS).read_text()))
