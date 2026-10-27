"""The MVP end to end in Snowflake: one RUN_PIPELINE call per golden (docs/review MVP checks 1-5).

The golden is staged in @UPLOADS, CREATE_RUN creates the run and RUN_PIPELINE runs every stage
inside Snowflake. Expected values come from a local run on the same bytes (the same lift, the
same registry), never from literals. Evidence goes to .context/evidence/pipeline_live_<date>.txt.
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any

import pytest
from snowflake.snowpark import Session

from bob_killer.contracts.runs import RunState, StageState
from bob_killer.hosts.snowflake import compiler, dbt, procedure, run_pipeline
from bob_killer.hosts.snowflake.reviews import lifted
from bob_killer.ir import dump_ir
from bob_killer.verify.stage import denominator
from tests.conftest import MVP_GOLDENS, golden_workbook
from tests.live.conftest import write_evidence


def _expected_stages() -> tuple[str, ...]:
    from bob_killer import registry

    with registry.stages.snapshot():
        registry.stages.clear()
        procedure.register_pipeline()
        return registry.stages.names()


def _rows(session: Session, sql: str, *params: Any) -> list[dict[str, Any]]:
    return [r.as_dict() for r in session.sql(sql, params=list(params)).collect()]


@pytest.mark.parametrize("golden_id", MVP_GOLDENS)
def test_one_upload_runs_the_whole_pipeline_inside_snowflake(
    session: Session, host_schema: str, golden_id: str
) -> None:
    session.use_schema(host_schema)
    data = golden_workbook(golden_id)
    sha = hashlib.sha256(data).hexdigest()
    session.file.put_stream(
        io.BytesIO(data), procedure.staged_path(sha), auto_compress=False, overwrite=True
    )
    created = json.loads(session.call("CREATE_RUN", f"{sha}.xlsx", f"{golden_id}.xlsx", sha))
    run_id = created["run_id"]
    view = json.loads(session.call(run_pipeline.NAME, run_id))
    local = lifted(data)

    # 1. every stage row is succeeded, in pipeline order
    stages = _rows(
        session,
        "SELECT stage, state, detail FROM STAGE_STATUS WHERE run_id = ? ORDER BY _seq",
        run_id,
    )
    assert [(s["STAGE"], s["STATE"]) for s in stages] == [
        (n, StageState.SUCCEEDED.value) for n in _expected_stages()
    ]
    assert view["run"]["state"] == RunState.SUCCEEDED.value

    # 2. CREATE DBT PROJECT at the pinned version; build returned SUCCESS = TRUE
    detail = json.loads(next(s["DETAIL"] for s in stages if s["STAGE"] == dbt.STAGE_NAME))
    assert detail["dbt_version"] == compiler.DBT_VERSION
    assert detail["build"]["success"] is True
    projects = [
        r["name"] for r in session.sql(f"SHOW DBT PROJECTS IN SCHEMA {host_schema}").collect()
    ]
    assert dbt.project_name(run_id) in projects

    # 3. the dbt parity test (bk_exact_parity, BK_VALUES_EQUAL) has zero failing rows
    io_ = compiler.CompilerIO(session, procedure.default_workspace())
    assert detail["parity"]["success"] is True
    assert io_.parity_failures(run_id) == ()

    # 4. the report: cells_matched == cells_checked == denominator, no mismatches
    (report,) = _rows(
        session,
        "SELECT denominator, cells_checked, cells_matched, mismatches, channels_agree, "
        "parity_test_failures FROM WB_REPORTS WHERE run_id = ?",
        run_id,
    )
    expected = denominator(local)
    assert report["CELLS_MATCHED"] == report["CELLS_CHECKED"] == report["DENOMINATOR"] == expected
    assert json.loads(report["MISMATCHES"])["cells"] == []
    assert report["CHANNELS_AGREE"] is True

    # 5. the IR YAML and the generated docs are on the stage under the run id
    names = compiler.StageFiles(session).names(f"{run_id}/")
    assert compiler.StageFiles(session).get(f"{run_id}/{procedure.IR_YAML}").decode() == dump_ir(
        local
    )
    docs = [n for n in names if n.startswith(f"{run_id}/docs/")]
    assert docs

    write_evidence(
        "pipeline_live",
        f"{golden_id} RUN_PIPELINE",
        json.dumps(
            {
                "run_id": run_id,
                "stages": [(s["STAGE"], s["STATE"], s["DETAIL"][:300]) for s in stages],
                "report": {k: report[k] for k in report if k != "MISMATCHES"},
                "files_on_stage": len(names),
                "docs": docs,
            },
            indent=2,
            default=str,
        ),
    )
