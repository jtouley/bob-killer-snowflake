"""graph/parser.py: Excel formula text to our own AST over openpyxl's tokenizer (SPEC decision 2)."""

from __future__ import annotations

import json
import math
import string
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bob_killer.contracts.graph import (
    Anchor,
    ArrayConst,
    BinaryOp,
    Boolean,
    Call,
    CellRef,
    ErrorLiteral,
    ExcelError,
    Expr,
    Missing,
    NameRef,
    Number,
    RangeRef,
    Text,
    UnaryOp,
)
from bob_killer.graph.parser import FormulaError, parse
from bob_killer.graph.render import render
from bob_killer.graph.walk import function_names, references

LIMITS = json.loads(
    (Path(__file__).parents[1] / "oracle" / "excel_sheet_limits.json").read_text(encoding="utf-8")
)


def col(letters: str) -> int:
    """Column letters to a 1-based number, written independently of the parser."""
    number = 0
    for ch in letters:
        number = number * 26 + string.ascii_uppercase.index(ch) + 1
    return number


def at(letters: str, row: int, *, abs_col: bool = False, abs_row: bool = False) -> Anchor:
    return Anchor(column=col(letters), row=row, column_absolute=abs_col, row_absolute=abs_row)


def cell(letters: str, row: int, sheet: str | None = None, **flags: bool) -> CellRef:
    return CellRef(sheet=sheet, at=at(letters, row, **flags))


def rng(start: Anchor, end: Anchor, sheet: str | None = None) -> RangeRef:
    return RangeRef(sheet=sheet, start=start, end=end)


def num(value: float) -> Number:
    return Number(value=value)


def bin_(op: Any, left: Expr, right: Expr) -> BinaryOp:
    return BinaryOp(op=op, left=left, right=right)


def un(op: Any, operand: Expr) -> UnaryOp:
    return UnaryOp(op=op, operand=operand)


def call(name: str, *args: Expr) -> Call:
    return Call(name=name, args=args)


A1, B1, B2 = cell("A", 1), cell("B", 1), cell("B", 2)

PARSE_CASES = [
    pytest.param("=1.5", num(1.5), id="number"),
    pytest.param("=1E+3", num(1e3), id="number-scientific"),
    pytest.param('="a""b"', Text(value='a"b'), id="text-escaped-quote"),
    pytest.param('=""', Text(value=""), id="text-empty"),
    pytest.param("=TRUE", Boolean(value=True), id="boolean-true"),
    pytest.param("=false", Boolean(value=False), id="boolean-lowercase"),
    pytest.param("=#N/A", ErrorLiteral(value=ExcelError.NA), id="error-na"),
    pytest.param("=#DIV/0!", ErrorLiteral(value=ExcelError.DIV0), id="error-div0"),
    pytest.param("=A1", A1, id="cell"),
    pytest.param("=$B$2", cell("B", 2, abs_col=True, abs_row=True), id="cell-absolute"),
    pytest.param("=$A1", cell("A", 1, abs_col=True), id="cell-mixed"),
    pytest.param("=A1:B2", rng(at("A", 1), at("B", 2)), id="range"),
    pytest.param(
        "=A:$C",
        rng(Anchor(column=col("A")), Anchor(column=col("C"), column_absolute=True)),
        id="range-whole-columns",
    ),
    pytest.param(
        "=$1:3", rng(Anchor(row=1, row_absolute=True), Anchor(row=3)), id="range-whole-rows"
    ),
    pytest.param("=Sheet2!C3", cell("C", 3, sheet="Sheet2"), id="cross-sheet"),
    pytest.param(
        "='My Sheet'!A1:B2", rng(at("A", 1), at("B", 2), sheet="My Sheet"), id="quoted-sheet"
    ),
    pytest.param("='It''s'!A1", cell("A", 1, sheet="It's"), id="quoted-sheet-apostrophe"),
    pytest.param(
        "=Sheet1!A1:Sheet1!B2", rng(at("A", 1), at("B", 2), sheet="Sheet1"), id="range-sheet-twice"
    ),
    pytest.param("=Rate", NameRef(name="Rate"), id="defined-name"),
    pytest.param("=Sheet1!Rate", NameRef(name="Rate", sheet="Sheet1"), id="sheet-scoped-name"),
    pytest.param("=-A1", un("-", A1), id="unary-minus"),
    pytest.param("=+A1", un("+", A1), id="unary-plus"),
    pytest.param("=A1%", un("%", A1), id="percent"),
    pytest.param("=-2^2", bin_("^", un("-", num(2)), num(2)), id="negation-above-power"),
    pytest.param("=-A1%", un("%", un("-", A1)), id="negation-above-percent"),
    pytest.param("=1+2*3", bin_("+", num(1), bin_("*", num(2), num(3))), id="mul-above-add"),
    pytest.param("=2^3^2", bin_("^", bin_("^", num(2), num(3)), num(2)), id="power-left-assoc"),
    pytest.param("=1-2-3", bin_("-", bin_("-", num(1), num(2)), num(3)), id="sub-left-assoc"),
    pytest.param("=A1&1+2", bin_("&", A1, bin_("+", num(1), num(2))), id="add-above-concat"),
    pytest.param(
        '=A1&"x"=B1', bin_("=", bin_("&", A1, Text(value="x")), B1), id="concat-above-compare"
    ),
    pytest.param("=A1<>B1", bin_("<>", A1, B1), id="not-equal"),
    pytest.param("=(1+2)*3", bin_("*", bin_("+", num(1), num(2)), num(3)), id="parens"),
    pytest.param("=(A1+1)%", un("%", bin_("+", A1, num(1))), id="percent-of-parens"),
    pytest.param("=A1 + B1", bin_("+", A1, B1), id="whitespace-ignored"),
    pytest.param(
        "=SUM(A1:A3,2)", call("SUM", rng(at("A", 1), at("A", 3)), num(2)), id="function-call"
    ),
    pytest.param(
        "=if(A1>0,1,0)", call("IF", bin_(">", A1, num(0)), num(1), num(0)), id="function-lowercase"
    ),
    pytest.param("=NOW()", call("NOW"), id="function-no-args"),
    pytest.param("=IF(,1,)", call("IF", Missing(), num(1), Missing()), id="function-missing-args"),
    pytest.param(
        "=_xlfn.XLOOKUP(A1,B1:B2,A1)",
        call("XLOOKUP", A1, rng(at("B", 1), at("B", 2)), A1),
        id="function-xlfn-prefix",
    ),
    pytest.param("=SUM(ROUND(A1,0))", call("SUM", call("ROUND", A1, num(0))), id="function-nested"),
    pytest.param(
        '={1,"a";TRUE,#N/A}',
        ArrayConst(
            rows=(
                (num(1), Text(value="a")),
                (Boolean(value=True), ErrorLiteral(value=ExcelError.NA)),
            )
        ),
        id="array-constant",
    ),
    pytest.param("={-1,2}", ArrayConst(rows=((un("-", num(1)), num(2)),)), id="array-negative"),
    pytest.param(
        "=A1:B2 B1:C3",
        bin_(" ", rng(at("A", 1), at("B", 2)), rng(at("B", 1), at("C", 3))),
        id="intersection",
    ),
    pytest.param("=SUM((A1,B1))", call("SUM", bin_(",", A1, B1)), id="union-in-parens"),
]


@pytest.mark.parametrize(("formula", "expected"), PARSE_CASES)
def test_parse(formula: str, expected: Expr) -> None:
    assert parse(formula) == expected


@pytest.mark.parametrize(("formula", "expected"), PARSE_CASES)
def test_render_round_trips_each_case(formula: str, expected: Expr) -> None:
    assert parse(render(expected)) == expected


@pytest.mark.parametrize(
    "formula",
    [
        pytest.param("", id="empty"),
        pytest.param("=", id="equals-only"),
        pytest.param("A1", id="no-equals"),
        pytest.param("=A1#", id="tokenizer-error"),
        pytest.param("=Table1[Col]", id="structured-reference"),
        pytest.param("=[1]Sheet1!A1", id="external-workbook"),
        pytest.param("=Sheet1:Sheet3!A1", id="three-d-reference"),
        pytest.param("=(A1", id="unclosed-paren"),
        pytest.param("=SUM(A1", id="unclosed-call"),
        pytest.param("=A1+", id="dangling-operator"),
        pytest.param("=1)", id="stray-close"),
        pytest.param("=*2", id="leading-infix"),
    ],
)
def test_unparseable_formula_raises(formula: str) -> None:
    with pytest.raises(FormulaError):
        parse(formula)


def test_sheet_bounds_come_from_the_oracle() -> None:
    last, rows = LIMITS["last_column"], LIMITS["max_rows"]
    assert parse(f"={last}{rows}") == CellRef(at=Anchor(column=LIMITS["max_columns"], row=rows))
    for past in (f"{LIMITS['first_column_past']}1", f"A{rows + 1}"):
        assert parse(f"={past}") == NameRef(name=past)


@pytest.mark.parametrize(
    ("formula", "refs", "functions"),
    [
        pytest.param("=1+2", (), (), id="no-references"),
        pytest.param(
            "=SUM(A1,Sheet2!B1:B2)+Rate",
            (A1, rng(at("B", 1), at("B", 2), sheet="Sheet2"), NameRef(name="Rate")),
            ("SUM",),
            id="cells-ranges-names",
        ),
        pytest.param(
            "=IF(A1,NOW(),INDIRECT(B1))", (A1, B1), ("IF", "NOW", "INDIRECT"), id="nested-calls"
        ),
    ],
)
def test_references_and_functions(formula: str, refs: tuple[Any, ...], functions: Any) -> None:
    expr = parse(formula)
    assert references(expr) == refs
    assert function_names(expr) == functions


# --- property: parse(render(ast)) == ast for any generated AST ---------------------------------

_SHEET_CHARS = string.ascii_letters + string.digits + " .'!-"
sheets = st.none() | st.text(_SHEET_CHARS, min_size=1, max_size=8).filter(
    lambda s: not s.startswith("'") and not s.endswith("'") and s.strip() == s
)
columns = st.integers(1, LIMITS["max_columns"])
rows = st.integers(1, LIMITS["max_rows"])
anchors = st.builds(
    Anchor, column=columns, row=rows, column_absolute=st.booleans(), row_absolute=st.booleans()
)
column_anchors = st.builds(Anchor, column=columns, column_absolute=st.booleans())
row_anchors = st.builds(Anchor, row=rows, row_absolute=st.booleans())
refs = st.one_of(
    st.builds(CellRef, sheet=sheets, at=anchors),
    st.builds(RangeRef, sheet=sheets, start=anchors, end=anchors),
    st.builds(RangeRef, sheet=sheets, start=column_anchors, end=column_anchors),
    st.builds(RangeRef, sheet=sheets, start=row_anchors, end=row_anchors),
    st.builds(NameRef, sheet=sheets, name=st.from_regex(r"nm_[a-z0-9_]{0,6}", fullmatch=True)),
)
numbers = st.builds(
    Number,
    value=st.floats(min_value=0, allow_nan=False, allow_infinity=False).filter(
        lambda v: math.copysign(1, v) > 0
    ),
)
texts = st.builds(Text, value=st.text(string.printable.strip() + " ", max_size=6))
constants = st.one_of(
    numbers,
    texts,
    st.builds(Boolean, value=st.booleans()),
    st.builds(ErrorLiteral, value=st.sampled_from(ExcelError)),
)
array_items = constants | st.builds(UnaryOp, op=st.just("-"), operand=numbers)
arrays = st.integers(1, 3).flatmap(
    lambda width: st.lists(
        st.lists(array_items, min_size=width, max_size=width).map(tuple), min_size=1, max_size=3
    ).map(lambda r: ArrayConst(rows=tuple(r)))
)
BINARY_OPS = ("^", "*", "/", "+", "-", "&", "=", "<>", "<", "<=", ">", ">=")
FUNCTION_NAMES = ("SUM", "IF", "NOW", "INDIRECT", "OFFSET", "LOG10")


def _calls(children: st.SearchStrategy[Expr]) -> st.SearchStrategy[Call]:
    args = st.lists(children | st.builds(Missing), max_size=3).filter(lambda a: a != [Missing()])
    return st.builds(Call, name=st.sampled_from(FUNCTION_NAMES), args=args.map(tuple))


expressions = st.recursive(
    st.one_of(constants, refs, arrays),
    lambda children: st.one_of(
        st.builds(UnaryOp, op=st.sampled_from(("+", "-", "%")), operand=children),
        st.builds(BinaryOp, op=st.sampled_from(BINARY_OPS), left=children, right=children),
        _calls(children),
    ),
    max_leaves=12,
)


@given(expressions)
def test_parse_render_round_trip(expr: Expr) -> None:
    assert parse(render(expr)) == expr
