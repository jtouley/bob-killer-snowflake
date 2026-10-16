"""Stage 2 (Graph) contracts: the formula AST, the graph input, and the CellGraph output.

The AST is our own (SPEC decision 2): every node is a strict, frozen model with a ``kind``
discriminator, so a CellGraph round-trips through JSON without a second type definition.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import Field

from bob_killer.contracts.base import StrictModel

MAX_ROWS: Final = 1_048_576
MAX_COLUMNS: Final = 16_384

UnaryOperator = Literal["+", "-", "%"]
BinaryOperator = Literal[
    ":", " ", ",", "^", "*", "/", "+", "-", "&", "=", "<>", "<", "<=", ">", ">="
]


class ExcelError(StrEnum):
    """The error literals a formula can contain (the codes openpyxl's tokenizer accepts)."""

    NULL = "#NULL!"
    DIV0 = "#DIV/0!"
    VALUE = "#VALUE!"
    REF = "#REF!"
    NAME = "#NAME?"
    NUM = "#NUM!"
    NA = "#N/A"
    GETTING_DATA = "#GETTING_DATA"


class Number(StrictModel):
    kind: Literal["number"] = "number"
    value: float


class Text(StrictModel):
    kind: Literal["text"] = "text"
    value: str


class Boolean(StrictModel):
    kind: Literal["boolean"] = "boolean"
    value: bool


class ErrorLiteral(StrictModel):
    kind: Literal["error"] = "error"
    value: ExcelError


class Missing(StrictModel):
    """An empty function argument, as in ``IF(,1,)``."""

    kind: Literal["missing"] = "missing"


class Anchor(StrictModel):
    """One corner of a reference. ``None`` means the whole row or column (``A:A``, ``1:3``)."""

    column: Annotated[int, Field(ge=1, le=MAX_COLUMNS)] | None = None
    row: Annotated[int, Field(ge=1, le=MAX_ROWS)] | None = None
    column_absolute: bool = False
    row_absolute: bool = False


class CellRef(StrictModel):
    kind: Literal["cell"] = "cell"
    sheet: str | None = None
    at: Anchor


class RangeRef(StrictModel):
    kind: Literal["range"] = "range"
    sheet: str | None = None
    start: Anchor
    end: Anchor


class NameRef(StrictModel):
    """A defined name; ``sheet`` is set for a sheet-qualified name such as ``Sheet1!Rate``."""

    kind: Literal["name"] = "name"
    sheet: str | None = None
    name: str


class ArrayConst(StrictModel):
    kind: Literal["array"] = "array"
    rows: tuple[tuple[Expr, ...], ...]


class UnaryOp(StrictModel):
    kind: Literal["unary"] = "unary"
    op: UnaryOperator
    operand: Expr


class BinaryOp(StrictModel):
    kind: Literal["binary"] = "binary"
    op: BinaryOperator
    left: Expr
    right: Expr


class Call(StrictModel):
    """A function call; ``name`` is upper case without the ``_xlfn.``/``_xlws.`` storage prefix."""

    kind: Literal["call"] = "call"
    name: str
    args: tuple[Expr, ...] = ()


Expr = Annotated[
    Number
    | Text
    | Boolean
    | ErrorLiteral
    | Missing
    | CellRef
    | RangeRef
    | NameRef
    | ArrayConst
    | UnaryOp
    | BinaryOp
    | Call,
    Field(discriminator="kind"),
]
Reference = Annotated[CellRef | RangeRef | NameRef, Field(discriminator="kind")]

for _model in (ArrayConst, UnaryOp, BinaryOp, Call):
    _model.model_rebuild()


class CellKey(StrictModel):
    sheet: str
    column: Annotated[int, Field(ge=1, le=MAX_COLUMNS)]
    row: Annotated[int, Field(ge=1, le=MAX_ROWS)]


class FormulaCell(StrictModel):
    """Stage input: the formula text of one cell, as Extract stores it."""

    sheet: str
    address: Annotated[str, Field(pattern=r"^\$?[A-Za-z]{1,3}\$?[0-9]{1,7}$")]
    formula: str


class DefinedName(StrictModel):
    """A defined name; ``scope`` is the sheet for a sheet-scoped name, else workbook scope."""

    name: str
    scope: str | None = None
    refers_to: str


class GraphInput(StrictModel):
    cells: tuple[FormulaCell, ...]
    names: tuple[DefinedName, ...] = ()


class CellNode(StrictModel):
    key: CellKey
    formula: str
    ast: Expr | None = None
    error: str | None = None
    references: tuple[Reference, ...] = ()
    precedents: tuple[CellKey, ...] = ()
    volatile: tuple[str, ...] = ()
    dynamic: tuple[str, ...] = ()
    unresolved_names: tuple[str, ...] = ()


class CellGraph(StrictModel):
    """Stage output. ``order`` lists every node outside a cycle, precedents first."""

    nodes: tuple[CellNode, ...]
    order: tuple[CellKey, ...]
    cycles: tuple[tuple[CellKey, ...], ...]
