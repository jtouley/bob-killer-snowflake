"""Formula text to our own AST, on top of openpyxl's MIT tokenizer (SPEC decision 2).

Precedence climbing over the token list; the operator table lives in ``grammar``.
"""

from __future__ import annotations

from openpyxl.formula.tokenizer import Token, Tokenizer, TokenizerError

from bob_killer.contracts.graph import (
    ArrayConst,
    BinaryOp,
    Boolean,
    Call,
    ErrorLiteral,
    ExcelError,
    Expr,
    Missing,
    Number,
    Text,
    UnaryOp,
)
from bob_killer.graph import grammar
from bob_killer.graph.refs import FormulaError, parse_reference

__all__ = ["FormulaError", "parse"]

_INTERSECT = Token(" ", Token.OP_IN)
_BOOLEANS = ("TRUE", "FALSE")


def _ends_operand(tok: Token) -> bool:
    return tok.type in (Token.OPERAND, Token.OP_POST) or tok.subtype == Token.CLOSE


def _starts_operand(tok: Token) -> bool:
    return tok.type == Token.OPERAND or tok.subtype == Token.OPEN


def _tokens(formula: str) -> list[Token]:
    if not formula.startswith("="):
        raise FormulaError(f"not a formula: {formula!r}")
    try:
        items = Tokenizer(formula).items
    except (TokenizerError, IndexError, AssertionError) as exc:  # the tokenizer raises all three
        raise FormulaError(f"cannot tokenize {formula!r}: {exc}") from exc
    out: list[Token] = []
    for i, tok in enumerate(items):
        if tok.type != Token.WSPACE:
            out.append(tok)
        elif (
            out and i + 1 < len(items) and _ends_operand(out[-1]) and _starts_operand(items[i + 1])
        ):
            out.append(_INTERSECT)  # whitespace between two operands is the intersection operator
    if not out:
        raise FormulaError("empty formula")
    return out


def _function_name(raw: str) -> str:
    name = raw.upper()
    while name.startswith(grammar.STORAGE_PREFIXES):
        name = name.split(".", 1)[1]
    if not name or ":" in name or "!" in name:
        raise FormulaError(f"unsupported function reference {raw!r}")
    return name


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self) -> Token:
        tok = self.peek()
        if tok is None:
            raise FormulaError("formula ends early")
        self.pos += 1
        return tok

    def at(self, type_: str, subtype: str | None = None, value: str | None = None) -> bool:
        tok = self.peek()
        return (
            tok is not None
            and tok.type == type_
            and (subtype is None or tok.subtype == subtype)
            and (value is None or tok.value == value)
        )

    def expect(self, type_: str, subtype: str) -> None:
        if not self.at(type_, subtype):
            raise FormulaError(f"expected {type_} {subtype} at token {self.pos}")
        self.pos += 1

    def infix(self, table: dict[str, int], minimum: int) -> int | None:
        tok = self.peek()
        if tok is None or tok.type != Token.OP_IN:
            return None
        level = table.get(tok.value)
        return level if level is not None and level >= minimum else None

    def binary(self, minimum: int = 0) -> Expr:
        left = self.percent()
        while (level := self.infix(grammar.VALUE_OPERATORS, minimum)) is not None:
            op = self.next().value
            left = BinaryOp(op=op, left=left, right=self.binary(level + 1))
        return left

    def percent(self) -> Expr:
        operand = self.prefix()
        while self.at(Token.OP_POST, value="%"):
            self.pos += 1
            operand = UnaryOp(op="%", operand=operand)
        return operand

    def prefix(self) -> Expr:
        tok = self.peek()
        if tok is not None and tok.type == Token.OP_PRE and tok.value in ("+", "-"):
            self.pos += 1
            return UnaryOp(op=tok.value, operand=self.prefix())
        return self.reference(min(grammar.REFERENCE_OPERATORS.values()))

    def reference(self, minimum: int) -> Expr:
        left = self.primary()
        while (level := self.infix(grammar.REFERENCE_OPERATORS, minimum)) is not None:
            op = self.next().value
            left = BinaryOp(op=op, left=left, right=self.reference(level + 1))
        return left

    def primary(self) -> Expr:
        tok = self.next()
        if tok.type == Token.OPERAND:
            return _operand(tok)
        if tok.type == Token.FUNC and tok.subtype == Token.OPEN:
            return Call(name=_function_name(tok.value[:-1]), args=self.arguments())
        if tok.type == Token.PAREN and tok.subtype == Token.OPEN:
            inner = self.binary()
            self.expect(Token.PAREN, Token.CLOSE)
            return inner
        if tok.type == Token.ARRAY and tok.subtype == Token.OPEN:
            return self.array()
        raise FormulaError(f"unexpected {tok.value!r} at token {self.pos - 1}")

    def arguments(self) -> tuple[Expr, ...]:
        if self.at(Token.FUNC, Token.CLOSE):
            self.pos += 1
            return ()
        args: list[Expr] = []
        while True:
            empty = self.at(Token.SEP, Token.ARG) or self.at(Token.FUNC, Token.CLOSE)
            args.append(Missing() if empty else self.binary())
            if self.at(Token.SEP, Token.ARG):
                self.pos += 1
                continue
            self.expect(Token.FUNC, Token.CLOSE)
            return tuple(args)

    def array(self) -> ArrayConst:
        rows: list[tuple[Expr, ...]] = []
        row: list[Expr] = [self.binary()]
        while not self.at(Token.ARRAY, Token.CLOSE):
            sep = self.next()
            if sep.type != Token.SEP:
                raise FormulaError(f"unexpected {sep.value!r} in array constant")
            if sep.subtype == Token.ROW:
                rows.append(tuple(row))
                row = []
            row.append(self.binary())
        self.pos += 1
        rows.append(tuple(row))
        if len({len(r) for r in rows}) != 1:
            raise FormulaError("array constant rows differ in length")
        return ArrayConst(rows=tuple(rows))


def _operand(tok: Token) -> Expr:
    value = tok.value
    if tok.subtype == Token.NUMBER:
        return Number(value=float(value))
    if tok.subtype == Token.TEXT:
        return Text(value=value[1:-1].replace('""', '"'))
    if tok.subtype == Token.LOGICAL or value.upper() in _BOOLEANS:  # lowercase arrives as RANGE
        return Boolean(value=value.upper() == "TRUE")
    if tok.subtype == Token.ERROR:
        try:
            return ErrorLiteral(value=ExcelError(value.upper()))
        except ValueError:
            raise FormulaError(f"unknown error literal {value!r}") from None
    return parse_reference(value)


def parse(formula: str) -> Expr:
    """Parse ``=...`` formula text into an AST, or raise FormulaError."""
    parser = _Parser(_tokens(formula))
    expr = parser.binary()
    if parser.peek() is not None:
        raise FormulaError(f"unexpected {parser.next().value!r} after the expression")
    return expr
