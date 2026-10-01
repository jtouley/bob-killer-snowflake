"""AST helpers shared by static gates: file iteration and import-alias-aware dotted names."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Module:
    rel: str
    tree: ast.Module
    lines: list[str]

    def where(self, node: ast.AST) -> str:
        return f"{self.rel}:{getattr(node, 'lineno', 0)}"


def modules(project_root: Path, *subdirs: str) -> Iterator[Module]:
    for sub in subdirs:
        base = project_root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            yield Module(
                path.relative_to(project_root).as_posix(), ast.parse(source), source.splitlines()
            )


def import_aliases(tree: ast.Module) -> dict[str, str]:
    """Local name -> fully qualified dotted name, from import statements."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                aliases[a.asname or a.name.split(".")[0]] = (
                    a.name if a.asname else a.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                aliases[a.asname or a.name] = f"{node.module}.{a.name}"
    return aliases


def dotted(node: ast.AST, aliases: dict[str, str]) -> str | None:
    """Resolve ``np.isclose`` -> ``numpy.isclose``; None for non-name expressions."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(aliases.get(node.id, node.id))
    return ".".join(reversed(parts))


def matches(name: str | None, banned: frozenset[str]) -> bool:
    return name is not None and any(name == b or name.startswith(f"{b}.") for b in banned)
