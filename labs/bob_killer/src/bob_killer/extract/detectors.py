"""Unsupported-feature detectors (SPEC non-goals): reported with their origin, never converted.

Each detector takes the formula-pass openpyxl workbook and yields ``RawUnsupported`` rows. They
are registered in ``registry.detectors`` under the kind they report; a new detector is one more
registration, not a change here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any, cast

from openpyxl.utils import get_column_letter
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.formula import DataTableFormula

from bob_killer import registry
from bob_killer.contracts.raw import RawUnsupported

Detector = Callable[[Workbook], Iterable[RawUnsupported]]

CHART = "chart"
PIVOT_TABLE = "pivot_table"
EXTERNAL_LINK = "external_link"
DATA_TABLE = "data_table"


def _private(obj: object, name: str) -> list[Any]:
    """openpyxl keeps charts, pivots and links on private lists that its stubs do not declare."""
    found: list[Any] = getattr(obj, name, [])
    return found


def charts(wb: Workbook) -> Iterator[RawUnsupported]:
    for ws in wb.worksheets:
        for chart in _private(ws, "_charts"):
            marker = getattr(chart.anchor, "_from", None)
            where = f"{get_column_letter(marker.col + 1)}{marker.row + 1}" if marker else "A1"
            yield RawUnsupported(
                kind=CHART, origin=f"{ws.title}!{where}", reason="charts are out of scope for v1"
            )


def pivot_tables(wb: Workbook) -> Iterator[RawUnsupported]:
    for ws in wb.worksheets:
        for pivot in _private(ws, "_pivots"):
            yield RawUnsupported(
                kind=PIVOT_TABLE,
                origin=f"{ws.title}!{pivot.location.ref}",
                reason=f"pivot table {pivot.name} is out of scope for v1",
            )


def external_links(wb: Workbook) -> Iterator[RawUnsupported]:
    for i, link in enumerate(_private(wb, "_external_links"), start=1):
        target = link.file_link.Target if link.file_link is not None else ""
        yield RawUnsupported(
            kind=EXTERNAL_LINK,
            origin=f"[{i}]",
            reason=f"external workbook link to {target!r} is out of scope for v1",
        )


def data_tables(wb: Workbook) -> Iterator[RawUnsupported]:
    for ws in wb.worksheets:
        for key in sorted(ws._cells):
            value = ws._cells[key].value
            if isinstance(value, DataTableFormula):
                yield RawUnsupported(
                    kind=DATA_TABLE,
                    origin=f"{ws.title}!{value.ref}",
                    reason="what-if data tables are out of scope for v1",
                )


BUILTIN: dict[str, Detector] = {
    CHART: charts,
    PIVOT_TABLE: pivot_tables,
    EXTERNAL_LINK: external_links,
    DATA_TABLE: data_tables,
}


def register_detectors() -> None:
    """Idempotent: adds each built-in detector that is not registered yet."""
    for name, detector in BUILTIN.items():
        if name not in registry.detectors:
            registry.detectors.add(name, detector)


def detect(wb: Workbook) -> tuple[RawUnsupported, ...]:
    register_detectors()
    found: list[RawUnsupported] = []
    for name, detector in registry.detectors.items():
        for row in cast(Iterable[object], detector(wb)):
            if not isinstance(row, RawUnsupported):
                raise TypeError(f"detector {name!r} yielded {type(row).__name__}")
            found.append(row)
    return tuple(found)
