"""Bronze landing records: one row per landed file, one row per sheet row (docs/SPEC.md §6.1)."""

from __future__ import annotations

from bob_killer.contracts.base import StrictModel

type CellJson = float | int | str | bool | None
"""A cached cell value: dates as ISO-8601 text, errors as their text (``#DIV/0!``)."""


class BronzePayload(StrictModel):
    column_names: tuple[str, ...]
    dtypes: dict[str, str]
    data: dict[str, CellJson]


class LandedFile(StrictModel):
    table_name = "landed_files"
    primary_key = ("file_sha256",)

    file_sha256: str
    filename: str
    stage_file: str
    size_bytes: int
    first_run_id: str


class BronzeRow(StrictModel):
    table_name = "bronze_rows"
    primary_key = ("file_sha256", "sheet", "row_number")

    file_sha256: str
    sheet: str
    row_number: int
    run_id: str
    payload: BronzePayload
