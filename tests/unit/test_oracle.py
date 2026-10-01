"""The oracle client protocol; Phase 0 ships only an explicit 'unavailable' implementation."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob_killer.verify.oracle import Oracle, OracleUnavailable, UnavailableOracle


def test_unavailable_oracle_satisfies_protocol() -> None:
    assert isinstance(UnavailableOracle(), Oracle)


def test_recalculate_refuses(tmp_path: Path) -> None:
    with pytest.raises(OracleUnavailable, match="Excel"):
        UnavailableOracle().recalculate(tmp_path / "b.xlsx", {})


def test_convert_xls_refuses(tmp_path: Path) -> None:
    with pytest.raises(OracleUnavailable):
        UnavailableOracle().convert_xls(tmp_path / "b.xls")
