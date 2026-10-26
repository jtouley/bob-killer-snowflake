# One-shot MVP prompt

Paste the block below into **Claude Code on your own machine**, started at the repo root. It needs the
`bob_killer` Snowflake connection, and a cloud session doesn't have your key. Do the 3 preconditions first.
Then run it in auto mode (or with the allowlist in `.claude/settings.json`) so it isn't stopped by
permission prompts.

## Preconditions (you, ~15 min)

1. `REVOKE ROLE ACCOUNTADMIN FROM USER BOB_KILLER_SVC;` (as admin). `tools/smoke-test` passes.
2. `git fetch && git checkout snowflake-host && git pull`.
3. Edit the two `PRE-APPROVED` lines in the prompt if you disagree with them.

## The prompt

```text
Goal: the Bob Killer MVP, end to end inside Snowflake, in this one session, without asking me anything.

MVP DEFINITION (done = all true, proven by live tests and evidence):
A workbook uploaded in the Snowsight app BOB_KILLER_APP (deployed into a TEST_ schema by the live fixture and,
at the end, into APP) runs ONE procedure call, RUN_PIPELINE(run_id), that executes the stages
land_bronze -> extract -> graph -> lift -> generate -> dbt_build -> verify, all inside Snowflake. The app shows
the run state, the stage table and the equivalence report. For the goldens mt_dot_budget AND sgec_current:
  1. every stage row is succeeded;
  2. the generated dbt project is created with CREATE DBT PROJECT (dbt 1.12.3) and EXECUTE DBT PROJECT 'build'
     returns SUCCESS = TRUE;
  3. the dbt parity test (bk_exact_parity, which calls the deployed BK_VALUES_EQUAL UDF) has zero failing rows;
  4. the equivalence report says cells_matched == cells_checked == denominator, with no mismatches;
  5. the IR YAML and the generated docs are on the stage under the run id.
Out of scope for the MVP: VBA translation (inventory only if it is cheap), jedi_wind, warm_v16, mirroring every
workbook.db table as Snowflake tables, the IronCalc oracle.

CONTEXT TO READ FIRST (in this order, then stop reading):
docs/review/REVIEW_2026-10-26.md (what exists, the gaps, the CI fix), labs/bob_killer/CLAUDE.md,
labs/bob_killer/AGENTS.md, docs/SPEC-compiler-dbt.md sections 3, 4, 5 and Phases 12, 14 and 15, docs/evidence/dbt_demo/*.py
(the working glue to promote), docs/evidence/dbt_in_snowflake_mt_dot_budget_20261016.md,
labs/bob_killer/src/bob_killer/hosts/snowflake/procedure.py, labs/bob_killer/src/bob_killer_sis/streamlit_app.py.

HOW TO WORK:
- Branch: stay on snowflake-host. Work from labs/bob_killer/. You build directly; do NOT use CoCo, tools/coco-*,
  or /cadence for this run.
- Follow the CLAUDE.md TDD loop for every unit: red test plus `uv run python scripts/record_run.py --phase red ...`
  committed together, then green, then refactor. Commit subjects `mvp/<red|green|refactor|scaffold>: <what>`, ONE
  trailer paragraph with TDD-Phase. Never edit an existing assertion. Never put a literal expected value in an
  assert: expected values come from golden cached values, tests/oracle/*.json, or an independent computation.
- Offline tests use the one FakeSession in tests/fakes/snowpark.py (extend it). Live tests go in tests/live/
  with @pytest.mark.live, in a TEST_<uuid8> schema that the existing fixture creates and drops. Never skip.
- After every green: `uv run pytest -q`, `uv run lint-imports`, `uv run mypy src`. Before every push:
  `uv run python scripts/gates.py --base 77fcc0781036da5accec50e0389b8c7e75653485` exits 0.
- Never use an admin role. Never write credentials, the account id or pandas into any file. Bound values only in SQL.

STEPS (in order; each ends green and pushed):
0. CI green first. Add the numpy mypy override from REVIEW section 3.1.1 to labs/bob_killer/pyproject.toml as a
   `TDD-Phase: gate-change` commit (the only gate change allowed in this run). Push. Open a DRAFT PR snowflake-host -> main
   titled "Bob Killer Snowflake host + compiler MVP", body links #1 and #2. CI must be green before step 1.
1. Stage context in the procedure. In procedure.py, register land_bronze, extract, graph and lift (their existing
   register_stages functions; registry order test: land_bronze, extract, graph, lift). In each handler call, bind
   the extract/graph/lift inputs to: workbook bytes via session.file.get_stream of @UPLOADS/<sha>.xlsx, and a
   per-run SQLite workbook.db under tempfile.gettempdir(). After the run, put workbook.db and ir.yaml on
   @DBT_SRC/<run_id>/ (auto_compress=False). Create stage DBT_SRC in a new hosts/snowflake/sql/20_compiler_objects.sql;
   99_teardown.sql also drops <schema>__R_% schemas.
2. Runtime UDFs. Add src/bob_killer/hosts/snowflake/udfs.py. It generates one Python 3.12 UDF per entry in
   registry.functions (BK_FN_<NAME>) and per operator (BK_OP_<NAME>), plus BK_VALUES_EQUAL wrapping
   verify.config.values_equal, from the registry only (no hand list). The handlers import the build zip. Generated
   DDL goes to hosts/snowflake/sql/30_udfs.sql with a golden drift test. Use runtime/operators.py; delete
   nothing in docs/evidence, but do not import from it. Live test: the UDFs return the same wire value as the
   Python runtime for every golden corpus case of mt_dot_budget and sgec_current.
3. Generate stage. Register `generate`. It runs registry.generators (dbt and docs) on the run's IR and writes
   every file to @DBT_SRC/<run_id>/dbt/ and /docs/, plus WB_INPUT_CELLS rows (the golden's input cached values as
   wire JSON) and the bk_oracle seed. Logic is promoted from docs/evidence/dbt_demo/gen_dbt.py.
4. dbt_build stage, in src/bob_killer/hosts/snowflake/dbt.py: CREATE OR REPLACE DBT PROJECT BK_<run_id8> FROM
   @DBT_SRC/<run_id>/dbt DBT_VERSION='1.12.3', then EXECUTE DBT PROJECT ... ARGS='build --target ...' into schema
   <schema>__R_<run_id8>. SUCCESS=FALSE fails the stage with the dbt output as the detail. A parity-test failure
   does not fail this stage (verify reports it). FakeSession tests script both outcomes.
5. verify stage plus EquivalenceReport. A strict contract in contracts/ goes through the D31 bump rules and
   export_contracts, and the app schemas.json copy is refreshed. Two channels: (a) the dbt parity failures table,
   (b) a SQL compare of FCT_FORMULA_CELLS vs BK_ORACLE via BK_VALUES_EQUAL. The run fails if the channels disagree.
   Write the report row to a WB_REPORTS table.
6. RUN_PIPELINE(run_id) procedure in snowflake.yml (runtime 3.12, packages per the existing F3 evidence plus
   jinja2 and pyyaml). It runs all stages in order through the core execute_run. If one procedure call cannot run dbt
   (EXECUTE DBT PROJECT inside an owner's-rights procedure), use the SPEC-compiler-dbt D18 split instead:
   EXECUTE_RUN up to the foreign stage, dbt_build, EXECUTE_RUN to resume. Caller's rights if required. Record which one worked in evidence.
7. App. streamlit_app.py calls RUN_PIPELINE with block=False after CREATE_RUN, polls RUNS/STAGE_STATUS/WB_REPORTS,
   and shows the stage table, report counts, the mismatch table and the docs stage path. AppTest covers the
   happy path, a rejected upload, and a report row that fails JSON Schema. Still Python 3.11, still never imports bob_killer.
8. Live end to end (tests/live/test_pipeline.py, parametrized over mt_dot_budget and sgec_current): stage the
   golden, CREATE_RUN, RUN_PIPELINE, then assert MVP checks 1–5. Expected counts come from the local run on the same bytes, not from literals.
9. Deploy to APP with the documented build+deploy commands, upload mt_dot_budget once through the same procedures,
   and write the query outputs to .context/evidence/mvp_<date>.md (account redacted to <ACCOUNT>).
   Tag the commit deploy/mvp-<short-sha> and push the tag.
10. Docs: update the root README status table and labs/bob_killer/README.md (remove the "Incubating in sandbox"
   line). hosts/snowflake/README.md gets one-command deploy and teardown. Mark the PR ready for review and comment
   the evidence summary.

PRE-APPROVED (do not ask me):
- PRE-APPROVED naming: for mt_dot_budget and sgec_current, accept the deterministic naming rule's top choice for every
  output-facing needs_review node. Commit them as hosts/snowflake/reviews/<golden>.yaml with reviewer "jtouley",
  reason "MVP pre-approval 2026-10-26". Also write the full queue to .context/evidence/review_queue_<golden>.md so I can revisit.
- PRE-APPROVED dependencies: jinja2, pyyaml, openpyxl, oletools (already present) and any Snowflake-channel package the
  F3 evidence lists. Any other new dependency: stop.

STOP AND REPORT (do not route around) when: a platform fact is false in this account; a function needs a
tolerance to match Excel (that would need an ALLOWLIST.md row, which is my decision); a gate fails and the fix
would change a gate; three fix attempts on one step fail. When you stop, push what is green, update the PR body
with a checklist of steps 0–10 (done / blocked + reason), and end.

FINAL MESSAGE: the PR URL, the checklist, the report counts per golden, and the evidence file path.
```

## Why this works as one shot

- It names a **narrow, checkable MVP** (2 goldens, 7 stages, 5 signals) instead of the full Phase 9–16 goal.
- It points at the **existing glue** (`docs/evidence/dbt_demo/`), so nothing is reinvented.
- It **pre-decides** the only human-in-the-loop steps: name review, dependencies, and the RUN_PIPELINE fallback.
  It also gives explicit stop rules, so an unattended run can't stall on a question or cheat past a gate.
- It keeps the anti-cheat gates and drops the CoCo bridge overhead.
