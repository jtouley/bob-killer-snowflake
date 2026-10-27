"""The equivalence report (docs/SPEC-compiler-dbt.md §5.4, §5.5): one row per run in WB_REPORTS.

Parity is checked two ways. Channel (a) is the dbt test ``bk_exact_parity`` (its stored failing
rows); channel (b) is the verify stage's own SQL compare of ``fct_formula_cells`` with the oracle
seed through ``BK_VALUES_EQUAL``. ``channels_agree`` says both name the same mismatched cells.
A cell missing on one side has ``None`` there.
"""

from __future__ import annotations

from bob_killer.contracts.base import StrictModel
from bob_killer.contracts.ir import CellValue
from bob_killer.contracts.workbook import RunId, Sha256


class CellMismatch(StrictModel):
    sheet: str
    cell_row: int
    cell_col: int
    expected: CellValue | None
    actual: CellValue | None


class Mismatches(StrictModel):
    cells: tuple[CellMismatch, ...]


class EquivalenceReport(StrictModel):
    table_name = "wb_reports"
    primary_key = ("run_id",)

    run_id: RunId
    workbook_sha256: Sha256
    denominator: int
    cells_checked: int
    cells_matched: int
    mismatches: Mismatches
    parity_test_failures: int
    channels_agree: bool
    steps_generated: int
    steps_total: int
    unsupported: int
