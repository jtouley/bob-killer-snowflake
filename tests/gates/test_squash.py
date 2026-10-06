"""Squash with archived history: a squash commit is checked against the history it replaces."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

import pytest

from bk_gates.core import load_gates
from tests.gates.conftest import History
from tests.gates.test_history_gates import FAILED, IMPL, TEST_LOOSE, TEST_V1, S, T, clean, scaffold


def _git(h: History, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=h.root, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def squash(h: History, history_ref: str = "HEAD", *, extra: dict[str, str] | None = None) -> None:
    """Archive the current branch, then replace base..HEAD with one squash commit."""
    archived = _git(h, "rev-parse", history_ref)
    _git(h, "tag", "archive", archived)
    _git(h, "reset", "-q", "--soft", h.base)
    h.commit(extra or {}, phase="squash", trailers={"TDD-History": archived})


def honest_squash(h: History) -> None:
    clean(h)
    squash(h)


def squash_hides_cheat(h: History) -> None:
    scaffold(h)
    h.commit({S: IMPL}, phase="green")
    squash(h)


def squash_hides_loosened_assert(h: History) -> None:
    scaffold(h)
    h.red({T: TEST_V1}, FAILED)
    h.commit({S: IMPL, T: TEST_LOOSE}, phase="green")
    squash(h)


def squash_tree_differs(h: History) -> None:
    clean(h)
    squash(h, extra={"proj/src/pkg/sneaky.py": "def f() -> int:\n    return 1\n"})


def squash_history_missing(h: History) -> None:
    clean(h)
    h.commit({}, phase="squash", trailers={"TDD-History": "0" * 40})


def squash_without_history_trailer(h: History) -> None:
    clean(h)
    _git(h, "reset", "-q", "--soft", h.base)
    h.commit({}, phase="squash")


def squash_history_not_descendant(h: History) -> None:
    clean(h)
    archived = _git(h, "rev-parse", "HEAD")
    _git(h, "checkout", "-q", "--orphan", "other")
    _git(h, "rm", "-rqf", ".")
    h.commit({"README.md": "base\n"}, phase=None)
    unrelated = _git(h, "rev-parse", "HEAD")
    _git(h, "checkout", "-q", "main")
    _git(h, "reset", "-q", "--hard", archived)
    _git(h, "reset", "-q", "--soft", h.base)
    h.commit({}, phase="squash", trailers={"TDD-History": unrelated})


Builder = Callable[[History], None]

CHEATS: list[tuple[Builder, str]] = [
    (squash_hides_cheat, "tdd_order/green-without-red"),
    (squash_hides_loosened_assert, "assertions_frozen/assert-modified"),
    (squash_tree_differs, "tdd_order/squash-tree-mismatch"),
    (squash_history_missing, "tdd_order/squash-history-missing"),
    (squash_without_history_trailer, "tdd_order/squash-history-missing"),
    (squash_history_not_descendant, "tdd_order/squash-not-descendant"),
]


def _rules(h: History) -> set[str]:
    gates = load_gates()
    return {
        v.rule
        for name in ("tdd_order", "assertions_frozen")
        for v in gates[name].check(h.context())
    }


def test_honest_squash_passes(history: History) -> None:
    honest_squash(history)
    assert _rules(history) == set()


@pytest.mark.parametrize(("build", "rule"), CHEATS, ids=[b.__name__ for b, _ in CHEATS])
def test_squash_cheat_rejected(history: History, build: Builder, rule: str) -> None:
    build(history)
    assert rule in _rules(history)
