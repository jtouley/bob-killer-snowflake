"""Excel date serials, 1900 and 1904 systems, including the 1900 leap-year bug.

1900 system: serial 1 is 1900-01-01 and serial 60 is the phantom 1900-02-29 that Excel keeps for
Lotus 1-2-3 compatibility, so every later serial is one more than the true day count.
1904 system: serial 0 is 1904-01-01. Valid dates run to 9999-12-31 (Excel specifications).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

LEAP_BUG_SERIAL = 60
LEAP_BUG_YMD = (1900, 2, 29)
_DAY_ZERO_1900 = date(1899, 12, 31)  # serial 0 before the leap bug
_DAY_ZERO_1904 = date(1904, 1, 1)
_LAST_DATE = date(9999, 12, 31)


def _bounds(date1904: bool) -> tuple[int, int]:
    if date1904:
        return 0, (_LAST_DATE - _DAY_ZERO_1904).days
    return 1, (_LAST_DATE - _DAY_ZERO_1900).days + 1


def _check(serial: int, date1904: bool) -> None:
    first, last = _bounds(date1904)
    if not first <= serial <= last:
        system = "1904" if date1904 else "1900"
        raise ValueError(
            f"serial {serial} is outside Excel's {system} date system [{first}, {last}]"
        )


def ymd_to_serial(year: int, month: int, day: int, *, date1904: bool = False) -> float:
    """The serial number of a calendar date."""
    if date1904:
        serial = (date(year, month, day) - _DAY_ZERO_1904).days
    elif (year, month, day) == LEAP_BUG_YMD:
        serial = LEAP_BUG_SERIAL
    else:
        serial = (date(year, month, day) - _DAY_ZERO_1900).days
        if serial >= LEAP_BUG_SERIAL:
            serial += 1
    _check(serial, date1904)
    return float(serial)


def serial_to_ymd(serial: float, *, date1904: bool = False) -> tuple[int, int, int]:
    """The calendar date of a serial number; the fraction (time of day) is dropped."""
    whole = math.floor(serial)
    _check(whole, date1904)
    if date1904:
        d = _DAY_ZERO_1904 + timedelta(days=whole)
    elif whole == LEAP_BUG_SERIAL:
        return LEAP_BUG_YMD
    else:
        d = _DAY_ZERO_1900 + timedelta(days=whole - (whole > LEAP_BUG_SERIAL))
    return d.year, d.month, d.day
