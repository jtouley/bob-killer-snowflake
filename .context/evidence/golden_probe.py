"""Golden probe (evidence script, not a test): Extract -> Graph -> runtime, per cell, vs Excel's cache.

For each pinned golden: extract every cell with the merged Extract stage, parse every formula with
the merged Graph parser, and for each formula built only from registered runtime functions and
supported operators, evaluate it on Excel's own cached inputs and compare the result with the cell's
cached value using verify/config.values_equal (exact, no tolerance). Each cell is checked on its own.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
import sys
from collections import Counter
from pathlib import Path

from bob_killer import registry
from bob_killer.contracts.raw import CachedType
from bob_killer.extract.reader import extract_workbook
from bob_killer.graph.parser import parse
from bob_killer.runtime import coercion
from bob_killer.runtime import functions as fn_pkg
from bob_killer.runtime.values import ExcelError
from bob_killer.verify.config import values_equal

for info in pkgutil.iter_modules(fn_pkg.__path__):
    importlib.import_module(f"{fn_pkg.__name__}.{info.name}")
SUPPORTED = set(registry.functions.names())


class Unsupported(Exception):
    pass


def col_letters(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def decode(cell: object) -> object:
    t, v = cell.cached_type, cell.cached_value  # type: ignore[attr-defined]
    if t == CachedType.NUMBER:
        return float(v)
    if t == CachedType.STRING:
        return v
    if t == CachedType.BOOL:
        return v.lower() in ("true", "1")
    if t == CachedType.ERROR:
        return next((e for e in ExcelError if e.value == v), Unsupported)
    if t == CachedType.BLANK:
        return None
    raise Unsupported(f"cached type {t}")


class Book:
    def __init__(self, raw: object) -> None:
        self.cells = {(c.sheet, c.address): c for c in raw.cells}  # type: ignore[attr-defined]

    def value(self, sheet: str, address: str) -> object:
        c = self.cells.get((sheet, address))
        return None if c is None else decode(c)


ARITH = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
}


def ev(e: object, book: Book, sheet: str) -> object:
    k = e.kind  # type: ignore[attr-defined]
    if k == "number":
        return e.value  # type: ignore[attr-defined]
    if k == "text":
        return e.value  # type: ignore[attr-defined]
    if k == "boolean":
        return e.value  # type: ignore[attr-defined]
    if k == "cell":
        if e.sheet not in (None, sheet):  # type: ignore[attr-defined]
            return book.value(e.sheet, f"{col_letters(e.at.column)}{e.at.row}")  # type: ignore[attr-defined]
        return book.value(sheet, f"{col_letters(e.at.column)}{e.at.row}")  # type: ignore[attr-defined]
    if k == "range":
        s, a, b = e.sheet or sheet, e.start, e.end  # type: ignore[attr-defined]
        if None in (a.column, a.row, b.column, b.row):
            raise Unsupported("whole row/column range")
        return tuple(
            book.value(s, f"{col_letters(c)}{r}")
            for r in range(a.row, b.row + 1)
            for c in range(a.column, b.column + 1)
        )
    if k == "call":
        if e.name not in SUPPORTED:  # type: ignore[attr-defined]
            raise Unsupported(f"function {e.name}")  # type: ignore[attr-defined]
        args = tuple(ev(x, book, sheet) for x in e.args)  # type: ignore[attr-defined]
        return registry.functions.get(e.name)(*args)  # type: ignore[attr-defined]
    if k == "unary" and e.op == "-":  # type: ignore[attr-defined]
        v = coercion.to_number(ev(e.operand, book, sheet))  # type: ignore[attr-defined]
        return v if isinstance(v, ExcelError) else -v
    if k == "binary" and e.op in ARITH:  # type: ignore[attr-defined]
        a = coercion.to_number(ev(e.left, book, sheet))  # type: ignore[attr-defined]
        b = coercion.to_number(ev(e.right, book, sheet))  # type: ignore[attr-defined]
        for v in (a, b):
            if isinstance(v, ExcelError):
                return v
        if e.op == "/" and b == 0:  # type: ignore[attr-defined]
            return ExcelError.DIV0 if hasattr(ExcelError, "DIV0") else ExcelError("#DIV/0!")
        return ARITH[e.op](a, b)  # type: ignore[attr-defined]
    raise Unsupported(f"node {k}{':' + str(getattr(e, 'op', '')) if hasattr(e, 'op') else ''}")


def probe(path: Path) -> dict[str, object]:
    raw = extract_workbook(path.read_bytes())
    book = Book(raw)
    stats: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    mismatches: list[dict[str, str]] = []
    for c in raw.cells:
        stats["cells"] += 1
        if not c.formula:
            continue
        stats["formulas"] += 1
        try:
            ast = parse(c.formula)
        except Exception as exc:  # parse failure on a real Excel formula is a finding
            stats["parse_failed"] += 1
            reasons[f"parse: {type(exc).__name__}"] += 1
            continue
        stats["parsed"] += 1
        try:
            expected = decode(c)
            if expected is Unsupported:
                raise Unsupported("unknown error value")
            got = ev(ast, book, c.sheet)
            if not isinstance(got, tuple):
                got = coercion.cell_result(got)  # Excel shows a blank formula result as 0
        except Unsupported as u:
            reasons[str(u)] += 1
            continue
        except Exception as exc:
            stats["eval_crash"] += 1
            reasons[f"eval crash: {type(exc).__name__}"] += 1
            continue
        if isinstance(got, tuple):
            reasons["range result"] += 1
            continue
        stats["evaluated"] += 1
        if isinstance(expected, float) and isinstance(got, (int, bool)) and not isinstance(got, bool):
            got = float(got)
        if values_equal(expected, got):  # type: ignore[arg-type]
            stats["exact_match"] += 1
        else:
            stats["mismatch"] += 1
            if len(mismatches) < 8:
                mismatches.append({"cell": f"{c.sheet}!{c.address}", "formula": c.formula[:80],
                                   "excel": repr(expected), "ours": repr(got)})
    return {"stats": dict(stats), "top_gaps": reasons.most_common(8), "mismatches": mismatches}


if __name__ == "__main__":
    lock = json.loads(Path("golden.lock").read_text())
    out = {}
    for w in lock["workbooks"]:
        if w["status"] != "resolved":
            continue
        p = Path("golden") / w["filename"]
        out[w["id"]] = probe(p)
        s = out[w["id"]]["stats"]
        print(f"{w['id']:14} cells={s.get('cells',0):6} formulas={s.get('formulas',0):5} "
              f"parsed={s.get('parsed',0):5} parse_failed={s.get('parse_failed',0):4} "
              f"evaluated={s.get('evaluated',0):5} exact={s.get('exact_match',0):5} "
              f"mismatch={s.get('mismatch',0):4} crash={s.get('eval_crash',0):3}", flush=True)
    Path(sys.argv[1] if len(sys.argv) > 1 else "build/golden_probe.json").write_text(json.dumps(out, indent=2))
