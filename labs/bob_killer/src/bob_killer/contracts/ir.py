"""The Workbook IR: the only contract between stages (core SPEC "Workbook IR", decision 9).

Sections: ``schema_version``, ``source``, ``sheets``, ``parameters``, ``inputs``, ``lookups``,
``steps`` (the closed step-kind union), ``outputs``, ``unsupported``, ``vba``. Expressions use the
IR's own AST (core IR rules), never Excel text. Values cross every boundary as ``CellValue``, whose
JSON dump is the D21 wire format (a number is ``float.hex()`` text).

The generator boundary types (``TargetConfig``, ``GeneratedFile``, ``GeneratedProject``) live here
too (docs/SPEC-compiler-dbt.md §3.2, §3.4).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterator
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from bob_killer.contracts.base import SCHEMA_VERSION, StrictModel

MAX_ROW = 1_048_576
MAX_COL = 16_384

Id = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=63)]
SnowflakeName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_$]*$", max_length=255)]
Row = Annotated[int, Field(ge=1, le=MAX_ROW)]
Col = Annotated[int, Field(ge=1, le=MAX_COL)]

_CELL = r"\$?([A-Z]{1,3})\$?([0-9]{1,7})"
_A1 = re.compile(rf"(?:'((?:[^']|'')+)'|([A-Za-z0-9_.]+))!{_CELL}(?::{_CELL})?", re.DOTALL)


def _col_number(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - ord("A") + 1
    return n


class CellRef(StrictModel):
    sheet: str
    row: Row
    col: Col


class CellRange(StrictModel):
    sheet: str
    row: Row
    col: Col
    last_row: Row
    last_col: Col

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.last_row < self.row or self.last_col < self.col:
            raise ValueError("a range ends before it starts")
        return self

    @property
    def height(self) -> int:
        return self.last_row - self.row + 1

    @property
    def width(self) -> int:
        return self.last_col - self.col + 1

    def cells(self) -> tuple[CellRef, ...]:
        """Every cell in row-major order."""
        return tuple(
            CellRef(sheet=self.sheet, row=r, col=c)
            for r in range(self.row, self.last_row + 1)
            for c in range(self.col, self.last_col + 1)
        )


def cell_range(text: str) -> CellRange:
    """Parse an A1 origin such as ``Data!A1:C200`` or ``'My sheet'!$B$2``."""
    match = _A1.fullmatch(text)
    if match is None:
        raise ValueError(f"not an A1 origin: {text!r}")
    quoted, bare, c1, r1, c2, r2 = match.groups()
    sheet = quoted.replace("''", "'") if quoted is not None else bare
    row, col = int(r1), _col_number(c1)
    return CellRange(
        sheet=sheet,
        row=row,
        col=col,
        last_row=int(r2) if r2 else row,
        last_col=_col_number(c2) if c2 else col,
    )


def _origin(text: str) -> str:
    cell_range(text)
    return text


Origin = Annotated[str, AfterValidator(_origin)]


# --- values (D21) -------------------------------------------------------------------------------


class ValueKind(StrEnum):
    NUMBER = "n"
    TEXT = "s"
    BOOLEAN = "b"
    ERROR = "e"
    BLANK = "z"


class ExcelError(StrEnum):
    NULL = "#NULL!"
    DIV0 = "#DIV/0!"
    VALUE = "#VALUE!"
    REF = "#REF!"
    NAME = "#NAME?"
    NUM = "#NUM!"
    NA = "#N/A"
    GETTING_DATA = "#GETTING_DATA"
    SPILL = "#SPILL!"
    CALC = "#CALC!"
    FIELD = "#FIELD!"
    BLOCKED = "#BLOCKED!"
    CONNECT = "#CONNECT!"
    BUSY = "#BUSY!"
    UNKNOWN = "#UNKNOWN!"
    PYTHON = "#PYTHON!"


_PAYLOAD = {
    ValueKind.NUMBER: "h",
    ValueKind.TEXT: "t",
    ValueKind.BOOLEAN: "b",
    ValueKind.ERROR: "e",
    ValueKind.BLANK: None,
}


class CellValue(StrictModel):
    """One Excel value. ``wire()`` is the D21 wire text: ``{"k":"n","h":"<float.hex()>"}``."""

    k: ValueKind
    h: str | None = None
    t: str | None = None
    b: bool | None = None
    e: ExcelError | None = None

    @model_validator(mode="after")
    def _fields_match_kind(self) -> Self:
        present = {f for f in ("h", "t", "b", "e") if getattr(self, f) is not None}
        wanted = _PAYLOAD[self.k]
        if present != ({wanted} if wanted else set()):
            raise ValueError(f"kind {self.k.value!r} carries fields {sorted(present)}")
        if self.h is not None:
            x = float.fromhex(self.h)
            if not math.isfinite(x) or x.hex() != self.h:
                raise ValueError(f"number {self.h!r} is not a canonical finite float.hex()")
        return self

    @classmethod
    def number(cls, x: float) -> CellValue:
        return cls(k=ValueKind.NUMBER, h=float(x).hex())

    @classmethod
    def text(cls, t: str) -> CellValue:
        return cls(k=ValueKind.TEXT, t=t)

    @classmethod
    def boolean(cls, b: bool) -> CellValue:
        return cls(k=ValueKind.BOOLEAN, b=b)

    @classmethod
    def error(cls, e: ExcelError) -> CellValue:
        return cls(k=ValueKind.ERROR, e=e)

    @classmethod
    def blank(cls) -> CellValue:
        return cls(k=ValueKind.BLANK)

    @model_serializer(mode="wrap")
    def _drop_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        """Every dump is the wire shape: only ``k`` and the field of that kind."""
        return {k: v for k, v in handler(self).items() if v is not None}

    def wire(self) -> str:
        return json.dumps(self.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False)


# A shaped range on the wire (D21 extension for the BK_* UDFs): {"cols": <columns>, "cells": [...]}.
RANGE_COLUMNS = "cols"
RANGE_CELLS = "cells"


# --- expressions --------------------------------------------------------------------------------


class Operator(StrEnum):
    ADD = "ADD"
    SUB = "SUB"
    MUL = "MUL"
    DIV = "DIV"
    POW = "POW"
    CONCAT = "CONCAT"
    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    GT = "GT"
    LE = "LE"
    GE = "GE"
    NEG = "NEG"
    PERCENT = "PERCENT"


UNARY_OPERATORS = frozenset({Operator.NEG, Operator.PERCENT})


class CellExpr(StrictModel):
    """A cell reference. In a ``column_expr`` a relative part shifts with the output row."""

    type: Literal["cell"] = "cell"
    sheet: str
    row: Row
    col: Col
    row_abs: bool = True
    col_abs: bool = True


class RangeExpr(StrictModel):
    type: Literal["range"] = "range"
    sheet: str
    row: Row
    col: Col
    last_row: Row
    last_col: Col

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        self.as_range()
        return self

    def as_range(self) -> CellRange:
        return CellRange(
            sheet=self.sheet,
            row=self.row,
            col=self.col,
            last_row=self.last_row,
            last_col=self.last_col,
        )


class ParamExpr(StrictModel):
    type: Literal["param"] = "param"
    id: Id


class LiteralExpr(StrictModel):
    type: Literal["lit"] = "lit"
    value: CellValue


class CallExpr(StrictModel):
    type: Literal["call"] = "call"
    name: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_.]*$")]
    args: tuple[Expr, ...]


class OpExpr(StrictModel):
    type: Literal["op"] = "op"
    op: Operator
    args: tuple[Expr, ...]

    @model_validator(mode="after")
    def _arity(self) -> Self:
        want = 1 if self.op in UNARY_OPERATORS else 2
        if len(self.args) != want:
            raise ValueError(f"{self.op.value} takes {want} operand(s), got {len(self.args)}")
        return self


Expr = Annotated[
    CellExpr | RangeExpr | ParamExpr | LiteralExpr | CallExpr | OpExpr,
    Field(discriminator="type"),
]
CallExpr.model_rebuild()
OpExpr.model_rebuild()


def iter_expr(expr: Expr) -> Iterator[Expr]:
    """The expression and every sub-expression, depth first, left to right."""
    yield expr
    if isinstance(expr, CallExpr | OpExpr):
        for arg in expr.args:
            yield from iter_expr(arg)


# --- nodes --------------------------------------------------------------------------------------


class NameRule(StrEnum):
    """Core decision 3, in priority order, plus a human review."""

    DEFINED_NAME = "defined_name"
    TABLE_COLUMN = "table_column"
    HEADER_ABOVE = "header_above"
    HEADER_LEFT = "header_left"
    SHEET_ADDRESS = "sheet_address"
    REVIEWED = "reviewed"


class NameStatus(StrEnum):
    ACCEPTED = "accepted"
    NEEDS_REVIEW = "needs_review"


class Format(StrEnum):
    GENERAL = "general"
    NUMBER = "number"
    PERCENT = "percent"
    CURRENCY = "currency"
    DATE = "date"
    TEXT = "text"
    BOOLEAN = "boolean"


class DType(StrEnum):
    FLOAT64 = "float64"
    TEXT = "text"
    BOOL = "bool"
    CELL = "cell"


class Node(StrictModel):
    """Every IR node has an id and an origin back to cells (core IR rules)."""

    id: Id
    label: str
    origin: Annotated[tuple[Origin, ...], Field(min_length=1)]
    description: str = ""
    name_rule: NameRule
    name_status: NameStatus

    def ranges(self) -> tuple[CellRange, ...]:
        return tuple(cell_range(o) for o in self.origin)

    def cells(self) -> tuple[CellRef, ...]:
        return tuple(c for r in self.ranges() for c in r.cells())

    def _one_range(self) -> CellRange:
        if len(self.origin) != 1:
            raise ValueError(f"{self.id}: needs exactly one origin range")
        return self.ranges()[0]


class Sheet(StrictModel):
    id: Id
    name: str
    index: Annotated[int, Field(ge=0)]


class Source(StrictModel):
    file: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Column(StrictModel):
    name: Id
    label: str
    dtype: DType


class Parameter(Node):
    """A hardcoded number promoted to a named, editable value."""

    format: Format
    default: CellValue

    @model_validator(mode="after")
    def _numeric(self) -> Self:
        if self.default.k is not ValueKind.NUMBER:
            raise ValueError(f"{self.id}: a parameter default is a number")
        return self


class InputShape(StrEnum):
    SCALAR = "scalar"
    TABLE = "table"


class InputKind(StrEnum):
    INPUT = "input"
    FROZEN_VOLATILE = "frozen_volatile"


def _columns_span(node: Node, columns: tuple[Column, ...]) -> CellRange:
    rng = node._one_range()
    if rng.width != len(columns):
        raise ValueError(f"{node.id}: {len(columns)} columns for a range {rng.width} wide")
    if len({c.name for c in columns}) != len(columns):
        raise ValueError(f"{node.id}: duplicate column names")
    return rng


class Input(Node):
    shape: InputShape
    kind: InputKind = InputKind.INPUT
    columns: tuple[Column, ...]

    @model_validator(mode="after")
    def _shape(self) -> Self:
        rng = _columns_span(self, self.columns)
        if self.shape is InputShape.SCALAR and rng.height != 1:
            raise ValueError(f"{self.id}: a scalar input is one cell")
        return self


class Lookup(Node):
    key: Id
    columns: tuple[Column, ...]

    @model_validator(mode="after")
    def _key(self) -> Self:
        _columns_span(self, self.columns)
        if self.key not in {c.name for c in self.columns}:
            raise ValueError(f"{self.id}: key {self.key!r} is not a column")
        return self


class ExprStep(Node):
    expr: Expr
    formula: str
    fingerprint: str

    def exprs(self) -> tuple[Expr, ...]:
        return (self.expr,)


class _SingleCellStep(ExprStep):
    @model_validator(mode="after")
    def _single_cell(self) -> Self:
        rng = self._one_range()
        if rng.height != 1 or rng.width != 1:
            raise ValueError(f"{self.id}: this step kind computes one cell")
        return self


class ScalarExprStep(_SingleCellStep):
    kind: Literal["scalar_expr"] = "scalar_expr"


class ColumnExprStep(ExprStep):
    """One vectorized step: the same R1C1 formula down one column, row-wise over ``over``."""

    kind: Literal["column_expr"] = "column_expr"
    over: Id

    @model_validator(mode="after")
    def _one_column(self) -> Self:
        if self._one_range().width != 1:
            raise ValueError(f"{self.id}: a column step covers one column")
        return self


class AggregateStep(_SingleCellStep):
    kind: Literal["aggregate"] = "aggregate"


class LookupStep(_SingleCellStep):
    kind: Literal["lookup"] = "lookup"
    lookup: Id


class ConditionalStep(_SingleCellStep):
    kind: Literal["conditional"] = "conditional"


class VbaStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    UNTRANSLATED = "untranslated"
    TRANSLATED_UNVERIFIED = "translated_unverified"
    TRANSLATED_VERIFIED = "translated_verified"


class VbaClass(StrEnum):
    NAVIGATION_UI = "navigation_ui"
    EXTERNAL = "external"
    PURE_COMPUTATION = "pure_computation"
    UNKNOWN = "unknown"


class Assignment(StrictModel):
    cell: CellRef
    expr: Expr


class VbaProcedureStep(Node):
    """A translated VBA procedure as IR assignments (§6). Only ``translated_verified`` generates."""

    kind: Literal["vba_procedure"] = "vba_procedure"
    module: str
    procedure: Id
    status: VbaStatus
    assignments: Annotated[tuple[Assignment, ...], Field(min_length=1)]

    def exprs(self) -> tuple[Expr, ...]:
        return tuple(a.expr for a in self.assignments)


Step = Annotated[
    ScalarExprStep
    | ColumnExprStep
    | AggregateStep
    | LookupStep
    | ConditionalStep
    | VbaProcedureStep,
    Field(discriminator="kind"),
]
STEP_MODELS: tuple[type[StrictModel], ...] = (
    ScalarExprStep,
    ColumnExprStep,
    AggregateStep,
    LookupStep,
    ConditionalStep,
    VbaProcedureStep,
)


class Output(Node):
    step: Id
    format: Format


class Unsupported(StrictModel):
    kind: Id
    origin: Origin
    reason: str


class VbaEntry(StrictModel):
    module: str
    procedure: str
    status: VbaStatus
    classification: VbaClass
    writes: tuple[Origin, ...]
    translated_to: Id | None


class WorkbookIR(StrictModel):
    schema_version: int
    source: Source
    sheets: tuple[Sheet, ...]
    parameters: tuple[Parameter, ...]
    inputs: tuple[Input, ...]
    lookups: tuple[Lookup, ...]
    steps: tuple[Step, ...]
    outputs: tuple[Output, ...]
    unsupported: tuple[Unsupported, ...]
    vba: tuple[VbaEntry, ...]

    def nodes(self) -> tuple[Node, ...]:
        """Every node that owns cells: parameters, inputs, lookups and steps."""
        return (*self.parameters, *self.inputs, *self.lookups, *self.steps)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version {self.schema_version} != {SCHEMA_VERSION}")
        _unique("node id", [n.id for n in self.nodes()])
        _unique("output id", [o.id for o in self.outputs])
        _unique("sheet", [s.name for s in self.sheets])
        _unique("sheet id", [s.id for s in self.sheets])
        sheets = {s.name for s in self.sheets}
        origins = [o for n in (*self.nodes(), *self.outputs) for o in n.origin]
        origins += [u.origin for u in self.unsupported] + [w for v in self.vba for w in v.writes]
        exprs = [e for s in self.steps for root in s.exprs() for e in iter_expr(root)]
        used = {cell_range(o).sheet for o in origins}
        used |= {e.sheet for e in exprs if isinstance(e, CellExpr | RangeExpr)}
        used |= {
            a.cell.sheet
            for s in self.steps
            if isinstance(s, VbaProcedureStep)
            for a in s.assignments
        }
        if missing := used - sheets:
            raise ValueError(f"unknown sheets {sorted(missing)}")
        _known("parameter", {e.id for e in exprs if isinstance(e, ParamExpr)}, self.parameters)
        _known("input", {s.over for s in self.steps if isinstance(s, ColumnExprStep)}, self.inputs)
        _known("lookup", {s.lookup for s in self.steps if isinstance(s, LookupStep)}, self.lookups)
        _known("step", {o.step for o in self.outputs}, self.steps)
        _known("step", {v.translated_to for v in self.vba if v.translated_to}, self.steps)
        return self


def _unique(what: str, values: list[str]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate {what}")


def _known(what: str, wanted: set[str], nodes: tuple[Node, ...]) -> None:
    if missing := wanted - {n.id for n in nodes}:
        raise ValueError(f"unknown {what} {sorted(missing)}")


# --- generator boundary (docs/SPEC-compiler-dbt.md §3.2, §3.4) ------------------------------------


class TargetConfig(StrictModel):
    run_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    database: SnowflakeName
    deploy_schema: SnowflakeName
    role: SnowflakeName
    warehouse: SnowflakeName
    dbt_version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]

    @property
    def output_schema(self) -> str:
        return f"{self.deploy_schema}__R_{self.run_id}"


class GeneratedFile(StrictModel):
    path: Annotated[str, Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")]
    content: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def _digest(self) -> Self:
        if ".." in self.path.split("/"):
            raise ValueError(f"{self.path}: a generated path stays inside the project")
        if hashlib.sha256(self.content.encode()).hexdigest() != self.sha256:
            raise ValueError(f"{self.path}: sha256 does not match the content")
        return self

    @classmethod
    def of(cls, path: str, content: str) -> GeneratedFile:
        return cls(path=path, content=content, sha256=hashlib.sha256(content.encode()).hexdigest())


class GeneratedProject(StrictModel):
    """Files sorted by path, unique, no timestamps (§3.4)."""

    files: tuple[GeneratedFile, ...]

    @model_validator(mode="after")
    def _sorted(self) -> Self:
        paths = [f.path for f in self.files]
        if paths != sorted(set(paths)):
            raise ValueError("generated files must be sorted by path and unique")
        return self

    def by_path(self) -> dict[str, str]:
        return {f.path: f.content for f in self.files}
