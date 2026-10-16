"""Handlers for the BK_FN_* / BK_OP_* Snowflake Python UDFs the generated dbt models call (demo).

Functions (SUM, MIN, IF, ...) call the merged bob_killer runtime through registry.functions.
Operators are a DEMO SHIM here: the runtime has no operator layer yet (core rule: Excel semantics
belong in runtime/). SUMIF is not implemented in the runtime, so its UDF returns #N/A, and the
dbt parity test will report those cells.
"""

from __future__ import annotations

import importlib
import pkgutil

from bob_killer import registry
from bob_killer.runtime import coercion
from bob_killer.runtime import functions as _fns
from bob_killer.runtime.values import ExcelError

for _m in pkgutil.iter_modules(_fns.__path__):
    importlib.import_module(f"{_fns.__name__}.{_m.name}")


def decode(w):  # noqa: ANN001, ANN201
    if isinstance(w, list):
        return tuple(decode(x) for x in w)
    if w is None:
        return None
    k = w.get("k")
    if k == "n":
        return float.fromhex(w["h"])
    if k == "s":
        return w["t"]
    if k == "b":
        return bool(w["b"])
    if k == "e":
        return next(e for e in ExcelError if e.value == w["e"] or e.name == w["e"])
    return None


def encode(v):  # noqa: ANN001, ANN201
    if isinstance(v, tuple):
        return [encode(x) for x in v]
    if v is None:
        return {"k": "z"}
    if isinstance(v, bool):
        return {"k": "b", "b": v}
    if isinstance(v, float | int):
        return {"k": "n", "h": float(v).hex()}
    if isinstance(v, ExcelError):
        return {"k": "e", "e": v.value}
    return {"k": "s", "t": str(v)}


def fn(name):  # noqa: ANN001, ANN201
    def handler(*args):  # noqa: ANN002, ANN202
        if name not in registry.functions:
            return encode(ExcelError("#N/A"))
        return encode(registry.functions.get(name)(*(decode(a) for a in args)))

    return handler


def _num(a):  # noqa: ANN001, ANN202
    return coercion.to_number(decode(a))


def _arith(op):  # noqa: ANN001, ANN202
    def handler(a, b):  # noqa: ANN001, ANN202
        x, y = _num(a), _num(b)
        for v in (x, y):
            if isinstance(v, ExcelError):
                return encode(v)
        return encode(op(x, y))

    return handler


def _cmp(want_equal):  # noqa: ANN001, ANN202
    def handler(a, b):  # noqa: ANN001, ANN202
        x, y = decode(a), decode(b)
        if x is None:
            x = "" if isinstance(y, str) else 0.0
        if y is None:
            y = "" if isinstance(x, str) else 0.0
        if isinstance(x, str) and isinstance(y, str):
            eq = x.lower() == y.lower()
        else:
            eq = type(x) is type(y) and x == y
        return encode(eq if want_equal else not eq)

    return handler


op_add = _arith(lambda x, y: x + y)
op_sub = _arith(lambda x, y: x - y)
op_mul = _arith(lambda x, y: x * y)
op_eq = _cmp(True)
op_ne = _cmp(False)
fn_sum, fn_min, fn_if, fn_sumif = fn("SUM"), fn("MIN"), fn("IF"), fn("SUMIF")
