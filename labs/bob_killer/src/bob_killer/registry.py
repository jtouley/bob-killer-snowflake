"""Registries: functions, step kinds, generators, detectors, stages. Core never branches on type."""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any


class Registry[T]:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: dict[str, T] = {}

    def add(self, name: str, item: T) -> None:
        if name in self._items:
            raise ValueError(f"{self.kind}: {name!r} is already registered")
        self._items[name] = item

    def register(self, name: str) -> Callable[[T], T]:
        def decorator(item: T) -> T:
            self.add(name, item)
            return item

        return decorator

    def get(self, name: str) -> T:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(f"{self.kind}: no entry named {name!r}") from None

    def names(self) -> tuple[str, ...]:
        return tuple(self._items)

    def items(self) -> tuple[tuple[str, T], ...]:
        return tuple(self._items.items())

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)


def load_entry_points(registry: Registry[Any], group: str) -> None:
    for ep in entry_points(group=group):
        registry.add(ep.name, ep.load())


Stage = Callable[[str], None]

functions: Registry[Callable[..., object]] = Registry("functions")
step_kinds: Registry[type] = Registry("step_kinds")
generators: Registry[object] = Registry("generators")
detectors: Registry[Callable[..., object]] = Registry("detectors")
stages: Registry[Stage] = Registry("stages")
