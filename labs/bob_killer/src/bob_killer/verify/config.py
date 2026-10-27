"""The parity comparator. Exact by construction: there is no tolerance to configure."""

from __future__ import annotations

from bob_killer.contracts.ir import CellValue

CellScalar = float | str | bool | None
Comparable = CellScalar | CellValue | object  # a runtime value (errors included) or a wire value


def values_equal(expected: Comparable, actual: Comparable) -> bool:
    """Same type and same value; floats must be the same IEEE-754 double, sign of zero included.

    A contract ``CellValue`` holds its number as canonical ``float.hex()`` text, so equal kind
    and payload is the same double (docs/SPEC-compiler-dbt.md §5.3).
    """
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, float) and isinstance(actual, float):
        return expected.hex() == actual.hex()
    return expected == actual
