"""Excel oracle client. Real Excel (xlwings) or Microsoft Graph lives in services/oracle/.

LibreOffice is never an oracle. Until a runner exists, ``UnavailableOracle`` says so loudly.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, runtime_checkable

from bob_killer.verify.config import CellScalar


class OracleUnavailable(RuntimeError):
    pass


@runtime_checkable
class Oracle(Protocol):
    def recalculate(
        self, workbook: Path, inputs: Mapping[str, CellScalar]
    ) -> Mapping[str, CellScalar]: ...

    def convert_xls(self, workbook: Path) -> Path: ...


class UnavailableOracle:
    _WHY = (
        "no Excel oracle configured: recalculation needs desktop Excel (xlwings) on a "
        "Windows/Mac runner or Microsoft Graph credentials; see services/oracle/README.md"
    )

    def recalculate(
        self, workbook: Path, inputs: Mapping[str, CellScalar]
    ) -> Mapping[str, CellScalar]:
        raise OracleUnavailable(self._WHY)

    def convert_xls(self, workbook: Path) -> Path:
        raise OracleUnavailable(self._WHY)
