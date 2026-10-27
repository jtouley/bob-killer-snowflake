"""verify/stage.py: two parity channels, the equivalence report, and when the run fails (§5.4)."""

from __future__ import annotations

from typing import Any

import pytest

from bob_killer import registry
from bob_killer.contracts.ir import CellValue
from bob_killer.contracts.report import CellMismatch, EquivalenceReport
from bob_killer.verify import stage

RUN_ID = "ef" * 16


def _ir() -> Any:
    from bob_killer.hosts.snowflake.reviews import lifted
    from tests.conftest import golden_workbook

    return lifted(golden_workbook("mt_dot_budget"))


def _mismatch(ir: Any) -> CellMismatch:
    ref = ir.steps[0].cells()[0]
    return CellMismatch(
        sheet=ref.sheet,
        cell_row=ref.row,
        cell_col=ref.col,
        expected=CellValue.number(1.0),
        actual=CellValue.number(2.0),
    )


class FakeIO:
    def __init__(self, checked: int, mismatches: tuple[CellMismatch, ...], failures: Any) -> None:
        self.ir = _ir()
        self.checked, self.mismatches, self.failures = checked, mismatches, failures
        self.reports: list[EquivalenceReport] = []

    def load_ir(self, run_id: str) -> Any:
        return self.ir

    def compare(self, run_id: str) -> tuple[int, tuple[CellMismatch, ...]]:
        return self.checked, self.mismatches

    def parity_failures(self, run_id: str) -> Any:
        return self.failures

    def write_report(self, report: EquivalenceReport) -> None:
        self.reports.append(report)


def _cells(ir: Any) -> int:
    return sum(len(s.cells()) for s in ir.steps)


def test_every_cell_matching_writes_a_clean_report_and_succeeds() -> None:
    io = FakeIO(_cells(_ir()), (), ())
    stage.verify_stage(io)(RUN_ID)
    (report,) = io.reports
    assert report.cells_matched == report.cells_checked == report.denominator == _cells(io.ir)
    assert report.mismatches.cells == ()
    assert report.channels_agree is True
    assert report.workbook_sha256 == io.ir.source.sha256


def test_a_mismatch_in_both_channels_is_reported_and_fails_the_run() -> None:
    ir = _ir()
    m = _mismatch(ir)
    io = FakeIO(_cells(ir), (m,), ((m.sheet, m.cell_row, m.cell_col),))
    with pytest.raises(stage.ParityMismatch):
        stage.verify_stage(io)(RUN_ID)
    (report,) = io.reports
    assert report.mismatches.cells == (m,)
    assert report.cells_matched == report.cells_checked - len([m])
    assert report.channels_agree is True
    assert report.parity_test_failures == len([m])


@pytest.mark.parametrize("side", ["dbt-only", "verify-only"])
def test_channels_that_disagree_fail_the_run(side: str) -> None:
    ir = _ir()
    m = _mismatch(ir)
    key = (m.sheet, m.cell_row, m.cell_col)
    mismatches, failures = ((), (key,)) if side == "dbt-only" else ((m,), ())
    io = FakeIO(_cells(ir), mismatches, failures)
    with pytest.raises(stage.ParityChannelsDisagree):
        stage.verify_stage(io)(RUN_ID)
    (report,) = io.reports
    assert report.channels_agree is False


def test_fewer_cells_checked_than_the_denominator_fails() -> None:
    io = FakeIO(_cells(_ir()) - len([None]), (), ())
    with pytest.raises(stage.ParityMismatch):
        stage.verify_stage(io)(RUN_ID)


def test_the_denominator_keeps_unsupported_formula_cells() -> None:
    from bob_killer.contracts.ir import Unsupported

    ir = _ir()
    extra = Unsupported(kind=stage.FORMULA, origin=ir.steps[0].origin[0], reason="test")
    wider = ir.model_copy(update={"unsupported": (*ir.unsupported, extra)})
    assert stage.denominator(wider) == stage.denominator(ir) + len([extra])


def test_register_stages_is_idempotent() -> None:
    io = FakeIO(0, (), ())
    stage.register_stages(io)
    stage.register_stages(io)
    assert registry.stages.names() == (stage.STAGE_NAME,)
