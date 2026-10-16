"""service/runs.py: stage detail (D3), the claim path (G24) and errors outside a stage (G9a)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

from bob_killer import registry
from bob_killer.contracts.runs import RunState, StageState
from bob_killer.service.runs import execute_run
from tests.conftest import queued_run, sample_run

if TYPE_CHECKING:
    from bob_killer.store import RunRepository


@pytest.mark.parametrize("returns_text", [True, False], ids=["text", "none"])
def test_stage_return_is_the_success_detail(store: RunRepository, returns_text: bool) -> None:
    def stage(run_id: str) -> str | None:
        return f"landed {run_id}" if returns_text else None

    registry.stages.add(stage.__name__, stage)
    run = queued_run(store)
    execute_run(store, run.run_id)
    (status,) = store.stages(run.run_id)
    assert status.state == StageState.SUCCEEDED
    assert status.detail == (stage(run.run_id) or "")


class _Faulty:
    """Delegates to the real store; ``method`` raises RuntimeError when ``when(*args)`` is true."""

    def __init__(self, inner: RunRepository, method: str, when: Callable[..., bool]) -> None:
        self._inner, self._method, self._when = inner, method, when

    def __getattr__(self, name: str) -> object:
        real = getattr(self._inner, name)
        if name != self._method:
            return real

        def call(*args: object) -> object:
            if self._when(*args):
                raise RuntimeError(name)
            return real(*args)

        return call


def _counting_stage() -> list[str]:
    """Register one stage that records each run id it is called with."""
    calls: list[str] = []

    def counting(run_id: str) -> None:
        calls.append(run_id)

    registry.stages.add(counting.__name__, counting)
    return calls


def test_second_execute_runs_no_stage_and_writes_nothing(store: RunRepository) -> None:
    """G24: only the call that wins the claim runs the stages."""
    calls = _counting_stage()
    run = queued_run(store)
    first = execute_run(store, run.run_id)
    after_first = store.stages(run.run_id)
    second = execute_run(store, run.run_id)
    assert first == second == RunState.SUCCEEDED
    assert calls == [run.run_id]
    assert store.stages(run.run_id) == after_first


def test_execute_unknown_run_raises_key_error(store: RunRepository) -> None:
    missing = sample_run().run_id
    with pytest.raises(KeyError, match=missing):
        execute_run(store, missing)


@pytest.mark.parametrize(
    ("method", "when"),
    [
        ("upsert_stage", lambda status: True),
        ("set_state", lambda run_id, state: state == RunState.SUCCEEDED),
    ],
    ids=["upsert-after-claim", "final-set-state"],
)
def test_error_outside_a_stage_fails_the_run_and_raises(
    store: RunRepository, method: str, when: Callable[..., bool]
) -> None:
    """G9a (a) and (c): after a won claim, an error outside a stage gives failed and re-raises."""
    _counting_stage()
    run = queued_run(store)
    with pytest.raises(RuntimeError, match=method):
        execute_run(_Faulty(store, method, when), run.run_id)  # type: ignore[arg-type]
    fetched = store.get_run(run.run_id)
    assert fetched is not None
    assert fetched.state == RunState.FAILED


def test_error_after_a_lost_claim_writes_nothing(store: RunRepository) -> None:
    """G9a (b): a call that lost the claim propagates its error and leaves the state alone."""
    run = queued_run(store)
    assert execute_run(store, run.run_id) == RunState.SUCCEEDED
    with pytest.raises(RuntimeError, match="get_run"):
        execute_run(_Faulty(store, "get_run", lambda run_id: True), run.run_id)  # type: ignore[arg-type]
    fetched = store.get_run(run.run_id)
    assert fetched is not None
    assert fetched.state == RunState.SUCCEEDED
