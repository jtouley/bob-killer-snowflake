"""verify.config.values_equal is exact: same type, same value, no tolerance."""

from hypothesis import given
from hypothesis import strategies as st

from bob_killer.verify.config import values_equal

cell_values = st.one_of(st.floats(allow_nan=False), st.text(), st.booleans(), st.none())


@given(cell_values)
def test_value_equals_itself(v: object) -> None:
    assert values_equal(v, v)


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_next_float_differs(x: float) -> None:
    import math

    assert not values_equal(x, math.nextafter(x, math.inf))


def test_bool_is_not_number() -> None:
    assert not values_equal(True, 1.0)


def test_signed_zero_differs() -> None:
    assert not values_equal(0.0, -0.0)


def test_text_is_not_number() -> None:
    assert not values_equal("1", 1.0)
