"""Tests untouched in green: asserts, test functions and oracle data are frozen (C3, PR-3)."""

from __future__ import annotations

import ast

from bk_gates.core import GateContext, Violation, gate
from bk_gates.git_history import Change, Commit, commits_in_range, file_at

FROZEN_PHASES = frozenset({"green", "refactor", "gate-change"})
ORACLE_PATHS = ("oracle/", "oracle_values.py")

TestAsserts = dict[str, list[str]]


def test_functions(source: bytes | None) -> TestAsserts | None:
    """Map qualified test-function name to its assert nodes; None if unparseable."""
    if source is None:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    found: TestAsserts = {}

    def visit(body: list[ast.stmt], owner: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, f"{owner}{node.name}.")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
                "test"
            ):
                found[f"{owner}{node.name}"] = [
                    ast.dump(n, include_attributes=False)
                    for n in ast.walk(node)
                    if isinstance(n, ast.Assert)
                ]

    visit(tree.body, "")
    return found


def _check_change(
    ctx: GateContext, commit: Commit, phase: str, ch: Change, tests_prefix: str
) -> list[Violation]:
    rel = ch.source[len(tests_prefix) :]
    short = commit.sha[:8]
    if phase == "gate-change" and rel.startswith("gates/"):
        return []
    out: list[Violation] = []
    if ch.status in "MDR" and rel.startswith(ORACLE_PATHS):
        out.append(Violation("assertions_frozen/oracle-modified", f"{short} changes {rel}"))
    if not ch.path.endswith(".py"):
        return out
    old = (
        test_functions(file_at(ctx.repo_root, f"{commit.sha}^", ch.source))
        if ch.status in "MDR"
        else {}
    )
    new = test_functions(file_at(ctx.repo_root, commit.sha, ch.path)) if ch.status != "D" else {}
    if old is None or new is None:
        return [*out, Violation("assertions_frozen/assert-modified", f"{short} {rel} unparseable")]
    for name, asserts in old.items():
        if name not in new:
            out.append(
                Violation("assertions_frozen/test-removed", f"{short} removes {rel}::{name}")
            )
        elif new[name] != asserts:
            out.append(
                Violation("assertions_frozen/assert-modified", f"{short} changes {rel}::{name}")
            )
    if phase == "green":
        for name in new.keys() - old.keys():
            out.append(
                Violation("assertions_frozen/green-adds-tests", f"{short} adds {rel}::{name}")
            )
    return out


@gate("assertions_frozen")
def check(ctx: GateContext) -> list[Violation]:
    if ctx.base is None:
        return [Violation("assertions_frozen/no-base", "no base revision to compare against")]
    tests_prefix = f"{ctx.prefix}tests/"
    violations: list[Violation] = []
    for commit in commits_in_range(ctx.repo_root, ctx.base, ctx.head):
        phase = commit.trailers.get("TDD-Phase", "")
        if phase == "squash":
            from bk_gates.tdd_order import squash_history  # tdd_order reports squash errors

            history, _ = squash_history(ctx, commit)
            if history is not None:
                violations.extend(check(history))
            continue
        if phase not in FROZEN_PHASES:
            continue
        for ch in commit.changes:
            if ch.source.startswith(tests_prefix):
                violations.extend(_check_change(ctx, commit, phase, ch, tests_prefix))
    return violations
