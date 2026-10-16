"""The CLI is a thin client over the same service layer as the API."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob_killer.cli import EXIT_OK, EXIT_REJECTED, main
from bob_killer.contracts.runs import RunState
from tests.conftest import workbook_like


def test_all_on_empty_pipeline_succeeds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    book = tmp_path / "book.xlsx"
    book.write_bytes(workbook_like())
    assert main(["all", str(book), "--db", str(tmp_path / "cli.db")]) == EXIT_OK
    assert RunState.SUCCEEDED in capsys.readouterr().out


def test_rejected_upload_exit_code(tmp_path: Path) -> None:
    book = tmp_path / "book.xls"
    book.write_bytes(b"legacy")
    assert main(["all", str(book), "--db", str(tmp_path / "cli.db")]) == EXIT_REJECTED
