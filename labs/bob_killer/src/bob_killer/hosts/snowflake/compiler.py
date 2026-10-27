"""The compiler stages' IO in Snowflake: run files on @DBT_SRC, input cells, the dbt target.

A run's files live under ``@DBT_SRC/<run_id>/`` (auto_compress off, F6/F25). The local workspace
(workbook.db, ir.yaml) is the working copy within one procedure call; a stage that needs a file
the workspace lacks (a later call, D18) reads it back from the stage. Name reviews are YAML
``ReviewFile`` documents on ``@DBT_SRC/_reviews/`` (deployed from hosts/snowflake/reviews/).
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from typing import Any

import yaml

from bob_killer.contracts.ir import CellRef, CellValue, GeneratedProject, TargetConfig, WorkbookIR
from bob_killer.contracts.report import CellMismatch, EquivalenceReport
from bob_killer.contracts.workbook import NameReview, ReviewFile, WbInputCell
from bob_killer.extract.raw_db import read_raw
from bob_killer.generate.dbt.generator import FACT_MODEL, ORACLE_SEED, PARITY_TEST
from bob_killer.hosts.snowflake.batch import insert_rows
from bob_killer.ir import load_ir
from bob_killer.ir.cells import cached_values
from bob_killer.service.workspace import IR_YAML, WORKBOOK_DB, Workspace

DBT_SRC = "@DBT_SRC"
REVIEWS = "_reviews"
DBT_VERSION = "1.12.3"  # D29, F13
TARGET_SQL = (
    "SELECT CURRENT_DATABASE() AS DATABASE, CURRENT_SCHEMA() AS SCHEMA, "
    "CURRENT_ROLE() AS ROLE, CURRENT_WAREHOUSE() AS WAREHOUSE"
)
DELETE_INPUTS_SQL = f"DELETE FROM {WbInputCell.table_name.upper()} WHERE RUN_ID = ?"
LIST_SQL = "LIST ?"
RUN_SCHEMA_INFIX = "__R_"
AUDIT_SUFFIX = "_DBT_TEST__AUDIT"  # dbt's store_failures schema: <target schema>_dbt_test__audit
PARITY_TABLE = f"{PARITY_TEST}_{FACT_MODEL}_{ORACLE_SEED}".upper()
# Channel (b): every oracle cell against every computed cell, compared by the one comparator.
COMPARE_SQL = """SELECT COALESCE(o."sheet", f."sheet") AS SHEET,
    COALESCE(TO_NUMBER(o."row"), f."row") AS CELL_ROW,
    COALESCE(TO_NUMBER(o."col"), f."col") AS CELL_COL,
    PARSE_JSON(o."wire_json") AS EXPECTED, f."value" AS ACTUAL,
    COALESCE(o."sheet" IS NOT NULL AND f."sheet" IS NOT NULL
        AND BK_VALUES_EQUAL(PARSE_JSON(o."wire_json"), f."value"), FALSE) AS EQUAL
FROM IDENTIFIER(?) AS o FULL OUTER JOIN IDENTIFIER(?) AS f
    ON o."sheet" = f."sheet" AND TO_NUMBER(o."row") = f."row" AND TO_NUMBER(o."col") = f."col"
"""
FAILURES_SQL = "SELECT CELL_SHEET, CELL_ROW, CELL_COL FROM IDENTIFIER(?)"
DELETE_REPORT_SQL = f"DELETE FROM {EquivalenceReport.table_name.upper()} WHERE RUN_ID = ?"


class StageFiles:
    """Files on @DBT_SRC by path relative to the stage."""

    def __init__(self, session: Any) -> None:
        self.session = session

    def put(self, path: str, data: bytes) -> None:
        self.session.file.put_stream(
            io.BytesIO(data), f"{DBT_SRC}/{path}", auto_compress=False, overwrite=True
        )

    def get(self, path: str) -> bytes:
        data: bytes = self.session.file.get_stream(f"{DBT_SRC}/{path}").read()
        return data

    def names(self, prefix: str) -> list[str]:
        """Paths under ``prefix``; LIST names a file ``<stage>/<path>`` (stage name lowercased)."""
        rows = self.session.sql(LIST_SQL, params=[f"{DBT_SRC}/{prefix}"]).collect()
        return sorted(str(r["name"]).split("/", 1)[1] for r in rows)


class CompilerIO:
    """``GenerateIO`` (and the later stages' file access) over one session and workspace."""

    def __init__(self, session: Any, workspace: Workspace) -> None:
        self.session = session
        self.workspace = workspace
        self.files = StageFiles(session)

    def local(self, run_id: str, name: str) -> Any:
        path = self.workspace.path(run_id, name)
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.files.get(f"{run_id}/{name}"))
        return path

    def load_ir(self, run_id: str) -> WorkbookIR:
        return load_ir(self.local(run_id, IR_YAML).read_text(encoding="utf-8"))

    def cell_values(self, run_id: str) -> Mapping[CellRef, CellValue]:
        return cached_values(read_raw(self.local(run_id, WORKBOOK_DB)))

    def reviews(self, ir: WorkbookIR) -> tuple[NameReview, ...]:
        found: list[NameReview] = []
        for name in self.files.names(f"{REVIEWS}/"):
            doc = yaml.safe_load(self.files.get(name).decode("utf-8"))
            review = ReviewFile.model_validate_json(json.dumps(doc))
            if review.workbook_sha256 == ir.source.sha256:
                found.extend(review.reviews)
        return tuple(found)

    def target(self, run_id: str) -> TargetConfig:
        (row,) = self.session.sql(TARGET_SQL).collect()
        return TargetConfig(
            run_id=run_id,
            database=row["DATABASE"],
            deploy_schema=row["SCHEMA"],
            role=row["ROLE"],
            warehouse=row["WAREHOUSE"],
            dbt_version=DBT_VERSION,
        )

    def write_project(self, run_id: str, project: GeneratedProject) -> None:
        for f in project.files:
            self.files.put(f"{run_id}/{f.path}", f.content.encode("utf-8"))

    def write_input_cells(self, run_id: str, rows: tuple[WbInputCell, ...]) -> None:
        self.session.sql(DELETE_INPUTS_SQL, params=[run_id]).collect()
        insert_rows(self.session, WbInputCell, rows)

    def output_schema(self, run_id: str) -> str:
        """The run's dbt schema as dbt creates it: unquoted, so upper case."""
        target = self.target(run_id)
        return f"{target.database}.{target.output_schema.upper()}"

    def compare(self, run_id: str) -> tuple[int, tuple[CellMismatch, ...]]:
        schema = self.output_schema(run_id)
        names = [f"{schema}.{ORACLE_SEED.upper()}", f"{schema}.{FACT_MODEL.upper()}"]
        rows = self.session.sql(COMPARE_SQL, params=names).collect()
        mismatches = tuple(
            CellMismatch(
                sheet=r["SHEET"],
                cell_row=int(r["CELL_ROW"]),
                cell_col=int(r["CELL_COL"]),
                expected=_wire(r["EXPECTED"]),
                actual=_wire(r["ACTUAL"]),
            )
            for r in rows
            if r["EQUAL"] is not True
        )
        return len(rows), mismatches

    def parity_failures(self, run_id: str) -> tuple[tuple[str, int, int], ...]:
        table = f"{self.output_schema(run_id)}{AUDIT_SUFFIX}.{PARITY_TABLE}"
        rows = self.session.sql(FAILURES_SQL, params=[table]).collect()
        return tuple((r["CELL_SHEET"], int(r["CELL_ROW"]), int(r["CELL_COL"])) for r in rows)

    def write_report(self, report: EquivalenceReport) -> None:
        self.session.sql(DELETE_REPORT_SQL, params=[report.run_id]).collect()
        insert_rows(self.session, EquivalenceReport, [report])


def _wire(value: Any) -> CellValue | None:
    """A VARIANT wire object as Snowpark returns it (JSON text), or None for a missing side."""
    if value is None:
        return None
    return CellValue.model_validate_json(value if isinstance(value, str) else json.dumps(value))
