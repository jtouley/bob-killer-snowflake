"""registry.py: one generic registry type; duplicates and unknown names fail loudly."""

from __future__ import annotations

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
