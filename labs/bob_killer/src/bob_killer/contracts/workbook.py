"""Compiler host contracts: input cells for dbt, and name reviews (docs/SPEC-compiler-dbt.md).

``WbInputCell`` is one row of the host table ``WB_INPUT_CELLS``: the cached value of one IR input
cell of a run, as a wire ``CellValue`` (D21, D22). It is the only workbook data a generated dbt
model reads. ``row`` and ``col`` are reserved words in Snowflake, so the cell key is
``cell_row``/``cell_col``.

``NameReview`` records one decision on an output-facing name (core decision 3, D25). It applies
to the IR node with the same id, origin and fingerprint (a step's R1C1 fingerprint; "" for an
output). ``ReviewFile`` holds the reviews of one workbook, keyed by its sha256.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from bob_killer.contracts.base import StrictModel
from bob_killer.contracts.ir import CellValue, Id, Origin

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
RunId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]


class WbInputCell(StrictModel):
    table_name = "wb_input_cells"
    primary_key = ("run_id", "sheet", "cell_row", "cell_col")

    run_id: RunId
    sheet: str
    cell_row: int
    cell_col: int
    node_id: Id
    value: CellValue


class NameReview(StrictModel):
    node_id: Id
    origin: Origin
    fingerprint: str
    label: str
    reviewer: str
    reason: str


class ReviewFile(StrictModel):
    workbook_sha256: Sha256
    reviews: tuple[NameReview, ...]
