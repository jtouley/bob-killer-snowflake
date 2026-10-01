"""Gate registry: every gate is one function registered with ``@gate(name)``."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str


@dataclass(frozen=True)
class GateContext:
    repo_root: Path
    project_root: Path
    base: str | None
    head: str = "HEAD"

    @property
    def prefix(self) -> str:
        """Project path relative to the repo root, with a trailing slash ('' at the root)."""
        rel = self.project_root.resolve().relative_to(self.repo_root.resolve()).as_posix()
        return "" if rel == "." else f"{rel}/"


Check = Callable[[GateContext], list[Violation]]


@dataclass(frozen=True)
class Gate:
    name: str
    check: Check
    nightly_only: bool = False


_REGISTRY: dict[str, Gate] = {}


def gate(name: str, *, nightly_only: bool = False) -> Callable[[Check], Check]:
    def register(fn: Check) -> Check:
        if name in _REGISTRY and _REGISTRY[name].check is not fn:
            raise ValueError(f"gate {name!r} registered twice")
        _REGISTRY[name] = Gate(name, fn, nightly_only)
        return fn

    return register


def load_gates() -> dict[str, Gate]:
    """Import every bk_gates module so its gates register, then return the registry."""
    package = importlib.import_module("bk_gates")
    for info in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"bk_gates.{info.name}")
    return dict(_REGISTRY)
