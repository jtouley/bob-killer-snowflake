"""Excel's cached cell values as wire ``CellValue`` objects (the oracle, D15; the dbt inputs, D22).

The Raw layer keeps a number as ``repr(float)`` text, so it converts back exactly. A date (the
reader's ISO text) and a formula cell with no cached value have no exact value: they raise.
"""

from __future__ import annotations

from bob_killer.contracts.ir import CellRef, CellValue, ExcelError, cell_range
from bob_killer.contracts.raw import CachedType, RawCell, RawWorkbook


class NoCachedValue(ValueError):
    """The cell has no exact cached value to compare with or to feed a model."""


def cached_value(cell: RawCell) -> CellValue:
    match cell.cached_type:
        case CachedType.NUMBER:
            return CellValue.number(float(cell.cached_value))
        case CachedType.STRING:
            return CellValue.text(cell.cached_value)
        case CachedType.BOOL:
            return CellValue.boolean(cell.cached_value == "TRUE")
        case CachedType.ERROR:
            return CellValue.error(ExcelError(cell.cached_value))
        case CachedType.BLANK:
            return CellValue.blank()
    raise NoCachedValue(f"{cell.sheet}!{cell.address}: cached {cell.cached_type.value}")


def cell_ref(cell: RawCell) -> CellRef:
    r = cell_range("'" + cell.sheet.replace("'", "''") + "'!" + cell.address)
    return CellRef(sheet=r.sheet, row=r.row, col=r.col)


class CachedValues(dict[CellRef, CellValue]):
    """Every cell of a Raw layer by reference; a cell absent from the sheet XML is blank."""

    def __missing__(self, key: CellRef) -> CellValue:
        return CellValue.blank()


def cached_values(raw: RawWorkbook, refs: set[CellRef] | None = None) -> CachedValues:
    """The cached value of each cell of ``raw`` (only ``refs`` when given)."""
    out = CachedValues()
    for cell in raw.cells:
        ref = cell_ref(cell)
        if refs is None or ref in refs:
            out[ref] = cached_value(cell)
    return out
