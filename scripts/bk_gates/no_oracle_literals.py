"""No oracle literals: expected values come from fixtures or tests/oracle, never inline (D3)."""

from __future__ import annotations

import ast

from bk_gates.astutil import Module, modules
from bk_gates.core import GateContext, Violation, gate

SCOPES = ("tests/unit", "tests/integration")


def is_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return node.value is not None and not isinstance(node.value, bool) and node.value != ...
    if isinstance(node, ast.UnaryOp):
        return is_literal(node.operand)
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return any(is_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return any(is_literal(n) for n in [*node.keys, *node.values] if n is not None)
    return False


def _literal_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and is_literal(node.value):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and is_literal(node.value)
            and isinstance(node.target, ast.Name)
        ):
            names.add(node.target.id)
    return names


def _check(module: Module) -> list[Violation]:
    bound = _literal_names(module.tree)
    out: list[Violation] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Assert):
            continue
        for cmp in (n for n in ast.walk(node.test) if isinstance(n, ast.Compare)):
            for operand in (cmp.left, *cmp.comparators):
                if is_literal(operand) or (isinstance(operand, ast.Name) and operand.id in bound):
                    out.append(
                        Violation(
                            "no_oracle_literals/literal",
                            f"{module.where(operand)} compares against a literal expected value",
                        )
                    )
    return out


@gate("no_oracle_literals")
def check(ctx: GateContext) -> list[Violation]:
    return [v for m in modules(ctx.project_root, *SCOPES) for v in _check(m)]
