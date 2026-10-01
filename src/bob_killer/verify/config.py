"""The parity comparator. Exact by construction: there is no tolerance to configure."""

from __future__ import annotations

CellScalar = float | str | bool | None


def values_equal(expected: CellScalar, actual: CellScalar) -> bool:
    """Same type and same value; floats must be the same IEEE-754 double, sign of zero included."""
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, float) and isinstance(actual, float):
        return expected.hex() == actual.hex()
    return expected == actual
