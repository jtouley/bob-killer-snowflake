"""No silent skips: skip/xfail/approx/isclose need a `# allow: <id>` backed by ALLOWLIST.md."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from bk_gates.astutil import Module, dotted, import_aliases, matches, modules
from bk_gates.core import GateContext, Violation, gate

BANNED = frozenset(
    {
        "pytest.skip",
        "pytest.xfail",
        "pytest.importorskip",
        "pytest.approx",
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
        "math.isclose",
        "unittest.skip",
        "unittest.skipIf",
        "unittest.skipUnless",
        "unittest.expectedFailure",
        "numpy.isclose",
        "numpy.allclose",
        "numpy.testing",
    }
)
ALLOW = re.compile(r"#\s*allow:\s*([A-Za-z0-9_.-]+)")
ISSUE = re.compile(r"(https?://\S+|#\d+)")


def allowlist(project_root: Path) -> set[str]:
    """Allow ids whose ALLOWLIST.md row links an issue."""
    path = project_root / "ALLOWLIST.md"
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        is_row = len(cells) >= 4 and cells[0] not in ("id", "") and set(cells[0]) - {"-", ":"}
        if is_row and ISSUE.search(cells[-1]):
            ids.add(cells[0])
    return ids


DYNAMIC_IMPORTS = frozenset({"__import__", "importlib.import_module"})


def _offending_lines(module: Module) -> dict[int, tuple[str, str]]:
    """Line -> (rule, what). Dynamic imports are banned outright: they hide the module used."""
    aliases = import_aliases(module.tree)
    lines: dict[int, tuple[str, str]] = {}
    for node in ast.walk(module.tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                name = f"{node.module}.{a.name}"
                if matches(name, BANNED):
                    lines.setdefault(node.lineno, ("no_silent_skips/unallowed", name))
        elif isinstance(node, ast.Call) and dotted(node.func, aliases) in DYNAMIC_IMPORTS:
            lines[node.lineno] = ("no_silent_skips/dynamic-import", "dynamic import in tests")
        elif isinstance(node, ast.Attribute | ast.Name) and isinstance(
            getattr(node, "ctx", None), ast.Load
        ):
            resolved = dotted(node, aliases)
            if resolved is not None and matches(resolved, BANNED):
                lines.setdefault(node.lineno, ("no_silent_skips/unallowed", resolved))
    return lines


@gate("no_silent_skips")
def check(ctx: GateContext) -> list[Violation]:
    allowed = allowlist(ctx.project_root)
    out: list[Violation] = []
    for module in modules(ctx.project_root, "tests"):
        for lineno, (rule, name) in sorted(_offending_lines(module).items()):
            m = ALLOW.search(module.lines[lineno - 1])
            where = f"{module.rel}:{lineno}"
            if rule == "no_silent_skips/dynamic-import":
                out.append(Violation(rule, f"{where} {name}"))
            elif m is None:
                out.append(Violation(rule, f"{where} uses {name}"))
            elif m.group(1) not in allowed:
                out.append(
                    Violation(
                        "no_silent_skips/unknown-allow-id",
                        f"{where} allow id {m.group(1)!r} has no ALLOWLIST.md row with an issue",
                    )
                )
    return out
