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
from bob_killer.contracts.workbook import NameReview, ReviewFile, WbInputCell
from bob_killer.extract.raw_db import read_raw
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
