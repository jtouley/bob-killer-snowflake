"""verify.config.values_equal is exact: same type, same value, no tolerance."""

from hypothesis import given
from hypothesis import strategies as st

from bob_killer.contracts.ir import CellValue, ExcelError
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


# --- the contract CellValue (D21, docs/SPEC-compiler-dbt.md §5.3) ---------------------------------

wire_values = st.one_of(
    st.floats(allow_nan=False, allow_infinity=False).map(CellValue.number),
    st.text().map(CellValue.text),
    st.booleans().map(CellValue.boolean),
    st.sampled_from(list(ExcelError)).map(CellValue.error),
    st.just(None).map(lambda _: CellValue.blank()),
)


@given(wire_values)
def test_cell_value_equals_itself(v: CellValue) -> None:
    assert values_equal(v, v)


@given(wire_values, wire_values)
def test_cell_values_are_equal_only_when_kind_and_payload_match(a: CellValue, b: CellValue) -> None:
    assert values_equal(a, b) == (a.model_dump() == b.model_dump())


def test_cell_value_signed_zero_differs() -> None:
    assert not values_equal(CellValue.number(0.0), CellValue.number(-0.0))


def test_blank_empty_text_and_zero_are_three_values() -> None:
    blank, empty, zero = CellValue.blank(), CellValue.text(""), CellValue.number(0.0)
    assert not values_equal(blank, empty)
    assert not values_equal(blank, zero)
    assert not values_equal(empty, zero)


def test_errors_compare_by_error_type() -> None:
    assert values_equal(CellValue.error(ExcelError.NA), CellValue.error(ExcelError.NA))
    assert not values_equal(CellValue.error(ExcelError.NA), CellValue.error(ExcelError.DIV0))


def test_text_is_case_sensitive() -> None:
    assert not values_equal(CellValue.text("a"), CellValue.text("A"))
