"""Red before green: commit phases, red-run evidence and gate-file protection.

SPEC gate "Red before green" plus adversarial conditions C1, C2, C5 and C7.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import PurePosixPath

from bk_gates.core import GateContext, Violation, gate
from bk_gates.git_history import Commit, changed_paths, commits_in_range, file_at, files_under
from bk_gates.tdd_common import digest_tests_tree, parse_junit

PHASE_TRAILER = "TDD-Phase"
PHASES = frozenset({"red", "green", "refactor", "scaffold", "gate-change"})
GATE_PATHS = ("scripts/bk_gates/", "scripts/gates.py", "scripts/record_run.py")
RED_HELPER_NAMES = frozenset({"conftest.py", "__init__.py", "oracle_values.py"})
RUN_RECORD = re.compile(r"\.context/runs/[^/]+/run\.json")


def is_code(rel: str) -> bool:
    return rel.endswith(".py") and rel.startswith(("src/", "scripts/"))


def is_trivial_module(source: bytes) -> bool:
    """True for an empty module or one holding only a docstring."""
    body = ast.parse(source).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return not body


def _touches_project(commit: Commit, prefix: str) -> bool:
    return any(ch.path.startswith(prefix) or ch.source.startswith(prefix) for ch in commit.changes)


def _red_record_ok(ctx: GateContext, commit: Commit) -> str | None:
    """None when the commit carries an honest failing run for its tests tree, else a rule id."""
    records = [
        ch.path for ch in commit.changes if ch.status in "AM" and RUN_RECORD.fullmatch(ch.path)
    ]
    if not records:
        return "tdd_order/red-no-run-record"
    tests_prefix = f"{ctx.prefix}tests/"
    digest = digest_tests_tree(files_under(ctx.repo_root, commit.sha, tests_prefix))
    for record in records:
        raw = file_at(ctx.repo_root, commit.sha, record)
        junit = file_at(ctx.repo_root, commit.sha, str(PurePosixPath(record).parent / "junit.xml"))
        if raw is None or junit is None:
            continue
        data = json.loads(raw)
        nodes = data.get("nodes", {})
        honest = (
            data.get("tdd_phase") == "red"
            and data.get("tests_tree_sha256") == digest
            and data.get("junit_sha256") == hashlib.sha256(junit).hexdigest()
            and parse_junit(junit) == nodes
            and any(outcome in ("failed", "error") for outcome in nodes.values())
        )
        if honest:
            return None
    return "tdd_order/red-run-mismatch"


def _check_commit(
    ctx: GateContext, commit: Commit, phase: str, pending_red: bool
) -> tuple[list[Violation], bool]:
    prefix = ctx.prefix
    short = commit.sha[:8]
    project = [ch for ch in commit.changes if ch.path.startswith(prefix)]
    rel = {ch: ch.path[len(prefix) :] for ch in project}
    out: list[Violation] = []

    if phase != "gate-change":
        for ch in project:
            source = ch.source[len(prefix) :]
            if ch.status in "MDR" and source.startswith(GATE_PATHS):
                out.append(
                    Violation(
                        "tdd_order/gate-path-modified",
                        f"{short} changes gate file {source} without TDD-Phase: gate-change",
                    )
                )

    touches_code = any(is_code(r) for r in rel.values())
    if phase == "scaffold":
        for ch, r in rel.items():
            if ch.status in "AMR" and is_code(r):
                content = file_at(ctx.repo_root, commit.sha, ch.path) or b""
                if not is_trivial_module(content):
                    out.append(
                        Violation("tdd_order/scaffold-code", f"{short} scaffold adds logic to {r}")
                    )
    elif phase == "red":
        for ch, r in rel.items():
            if not r.startswith("tests/"):
                out.append(Violation("tdd_order/red-touches-code", f"{short} red commit edits {r}"))
            elif ch.status == "A" and r.endswith(".py"):
                name = PurePosixPath(r).name
                if not name.startswith("test_") and name not in RED_HELPER_NAMES:
                    out.append(
                        Violation(
                            "tdd_order/red-non-test-module",
                            f"{short} red commit adds non-test module {r}",
                        )
                    )
        rule = _red_record_ok(ctx, commit)
        if rule is None:
            pending_red = True
        else:
            out.append(Violation(rule, f"{short} red commit lacks an honest failing run record"))
    elif phase == "green" and touches_code:
        if not pending_red:
            out.append(
                Violation(
                    "tdd_order/green-without-red", f"{short} green code change with no prior red"
                )
            )
        pending_red = False
    return out, pending_red


@gate("tdd_order")
def check(ctx: GateContext) -> list[Violation]:
    if ctx.base is None:
        return [Violation("tdd_order/no-base", "no base revision to compare against")]
    prefix = ctx.prefix
    commits = [
        c
        for c in commits_in_range(ctx.repo_root, ctx.base, ctx.head)
        if _touches_project(c, prefix)
    ]
    start = next((i for i, c in enumerate(commits) if PHASE_TRAILER in c.trailers), None)
    if start is None:
        code = [
            p
            for p in changed_paths(ctx.repo_root, ctx.base, ctx.head)
            if p.startswith(prefix) and is_code(p[len(prefix) :])
        ]
        if code:
            return [
                Violation(
                    "tdd_order/empty-range",
                    f"code changed ({code[0]}...) but no TDD-Phase commits in range",
                )
            ]
        return []

    violations: list[Violation] = []
    pending_red = False
    for commit in commits[start:]:
        phase = commit.trailers.get(PHASE_TRAILER)
        if phase is None:
            violations.append(
                Violation("tdd_order/missing-trailer", f"{commit.sha[:8]} has no TDD-Phase")
            )
            continue
        if phase not in PHASES:
            violations.append(
                Violation("tdd_order/unknown-phase", f"{commit.sha[:8]} has phase {phase!r}")
            )
            continue
        found, pending_red = _check_commit(ctx, commit, phase, pending_red)
        violations.extend(found)
    return violations
