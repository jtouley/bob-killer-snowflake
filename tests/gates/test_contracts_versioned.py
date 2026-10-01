"""contracts_versioned: a contract change without a schema_version bump fails (Phase 0 done-when)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bk_gates.contracts_versioned import (
    check_snapshots,
    default_models,
    export,
    generate,
)
from bob_killer.contracts.base import StrictModel


class AddedField(StrictModel):
    """A contract the snapshot has never seen, standing in for 'someone added a field'."""

    surprise: int


def _rules(generated: dict[str, str], snapshot: Path) -> set[str]:
    return {v.rule for v in check_snapshots(generated, snapshot)}


def test_generation_is_deterministic() -> None:
    assert generate() == generate()


def test_default_models_are_only_shipped_contracts() -> None:
    assert AddedField not in default_models()
    assert all(m.__module__.startswith("bob_killer.contracts") for m in default_models())


def test_matching_snapshot_passes(tmp_path: Path) -> None:
    export(generate(), tmp_path / "v1")
    assert _rules(generate(), tmp_path / "v1") == set()


def test_missing_snapshot_fails(tmp_path: Path) -> None:
    assert "contracts_versioned/missing-snapshot" in _rules(generate(), tmp_path / "v1")


def test_contract_change_without_bump_fails(tmp_path: Path) -> None:
    export(generate(), tmp_path / "v1")
    changed = generate([*default_models(), AddedField])
    assert "contracts_versioned/drift" in _rules(changed, tmp_path / "v1")


def test_export_refuses_existing_version(tmp_path: Path) -> None:
    export(generate(), tmp_path / "v1")
    with pytest.raises(FileExistsError):
        export(generate(), tmp_path / "v1")
