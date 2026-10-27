"""hosts/snowflake/compiler.py: the verify channels and the report row over one session."""

from __future__ import annotations

import json
from pathlib import Path

from bob_killer.contracts.ir import CellValue
from bob_killer.contracts.report import EquivalenceReport, Mismatches
from bob_killer.hosts.snowflake import compiler
from bob_killer.service.workspace import Workspace
from tests.fakes.snowpark import FakeSession
from tests.unit.conftest import sample_target

RUN_ID = "12" * 16


def _io(tmp_path: Path) -> compiler.CompilerIO:
    target = sample_target()
    s = FakeSession()
    s.script(
        compiler.TARGET_SQL,
        [
            {
                "DATABASE": target.database,
                "SCHEMA": target.deploy_schema,
                "ROLE": target.role,
                "WAREHOUSE": target.warehouse,
            }
        ],
    )
    return compiler.CompilerIO(s, Workspace(tmp_path))


def test_compare_reads_the_runs_oracle_and_fact_tables_by_bound_name(tmp_path: Path) -> None:
    io = _io(tmp_path)
    one, two = CellValue.number(1.0), CellValue.number(2.0)
    rows = [
        {
            "SHEET": "S",
            "CELL_ROW": n,
            "CELL_COL": 1,
            "EXPECTED": one.wire(),
            "ACTUAL": a,
            "EQUAL": eq,
        }
        for n, (a, eq) in enumerate([(one.wire(), True), (two.wire(), False), (None, False)], 1)
    ]
    io.session.script(compiler.COMPARE_SQL, rows)
    checked, mismatches = io.compare(RUN_ID)
    schema = io.output_schema(RUN_ID)
    (params,) = [p for q, p in io.session.statements if q == compiler.COMPARE_SQL]
    assert params == (
        f"{schema}.{compiler.ORACLE_SEED.upper()}",
        f"{schema}.{compiler.FACT_MODEL.upper()}",
    )
    assert schema == schema.upper()
    assert checked == len(rows)
    unequal = [r for r in rows if not r["EQUAL"]]
    got = [(m.cell_row, m.actual and m.actual.wire()) for m in mismatches]
    assert got == [(r["CELL_ROW"], r["ACTUAL"]) for r in unequal]


def test_parity_failures_read_dbts_stored_failures(tmp_path: Path) -> None:
    io = _io(tmp_path)
    failure = {"CELL_SHEET": "S", "CELL_ROW": 4, "CELL_COL": 2}
    io.session.script(compiler.FAILURES_SQL, [failure])
    assert io.parity_failures(RUN_ID) == (tuple(failure.values()),)
    (params,) = [p for q, p in io.session.statements if q == compiler.FAILURES_SQL]
    assert params == (f"{io.output_schema(RUN_ID)}{compiler.AUDIT_SUFFIX}.{compiler.PARITY_TABLE}",)


def test_write_report_replaces_the_runs_row(tmp_path: Path) -> None:
    io = _io(tmp_path)
    report = EquivalenceReport(
        run_id=RUN_ID,
        workbook_sha256="ab" * 32,
        denominator=3,
        cells_checked=3,
        cells_matched=3,
        mismatches=Mismatches(cells=()),
        parity_test_failures=0,
        channels_agree=True,
        steps_generated=3,
        steps_total=3,
        unsupported=0,
    )
    io.write_report(report)
    delete, insert = io.session.statements
    assert delete == (compiler.DELETE_REPORT_SQL, (RUN_ID,))
    names = list(EquivalenceReport.model_fields)
    bound = dict(zip(names, insert[1], strict=True))
    assert Mismatches.model_validate_json(bound.pop("mismatches")) == report.mismatches
    assert bound == {k: v for k, v in report.model_dump(mode="json").items() if k in bound}
    assert json.loads(json.dumps(bound))
