"""The ``verify`` stage: two independent parity channels and the equivalence report (§5.4).

Channel (a) is what the dbt parity test stored as failing cells; channel (b) is the host's own
compare of every computed cell with Excel's cached value through the one comparator
(``BK_VALUES_EQUAL``, ``values_equal``). The report is written in every case. The stage fails
when the channels disagree (a broken seed encoding or UDF) or when any cell mismatches.
The denominator is every formula cell the IR computes plus every unsupported formula cell
(L12: unsupported cells stay in the denominator and fail until supported).
"""

from __future__ import annotations

from typing import Final, Protocol

from bob_killer import registry
from bob_killer.contracts.ir import WorkbookIR
from bob_killer.contracts.report import CellMismatch, EquivalenceReport, Mismatches
from bob_killer.registry import Stage

STAGE_NAME: Final = "verify"
FORMULA = "formula"  # the Unsupported kind of a formula cell (lift)

CellKey = tuple[str, int, int]


class ParityChannelsDisagree(RuntimeError):
    """The dbt parity test and the verify compare name different mismatched cells."""


class ParityMismatch(RuntimeError):
    """A computed cell differs from Excel's cached value (or one side is missing)."""


class VerifyIO(Protocol):
    def load_ir(self, run_id: str) -> WorkbookIR: ...

    def compare(self, run_id: str) -> tuple[int, tuple[CellMismatch, ...]]:
        """Channel (b): the number of cells compared and the ones that are not equal."""
        ...

    def parity_failures(self, run_id: str) -> tuple[CellKey, ...]:
        """Channel (a): the cells the dbt parity test stored as failing."""
        ...

    def write_report(self, report: EquivalenceReport) -> None: ...


def denominator(ir: WorkbookIR) -> int:
    computed = sum(len(s.cells()) for s in ir.steps)
    return computed + sum(1 for u in ir.unsupported if u.kind == FORMULA)


def build_report(
    run_id: str,
    ir: WorkbookIR,
    checked: int,
    mismatches: tuple[CellMismatch, ...],
    failures: tuple[CellKey, ...],
) -> EquivalenceReport:
    keys = {(m.sheet, m.cell_row, m.cell_col) for m in mismatches}
    return EquivalenceReport(
        run_id=run_id,
        workbook_sha256=ir.source.sha256,
        denominator=denominator(ir),
        cells_checked=checked,
        cells_matched=checked - len(mismatches),
        mismatches=Mismatches(cells=mismatches),
        parity_test_failures=len(failures),
        channels_agree=keys == set(failures),
        steps_generated=len(ir.steps),
        steps_total=len(ir.steps) + sum(1 for u in ir.unsupported if u.kind == FORMULA),
        unsupported=len(ir.unsupported),
    )


def verify_stage(io: VerifyIO) -> Stage:
    def run(run_id: str) -> str:
        ir = io.load_ir(run_id)
        checked, mismatches = io.compare(run_id)
        report = build_report(run_id, ir, checked, mismatches, io.parity_failures(run_id))
        io.write_report(report)
        summary = (
            f"{report.cells_matched} of {report.cells_checked} cells match "
            f"(denominator {report.denominator})"
        )
        if not report.channels_agree:
            raise ParityChannelsDisagree(f"parity channels disagree: {summary}")
        if mismatches or report.cells_checked != report.denominator:
            raise ParityMismatch(summary)
        return summary

    return run


def register_stages(io: VerifyIO) -> None:
    if STAGE_NAME not in registry.stages:
        registry.stages.add(STAGE_NAME, verify_stage(io))
