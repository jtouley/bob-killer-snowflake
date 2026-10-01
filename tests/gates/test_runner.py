"""scripts/gates.py: one registry, exit codes, rule ids on stderr."""

from __future__ import annotations

import pytest

from bk_gates.core import load_gates
from gates import main
from tests.gates.conftest import History

EXPECTED_HISTORY_GATES = {"tdd_order", "assertions_frozen"}


def _argv(h: History, *extra: str) -> list[str]:
    return ["--repo-root", str(h.root), "--project-root", str(h.project), "--base", h.base, *extra]


def test_registry_has_history_gates() -> None:
    assert EXPECTED_HISTORY_GATES <= set(load_gates())


def test_clean_history_exits_zero(history: History) -> None:
    history.commit({"proj/src/pkg/__init__.py": ""}, phase="scaffold")
    assert main(_argv(history, "--only", "tdd_order", "--only", "assertions_frozen")) == 0


def test_cheat_exits_one_with_rule_id(history: History, capsys: pytest.CaptureFixture[str]) -> None:
    history.commit({"proj/src/pkg/calc.py": "def f() -> int:\n    return 1\n"}, phase="green")
    assert main(_argv(history, "--only", "tdd_order")) == 1
    assert "tdd_order/green-without-red" in capsys.readouterr().err


def test_unknown_gate_is_usage_error(history: History) -> None:
    with pytest.raises(SystemExit) as exc:
        main(_argv(history, "--only", "no_such_gate"))
    assert exc.value.code == 2
