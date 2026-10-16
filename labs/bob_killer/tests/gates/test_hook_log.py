"""append_only_log: hash-chained .context/hooks.log, anchored in commit trailers (C4, TB-5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bk_gates.core import load_gates
from bk_gates.hook_log import GENESIS, append_event, chain_head, verify_chain
from tests.gates.conftest import History

LOG = ".context/hooks.log"
events = st.lists(
    st.dictionaries(st.sampled_from(["event", "file", "result"]), st.text(max_size=8)),
    min_size=2,
    max_size=8,
)


def _write_log(path: Path, evs: list[dict[str, str]]) -> str:
    for ev in evs:
        append_event(path, ev)
    return path.read_text()


@given(events)
def test_appended_log_verifies(evs: list[dict[str, str]]) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        text = _write_log(Path(d) / "hooks.log", evs)
    assert verify_chain(text) is None


@given(events, st.data())
def test_editing_any_non_last_line_breaks_chain(
    evs: list[dict[str, str]], data: st.DataObject
) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        lines = _write_log(Path(d) / "hooks.log", evs).splitlines()
    i = data.draw(st.integers(min_value=0, max_value=len(lines) - 2))
    lines[i] = lines[i] + " "
    assert verify_chain("\n".join(lines) + "\n") is not None


def test_empty_log_head_is_genesis() -> None:
    assert chain_head("") == GENESIS


def test_append_returns_new_head(tmp_path: Path) -> None:
    path = tmp_path / "hooks.log"
    head = append_event(path, {"event": "x"})
    assert head == chain_head(path.read_text())


def _append(h: History, event: str) -> str:
    return append_event(h.root / LOG, {"event": event})


def anchored(h: History) -> None:
    h.commit({}, phase="scaffold", trailers={"Hooks-Log-Head": _append(h, "a")})
    h.commit({}, phase="scaffold", trailers={"Hooks-Log-Head": _append(h, "b")})


def edit_middle(h: History) -> None:
    anchored(h)
    _append(h, "c")
    path = h.root / LOG
    lines = path.read_text().splitlines()
    lines[0] = lines[0].replace('"a"', '"z"')
    path.write_text("\n".join(lines) + "\n")
    h.commit({}, phase="scaffold", trailers={"Hooks-Log-Head": chain_head(path.read_text())})


def full_recompute(h: History) -> None:
    anchored(h)
    (h.root / LOG).unlink()
    _append(h, "z")
    head = _append(h, "b")
    h.commit({}, phase="scaffold", trailers={"Hooks-Log-Head": head})


def missing_anchor(h: History) -> None:
    anchored(h)
    _append(h, "c")
    h.commit({}, phase="scaffold")


def wrong_anchor(h: History) -> None:
    anchored(h)
    _append(h, "c")
    h.commit({}, phase="scaffold", trailers={"Hooks-Log-Head": GENESIS})


def deleted(h: History) -> None:
    anchored(h)
    h.commit({LOG: None}, phase="scaffold")


def uncommitted_rewrite(h: History) -> None:
    anchored(h)
    path = h.root / LOG
    path.write_text(path.read_text().splitlines()[0] + "\n")


def last_line_edit_uncommitted(h: History) -> None:
    anchored(h)
    path = h.root / LOG
    lines = path.read_text().splitlines()
    lines[-1] = lines[-1].replace('"b"', '"q"')
    path.write_text("\n".join(lines) + "\n")


CHEATS = [
    (edit_middle, "append_only_log/rewritten"),
    (full_recompute, "append_only_log/rewritten"),
    (missing_anchor, "append_only_log/missing-anchor"),
    (wrong_anchor, "append_only_log/anchor-mismatch"),
    (deleted, "append_only_log/rewritten"),
    (uncommitted_rewrite, "append_only_log/rewritten"),
    (last_line_edit_uncommitted, "append_only_log/rewritten"),
]


def _rules(h: History) -> set[str]:
    return {v.rule for v in load_gates()["append_only_log"].check(h.context())}


def test_anchored_log_passes(history: History) -> None:
    anchored(history)
    assert _rules(history) == set()


def test_no_log_passes(history: History) -> None:
    assert _rules(history) == set()


@pytest.mark.parametrize(("build", "rule"), CHEATS, ids=[b.__name__ for b, _ in CHEATS])
def test_cheat_is_rejected(history: History, build: object, rule: str) -> None:
    assert callable(build)
    build(history)
    assert rule in _rules(history)
