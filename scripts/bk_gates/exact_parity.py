"""Parity is exact: the verify comparator takes no tolerance in any form (Decision 1, C6)."""

from __future__ import annotations

import ast
import re

from bk_gates.astutil import Module, dotted, import_aliases, matches, modules
from bk_gates.core import GateContext, Violation, gate

VERIFY = "src/bob_killer/verify"
COMPARATOR = "values_equal"
TOLERANCE_NAME = re.compile(r"(?i)(tol|eps|approx|margin|delta|ulp|precision|threshold)")
APPROX_CALLS = frozenset(
    {"math.isclose", "pytest.approx", "numpy.isclose", "numpy.allclose", "numpy.testing"}
)


def _function_violations(
    module: Module, fn: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[Violation]:
    out: list[Violation] = []
    a = fn.args
    for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs):
        if TOLERANCE_NAME.search(arg.arg):
            out.append(
                Violation(
                    "exact_parity/tolerance-param", f"{module.where(arg)} {fn.name}({arg.arg})"
                )
            )
    if a.vararg or a.kwarg:
        out.append(
            Violation(
                "exact_parity/tolerance-param", f"{module.where(fn)} {fn.name} takes *args/**kwargs"
            )
        )
    for default in (*a.defaults, *(d for d in a.kw_defaults if d is not None)):
        if isinstance(default, ast.Constant) and isinstance(default.value, float):
            out.append(
                Violation("exact_parity/tolerance-param", f"{module.where(default)} float default")
            )
    return out


def _check(module: Module) -> list[Violation]:
    aliases = import_aliases(module.tree)
    out: list[Violation] = []
    for node in module.tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and TOLERANCE_NAME.search(t.id):
                out.append(
                    Violation("exact_parity/tolerance-constant", f"{module.where(t)} {t.id}")
                )
    for sub in ast.walk(module.tree):
        if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
            out.extend(_function_violations(module, sub))
        elif isinstance(sub, ast.Call) and matches(dotted(sub.func, aliases), APPROX_CALLS):
            out.append(
                Violation("exact_parity/approx-call", f"{module.where(sub)} approximate compare")
            )
    return out


@gate("exact_parity")
def check(ctx: GateContext) -> list[Violation]:
    mods = list(modules(ctx.project_root, VERIFY))
    out = [v for m in mods for v in _check(m)]
    config = next((m for m in mods if m.rel == f"{VERIFY}/config.py"), None)
    has_comparator = config is not None and any(
        isinstance(n, ast.FunctionDef) and n.name == COMPARATOR for n in config.tree.body
    )
    if not has_comparator:
        out.append(
            Violation(
                "exact_parity/missing-comparator", f"{VERIFY}/config.py must define {COMPARATOR}"
            )
        )
    return out
