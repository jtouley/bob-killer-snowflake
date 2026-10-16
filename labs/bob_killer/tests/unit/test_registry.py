"""registry.py: one generic registry type; duplicates and unknown names fail loudly."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest

from bob_killer.registry import Registry, load_entry_points


def test_register_and_get() -> None:
    reg: Registry[object] = Registry("things")

    def total() -> None: ...

    assert reg.register(total.__name__)(total) is total
    assert reg.get(total.__name__) is total
    assert total.__name__ in reg
    assert reg.names() == (total.__name__,)


def test_duplicate_name_rejected() -> None:
    reg: Registry[object] = Registry("things")
    reg.add("x", object())
    with pytest.raises(ValueError, match="things"):
        reg.add("x", object())


def test_unknown_name_names_the_registry() -> None:
    reg: Registry[object] = Registry("generators")
    with pytest.raises(KeyError, match="generators"):
        reg.get("streamlit")


def test_entry_points_register(monkeypatch: pytest.MonkeyPatch) -> None:
    target = object()
    ep = SimpleNamespace(name="fake", load=lambda: target)
    monkeypatch.setattr(
        "bob_killer.registry.entry_points", lambda group: [ep] if group == "grp" else []
    )
    reg: Registry[object] = Registry("generators")
    load_entry_points(reg, "grp")
    assert reg.get("fake") is target


@pytest.mark.parametrize(
    "mutate",
    [lambda reg: reg.add("added", object()), lambda reg: reg.clear()],
    ids=["entry-added", "entry-removed"],
)
def test_snapshot_restores_entries(mutate: Callable[[Registry[object]], None]) -> None:
    reg: Registry[object] = Registry("things")
    reg.add("kept", object())
    before = reg.items()
    with reg.snapshot():
        mutate(reg)
        assert reg.items() != before
    assert reg.items() == before


def test_clear_empties_the_registry() -> None:
    reg: Registry[object] = Registry("things")
    reg.add("x", object())
    reg.clear()
    assert not reg
    assert reg.names() == ()


def test_excel_function_registers_in_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    import bob_killer.registry as registry

    fresh: Registry[object] = Registry("functions")
    monkeypatch.setattr(registry, "functions", fresh)

    def total() -> None: ...

    name = total.__name__.upper()
    assert registry.excel_function(name)(total) is total
    assert fresh.get(name) is total
    with pytest.raises(ValueError, match="functions"):
        registry.excel_function(name)(total)
