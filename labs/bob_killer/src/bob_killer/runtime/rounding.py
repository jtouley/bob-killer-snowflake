"""Excel rounding: 15 significant digits first, then decimal rounding, never binary rounding.

Excel keeps 15 digits of precision (support.microsoft.com "Excel specifications and limits"), so
ROUND(2.15, 1) is 2.2 although the double nearest 2.15 lies below it.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Context, Decimal

from bob_killer.runtime.values import UnsupportedValue

SIGNIFICANT_DIGITS = 15
_FIFTEEN = Context(prec=SIGNIFICANT_DIGITS, rounding=ROUND_HALF_UP)
_FIXED_MIN_EXPONENT = -5
_FIXED_MAX_EXPONENT = SIGNIFICANT_DIGITS - 1


def fifteen_digits(x: float) -> Decimal:
    """The double as Excel shows it: 15 significant decimal digits, half away from zero."""
    return _FIFTEEN.create_decimal_from_float(x)


def _round(x: float, digits: int, rounding: str) -> float:
    d = fifteen_digits(x)
    # Never quantize finer than the 15 digits held; the result has at most 16 digits.
    places = max(-digits, int(d.as_tuple().exponent))
    d = d.quantize(Decimal(f"1E{places}"), rounding=rounding)
    result = float(d)
    return 0.0 if result == 0 else result  # Excel has no negative zero in a cell


def round_half_away(x: float, digits: int) -> float:
    """ROUND: to ``digits`` decimal places (negative: left of the point), halves away from 0."""
    return _round(x, digits, ROUND_HALF_UP)


def round_away(x: float, digits: int) -> float:
    """ROUNDUP: away from zero."""
    return _round(x, digits, ROUND_UP)


def round_toward_zero(x: float, digits: int) -> float:
    """ROUNDDOWN: toward zero."""
    return _round(x, digits, ROUND_DOWN)


def number_to_text(x: float) -> str:
    """A number as text (``"A"&x``): 15 significant digits, trailing zeros dropped.

    Fixed notation for decimal exponents -5..14, ``d.ddE+XX`` from 1E+15 up. Below 1E-5 the
    General-format switch to scientific notation is not established, so it is refused.
    """
    d = fifteen_digits(x)
    if d.is_zero():
        return "0"
    d = d.normalize()
    exponent = d.adjusted()
    if _FIXED_MIN_EXPONENT <= exponent <= _FIXED_MAX_EXPONENT:
        return format(d, "f")
    if exponent < _FIXED_MIN_EXPONENT:
        raise UnsupportedValue(f"text form of {x!r} below 1E-5")  # pragma: no mutate
    sign, digits, _ = d.as_tuple()
    mantissa = "".join(map(str, digits))
    if len(mantissa) > 1:
        mantissa = f"{mantissa[0]}.{mantissa[1:]}"
    return f"{'-' if sign else ''}{mantissa}E+{exponent:02d}"
