"""Cheat fixtures for history gates: each must be rejected with its exact rule id (TB-2/TB-3)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from bk_gates.core import load_gates
from tests.gates.conftest import History

TEST_V1 = "def test_add():\n    assert add(1, 2) == expected()\n"
TEST_LOOSE = "def test_add():\n    assert add(1, 2) >= 0\n"
TEST_RENAMED = "def test_add_renamed():\n    assert add(1, 2) == expected()\n"
TEST_REFACTORED = "HELPER = 1\n\n\ndef test_add():\n    assert add(1, 2) == expected()\n"
IMPL = "def add(a: int, b: int) -> int:\n    return a + b\n"
IMPL_V2 = "def add(a: int, b: int) -> int:\n    total = a + b\n    return total\n"
FAILED = {"tests.test_add::test_add": "failed"}

T = "proj/tests/test_add.py"
S = "proj/src/pkg/calc.py"


def scaffold(h: History) -> None:
    h.commit({"proj/src/pkg/__init__.py": '"""pkg."""\n'}, phase="scaffold")


def clean(h: History) -> None:
    scaffold(h)
    h.red({T: TEST_V1}, FAILED)
    h.commit({S: IMPL}, phase="green")
    h.commit({S: IMPL_V2, T: TEST_REFACTORED}, phase="refactor")


def bootstrap(h: History) -> None:
    h.commit({"proj/src/legacy.py": "X = 1\n"}, phase=None)
    clean(h)


def merge(h: History) -> None:
    clean(h)
    h_git = h.root
    import subprocess

    subprocess.run(["git", "checkout", "-q", "-b", "side"], cwd=h_git, check=True)
    h.commit({"proj/docs.md": "x\n"}, phase="scaffold")
    subprocess.run(["git", "checkout", "-q", "main"], cwd=h_git, check=True)
    subprocess.run(
        ["git", "merge", "-q", "--no-ff", "-m", "merge\n\nTDD-Phase: scaffold", "side"],
        cwd=h_git,
        check=True,
    )


def gate_change(h: History) -> None:
    h.commit({"proj/scripts/bk_gates/x.py": "A = 1\n"}, phase="gate-change")
    h.commit({"proj/scripts/bk_gates/x.py": "A = 2\n"}, phase="gate-change")


def impl_and_test_one_commit(h: History) -> None:
    scaffold(h)
    h.commit({T: TEST_V1, S: IMPL}, phase="green")


def green_without_red(h: History) -> None:
    scaffold(h)
    h.commit({S: IMPL}, phase="green")


def second_green_without_red(h: History) -> None:
    clean(h)
    h.commit({"proj/src/pkg/more.py": IMPL}, phase="green")


def red_touches_code(h: History) -> None:
    scaffold(h)
    h.red({T: TEST_V1, S: IMPL}, FAILED)


def red_no_record(h: History) -> None:
    scaffold(h)
    h.commit({T: TEST_V1}, phase="red")


def red_passing_record(h: History) -> None:
    scaffold(h)
    h.red({T: TEST_V1}, {"tests.test_add::test_add": "passed"})


def red_forged_nodes(h: History) -> None:
    scaffold(h)
    h.write({T: TEST_V1})
    path = h.record(FAILED)
    import json

    run = h.root / path
    data = json.loads(run.read_text())
    data["nodes"]["tests.test_add::test_other"] = "failed"
    run.write_text(json.dumps(data))
    h.commit({}, phase="red")


def red_stale_digest(h: History) -> None:
    scaffold(h)
    h.write({T: TEST_V1})
    h.record(FAILED)
    h.commit({T: TEST_V1 + "\n# edited after recording\n"}, phase="red")


def red_non_test_module(h: History) -> None:
    scaffold(h)
    h.red({T: TEST_V1, "proj/tests/helpers.py": "def expected():\n    return 3\n"}, FAILED)


def scaffold_with_code(h: History) -> None:
    h.commit({S: IMPL}, phase="scaffold")


def missing_trailer(h: History) -> None:
    clean(h)
    h.commit({S: IMPL}, phase=None)


def unknown_phase(h: History) -> None:
    h.commit({S: IMPL}, phase="yolo")


def gate_path_modified(h: History) -> None:
    h.commit({"proj/scripts/bk_gates/x.py": "A = 1\n"}, phase="gate-change")
    h.red({T: TEST_V1}, FAILED)
    h.commit({"proj/scripts/bk_gates/x.py": "A = 2\n"}, phase="green")


def empty_range(h: History) -> None:
    h.commit({S: IMPL}, phase=None)


def loosen_assert(h: History) -> None:
    scaffold(h)
    h.red({T: TEST_V1}, FAILED)
    h.commit({S: IMPL, T: TEST_LOOSE}, phase="green")


def rename_test(h: History) -> None:
    scaffold(h)
    h.red({T: TEST_V1}, FAILED)
    h.commit({S: IMPL, T: TEST_RENAMED}, phase="green")


def delete_test_file(h: History) -> None:
    clean(h)
    h.commit({T: None}, phase="refactor")


def oracle_modified(h: History) -> None:
    scaffold(h)
    h.red({T: TEST_V1, "proj/tests/oracle/add.json": '{"v": 3}'}, FAILED)
    h.commit({S: IMPL, "proj/tests/oracle/add.json": '{"v": 4}'}, phase="green")


def green_adds_tests(h: History) -> None:
    clean(h)
    h.red({"proj/tests/test_sub.py": TEST_V1.replace("add", "sub")}, FAILED)
    extra = TEST_V1 + "\n\ndef test_extra():\n    assert add(0, 0) == expected()\n"
    h.commit({S: IMPL_V2 + "\n", T: extra}, phase="green")


Builder = Callable[[History], None]

CONTROLS: list[Builder] = [clean, bootstrap, merge, gate_change]

CHEATS: list[tuple[Builder, str]] = [
    (impl_and_test_one_commit, "tdd_order/green-without-red"),
    (green_without_red, "tdd_order/green-without-red"),
    (second_green_without_red, "tdd_order/green-without-red"),
    (red_touches_code, "tdd_order/red-touches-code"),
    (red_no_record, "tdd_order/red-no-run-record"),
    (red_passing_record, "tdd_order/red-run-mismatch"),
    (red_forged_nodes, "tdd_order/red-run-mismatch"),
    (red_stale_digest, "tdd_order/red-run-mismatch"),
    (red_non_test_module, "tdd_order/red-non-test-module"),
    (scaffold_with_code, "tdd_order/scaffold-code"),
    (missing_trailer, "tdd_order/missing-trailer"),
    (unknown_phase, "tdd_order/unknown-phase"),
    (gate_path_modified, "tdd_order/gate-path-modified"),
    (empty_range, "tdd_order/empty-range"),
    (loosen_assert, "assertions_frozen/assert-modified"),
    (rename_test, "assertions_frozen/test-removed"),
    (delete_test_file, "assertions_frozen/test-removed"),
    (oracle_modified, "assertions_frozen/oracle-modified"),
    (impl_and_test_one_commit, "assertions_frozen/green-adds-tests"),
    (green_adds_tests, "assertions_frozen/green-adds-tests"),
]

HISTORY_GATES = ("tdd_order", "assertions_frozen")


def _rules(h: History) -> set[str]:
    gates = load_gates()
    ctx = h.context()
    return {v.rule for name in HISTORY_GATES for v in gates[name].check(ctx)}


@pytest.mark.parametrize("build", CONTROLS, ids=lambda b: b.__name__)
def test_honest_history_passes(history: History, build: Builder) -> None:
    build(history)
    assert _rules(history) == set()


@pytest.mark.parametrize(
    ("build", "rule"), CHEATS, ids=[f"{b.__name__}-{r.split('/')[0]}" for b, r in CHEATS]
)
def test_cheat_is_rejected(history: History, build: Builder, rule: str) -> None:
    build(history)
    assert rule in _rules(history)
