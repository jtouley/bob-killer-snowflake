# Bob Killer compiler and dbt target in Snowflake — Build Spec (Phases 9–16)

Oct 16, 2026 · Jason Touleyrou · Status: r1 draft for issue jtouley/bob-killer-snowflake#2 · Builds on `docs/SPEC.md` r9-scope

This file is the build spec for host Phases 9–16. It extends `docs/SPEC.md`. It does not replace it.

**Authority.** These documents are binding, in this order:

1. `labs/bob_killer/SPEC.md` (core SPEC): the compiler design, the IR, the registries, core decisions 1–10.
2. `labs/bob_killer/CLAUDE.md` and `labs/bob_killer/AGENTS.md`: the TDD loop, the hard rules, the test rules.
3. `docs/SPEC.md`: the Snowflake host, §2.0 goal, §4 facts F1–F10, D1–D16, Phases 1–8.
4. This file: the compiler in Snowflake and the dbt target.

This file adds rules. Where it adds to a decision in a document above, it says so and names the decision.
If an agent finds a conflict that this file does not settle, the agent stops with status blocked and names it.

**Names.** "Phase N" is a host phase. A core phase is "core SPEC Phase N". "Golden" means a workbook of core
SPEC "Golden sample set". "Goal set" is defined in §1.2. Paths are relative to `labs/bob_killer/` unless
they start with `../../` or name the repo root.

---

## 1. Goal and done-definition

### 1.1 The goal

The user's words: "this fails if it doesn't meet my goal of having the bob-killer features and dbt projects
in snowflake".

A user uploads a workbook in Snowsight. Snowflake does all of these steps. Nothing runs on the Mac.

1. **Extract** every cell, formula, cached value, defined name, table and VBA module into the run's
   `workbook.db` tables in Snowflake (core SPEC stage 1, core decision 9).
2. **Graph** the formulas into a dependency DAG. Flag cycles, volatile functions and dynamic references (stage 2).
3. **Lift** the graph into the Workbook IR with the shared Excel runtime (`runtime/`, stage 3, core decision 5).
4. **Generate** a dbt project and docs from the IR, through `registry.generators` (D14).
5. **Deploy and run** the dbt project as a dbt Project on Snowflake (`CREATE DBT PROJECT`, `EXECUTE DBT PROJECT`).
6. **Verify** every non-VBA formula output exactly against Excel's cached values, with dbt parity tests and an
   equivalence report (D15, core decision 1).
7. **VBA**: inventory every module, list the cells a macro can write, translate pure-computation procedures
   behind tests (core decision 6, core SPEC Phase 5).

### 1.2 Done-definition

The **goal set** is these goldens from `golden.lock`: `mt_dot_budget`, `iwarm`, `sgec_current`, `jedi_wind`.
`sgec_v4_1` and `sgec_v5_1` join the goal set when Phase 9 pins them. `warm_v16` is not in the goal set,
because it is `.xls` and needs the Excel oracle to convert it (§1.3 L6).

The run is done when Phase 16's exit holds. For **each** workbook in the goal set, from one upload into a
TEST_ schema through the same procedures that the Snowsight app calls:

1. The run state is `succeeded`. Every stage row is `succeeded`.
2. `WB_CELLS` holds every cell, and `WB_VBA_MODULES` holds every VBA module of the workbook.
3. The IR round-trips: `workbook.db` → YAML → `workbook.db` is identical.
4. A dbt project object for the run exists. `EXECUTE DBT PROJECT` returned `SUCCESS = TRUE` for the build.
5. The dbt parity test returned zero failing rows.
6. The equivalence report says `cells_matched == cells_checked == denominator`. Its mismatch list is empty.
   No denominator cell is in the unsupported list.
7. The docs exist on the stage and in the dbt docs archive.
8. Every VBA procedure has a classification. Every macro-writable cell is listed.

After the merge, the user uploads each goal-set workbook in the Snowsight app (schema `APP`) and checks the
same signals. The query outputs go to `.context/evidence/`.

### 1.3 Honest limits

| # | Limit | Consequence |
| --- | --- | --- |
| L1 | There is no Excel on this Mac. | Nobody can author a new formula fixture. The cached values of the goldens are the fixture oracle for Phases 9–16 (`docs/SPEC.md` §2.2). A test that needs a fixture that only Excel can make is a blocked item with a reason. It is never a fake fixture. |
| L2 | The Excel oracle runner (desktop Excel or Microsoft Graph) is out of scope (`docs/SPEC.md` §2.3). | Cached values prove one input set per workbook. Other input sets, and runs with overridden dbt vars, are listed as unverified in every report. They are never approximated. |
| L3 | Excel's summation order and other numeric details are not documented. | The runtime infers them only from the goldens' cached values. A function or an order that no golden exercises is unproven. The report lists the functions that the goldens do not exercise. |
| L4 | Assumption A1: Excel writes each cached double with enough digits to read back the same double. | This cannot be checked without Excel. A mismatch that traces to A1 is reported with that root cause. |
| L5 | A formula fixture needs a file that Excel saved. | Phase 11 rejects a golden that Excel did not save (`docProps/app.xml`) or that has a formula cell with no cached value. |
| L6 | `warm_v16` is `.xls`. | It is out of the goal set until the oracle runner converts it. It stays in `golden.lock` and in the report. |
| L7 | VBA is never executed (core CLAUDE.md). | A translation is verified only when its output equals the cached values of the cells it writes. Otherwise it is listed as unverified, and its cells stay out of the denominator (§6). |
| L8 | Volatile functions (`NOW`, `RAND`, …) give a new value on each recalculation. | A volatile cell is frozen at its cached value as an input, is listed, and leaves the denominator. Its dependents stay in the denominator (D24). |
| L9 | Core decision 3: generation fails while an output-facing name is `needs_review`. | A human must review the output-facing names of each golden. CoCo cannot do this. Phase 13 lists the queue; you review it (§8, Phase 13). |
| L10 | dbt Python models are not documented for dbt Projects on Snowflake (F17). | The design does not use them. Excel semantics come from Python UDFs called from SQL models. |
| L11 | Golden files are not committed. NREL and Montana redistribution terms are not checked. | Files come from `scripts/fetch_golden.py` into gitignored `golden/`. Committed snapshots of generated output are hash manifests, not content. |
| L12 | Pivot tables, Power Query, Solver, data tables, charts and external links are core non-goals. | They appear in the coverage report. A golden whose denominator cells depend on one of them fails the goal. The core rule applies: extend the scope or swap the golden; never lower the gate. |
| L13 | A large golden (JEDI) can exceed procedure memory or run time on an XS warehouse. | Phase 11 measures each golden. D16 allows one procedure call per stage. A larger warehouse is a user decision. |
| L14 | Each dbt Core version has a support end date on Snowflake (F13). | The project pins one version (D29). A later bump is one config change and one live test run. |

---

## 2. Platform facts and constraints

From Snowflake docs and the Snowflake Anaconda channel, opened 2026-10-16. Phase 10 verifies each fact in
your account. It writes the output to `.context/evidence/snowflake_compiler_<date>.md`. A false fact in the
"stop" column stops the run blocked with the fact named. A false fact without "stop" switches to the named fallback.

| # | Fact | Source | Consequence | Phase 10 check | Stop? |
| --- | --- | --- | --- | --- | --- |
| F11 | `CREATE [OR REPLACE] DBT PROJECT <db.schema.name> FROM '<source>'` accepts an internal named stage, a workspace, an existing dbt project, or a Git repository stage. The source root holds one `dbt_project.yml`. The role needs `CREATE DBT PROJECT` on the schema. `OR REPLACE` can remove run history. | https://docs.snowflake.com/en/sql-reference/sql/create-dbt-project | Generated files go to stage `DBT_SRC` at `<run_id>/`. The project is created from `'@DBT_SRC/<run_id>'`. One project object per run, so no `OR REPLACE`. | In a TEST_ schema: `CREATE DBT PROJECT <db>.<test>.BK_HELLO FROM '@<db>.<test>.DBT_SRC/hello'`; `SHOW DBT PROJECTS IN SCHEMA <db>.<test>` lists it. | Stop |
| F12 | `EXECUTE DBT PROJECT <name> [ARGS = '<dbt command and options>'] [DBT_VERSION = '<v>']`. Without `ARGS` it runs `dbt run`. It returns `SUCCESS`, `EXCEPTION`, `STDOUT`, `OUTPUT_ARCHIVE_URL`. It needs `USAGE` on the project. Artifacts are stored even with `WRITEBACK = FALSE`. | https://docs.snowflake.com/en/sql-reference/sql/execute-dbt-project | The `dbt_build` stage reads `SUCCESS` and `STDOUT`, and records `OUTPUT_ARCHIVE_URL` as the stage detail. | `EXECUTE DBT PROJECT BK_HELLO ARGS = 'build'` returns `SUCCESS = TRUE`; record all four columns. | Stop |
| F13 | Supported dbt Core versions: 1.12.3 (active support to 2027-07-15), 1.11.11 (to 2026-12-18), 1.10.15, 1.9.4. `EXECUTE DBT PROJECT` uses 1.9.4 when no version is set; the account parameter `DEFAULT_DBT_VERSION` can change the default. | https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-dbt-core-versions | Pin `DBT_VERSION = '1.12.3'` on create and on execute (D29). | `SHOW PARAMETERS LIKE 'DEFAULT_DBT_VERSION' IN ACCOUNT`; the hello build `STDOUT` contains `Running with dbt=1.12.3`. | Stop if 1.12.3 is refused; then pin the newest accepted version and record it. |
| F14 | The project needs `profiles.yml` or `dbt_projects_profiles.yml` (the second wins). The target sets `type: snowflake`, `warehouse`, `database`, `schema`, `role`. "dbt requires an `account` and `user`, but these can be left with an empty or arbitrary string." The dbt command runs with the role in the `outputs` block. | https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-limitations, https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control | The generator writes `profiles.yml` with empty `account` and `user`, and the role, warehouse and database from `CURRENT_ROLE()`, `CURRENT_WAREHOUSE()`, `CURRENT_DATABASE()` of the procedure. No secret is in any file. | The hello project deploys and builds with `account: ""` and `user: ""`. | Stop |
| F15 | "When you use a stored procedure to call EXECUTE DBT PROJECT, use a caller's rights stored procedure." | https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-limitations | `EXECUTE_RUN` is owner's rights (D1), so it cannot run dbt. A new caller's-rights procedure `RUN_PIPELINE` runs the `dbt_build` stage (D18). | Call `EXECUTE DBT PROJECT` from an owner's-rights 3.12 procedure (record the error) and from a caller's-rights one (succeeds). | Stop if the caller's-rights call fails. |
| F16 | `EXECUTE DBT PROJECT` supports `build`, `seed`, `run`, `test`, `compile`, `parse`, `deps`, `docs generate`, and others. `snow dbt execute` does not support `docs generate`. `dbt docs serve` is not supported; use `dbt docs generate --static`. The flags `--profiles-dir`, `--project-dir`, `--log-format`, `--log-format-file` are not supported. | https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-supported-commands | Docs come from `ARGS = 'docs generate --static'`. Generated ARGS never use the unsupported flags. | `EXECUTE DBT PROJECT BK_HELLO ARGS = 'docs generate --static'`; the archive at `OUTPUT_ARCHIVE_URL` holds `static_index.html`. | No: docs then come only from the docs generator (§4.6). |
| F17 | Snowflake's dbt Projects pages do not document dbt Python models. | https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake (and the pages above) | Not used (D19). | Informational: a hello project with one Python model; record the result. | No |
| F18 | `snow dbt deploy <name> --source <dir> --profiles-dir <dir> [--force] [--dbt-version <v>] [--default-target <t>] [--external-access-integration <i>]` uploads to a temporary stage and creates or updates the project. Snowflake CLI 3.29.0 on this Mac has `snow dbt deploy|execute|describe|list|drop|copy` (checked 2026-10-16 with `uv run snow dbt --help`). | https://docs.snowflake.com/en/developer-guide/snowflake-cli/command-reference/dbt-commands/deploy | The manual path from the Mac. Phase 14 uses it to deploy a locally generated project. The in-run path uses SQL (F11). | `uv run --project ../.. snow dbt deploy -c bob_killer BK_HELLO_CLI --source tests/fixtures/dbt_hello --dbt-version 1.12.3` with the TEST_ schema. | No |
| F19 | Python UDFs support runtimes 3.10–3.14 (3.9 is deprecated). Code comes from stage imports; packages come from the Anaconda channel. | https://docs.snowflake.com/en/developer-guide/udf/python/udf-python-introduction | UDFs run the core `runtime/` from the same build zip as the procedures, `RUNTIME_VERSION = '3.12'` (D20). | `CREATE FUNCTION BK_PING() RETURNS VARCHAR LANGUAGE PYTHON RUNTIME_VERSION = '3.12' IMPORTS = ('<build zip>') HANDLER = …` returns `sys.version` and imports `bob_killer.runtime`. | Stop |
| F20 | The artifact repository `snowflake.snowpark.pypi_shared_repository` installs PyPI packages into UDFs and procedures with `ARTIFACT_REPOSITORY = …` and `PACKAGES = (…)`. The database role `SNOWFLAKE.PYPI_REPOSITORY_USER` is granted to PUBLIC by default. | https://docs.snowflake.com/en/developer-guide/udf/python/udf-python-packages | oletools comes from PyPI this way (D23). | A 3.12 procedure with `ARTIFACT_REPOSITORY = snowflake.snowpark.pypi_shared_repository PACKAGES = ('oletools')` returns `oletools.olevba.__version__`. | No: fallback is oletools in the build zip (D23). Stop only if both fail. |
| F21 | The Snowflake Anaconda channel (`repo.anaconda.com/pkgs/snowflake`, `repodata.json` read 2026-10-16) has **no** `oletools` and **no** `pcodedmp`. It has `olefile 0.46` (noarch), `openpyxl 3.1.5`, `jinja2 3.1.6`, `pyyaml 6.0.3`, `pydantic 2.11.9` and `2.13.5`, `polars 1.41.2`, `cryptography 50.0.0` for py312. | https://repo.anaconda.com/pkgs/snowflake/ | Procedure packages for the compiler: `openpyxl`, `jinja2`, `pyyaml` from Anaconda; `oletools` per F20. | `SELECT package_name, version FROM information_schema.packages WHERE language = 'python' AND runtime_version = '3.12' AND package_name IN ('oletools','olefile','openpyxl','jinja2','pyyaml','pyparsing')`. | No |
| F22 | Python type mapping: `FLOAT`↔`float`; `NUMBER` with scale 0 → `int`, else `decimal.Decimal`; `VARIANT` converts dynamically; `ARRAY`→`list`; `OBJECT`→`dict`; a decimal inside an ARRAY or OBJECT becomes a string. | https://docs.snowflake.com/en/developer-guide/udf-stored-procedure-data-type-mapping | No double crosses SQL as `NUMBER` or as a bare float. Doubles cross as `float.hex()` text inside the CellValue wire object (D21). | A UDF that receives an OBJECT built by `OBJECT_CONSTRUCT` returns the Python type names of its values; record them. | No |
| F23 | `ARRAY_AGG(…) WITHIN GROUP (ORDER BY …)` orders the elements. NULL values are omitted. One call returns at most 128 MB. | https://docs.snowflake.com/en/sql-reference/functions/array_agg | Ranges reach a UDF as `ARRAY_AGG(<wire object>) WITHIN GROUP (ORDER BY <excel order>)`. A blank is a wire object, not NULL, so it is kept. A range over 128 MB is unsupported. | `ARRAY_AGG` of 1 000 wire objects with shuffled insert order, ordered by row and column, equals the expected order; a blank wire stays in the array. | Stop |
| F24 | Assumption, not documented: a double survives every boundary bit for bit (qmark bind into `FLOAT`, `FLOAT` UDF argument and return, `ARRAY_AGG` of `FLOAT`, a float inside a returned `OBJECT`). | none | The design does not depend on it (D21). It only enables a later optimization. | 10 000 hypothesis doubles (incl. `-0.0`, subnormals, the largest and smallest normals, 17-digit values) per boundary, compared by `float.hex()`. Record pass or fail per boundary. | No |
| F25 | Assumption, not documented here: `session.file.put_stream` works inside a 3.12 owner's-rights procedure to write to an internal stage (F6 proves it from a client). | none | The `generate` stage writes the dbt files to `@DBT_SRC/<run_id>/` from inside `EXECUTE_RUN`. | A procedure writes three files and lists them; SHA-256 of each read-back file equals the source. | No: fallback is `COPY INTO @DBT_SRC/<path> FROM (SELECT <bound text>) FILE_FORMAT = (TYPE = CSV COMPRESSION = NONE …) SINGLE = TRUE`. |
| F26 | Assumption, not documented: `CREATE DBT PROJECT` runs inside a caller's-rights procedure. | none | `RUN_PIPELINE` creates the project before it executes it. | Create the hello project from a caller's-rights procedure. | Stop |
| F27 | A deployed dbt project folder holds at most 100 000 files. The Snowsight DAG shows at most 300 models. Serverless tasks cannot run dbt projects; a user-managed warehouse is needed. | https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-limitations | One model per vectorized step and one per sheet level of scalar steps (D26). `BOB_KILLER_WH` runs every execution. | Phase 14 records the model count per golden. | No |
| F28 | `AI_COMPLETE` needs a role with the database role `SNOWFLAKE.CORTEX_USER`. It returns NULL on error unless `return_error_details` is set. | https://docs.snowflake.com/en/sql-reference/functions/ai_complete | VBA translation runs in Snowflake with `AI_COMPLETE` (D27). | `SELECT AI_COMPLETE('<model>', 'Reply with OK')` as `BOB_KILLER_OWNER` from a 3.12 procedure; record the model names that work in this region. | No: translation then stays `untranslated`, listed (§6). |
| F29 | Assumption: `CURRENT_USER()` inside a caller's-rights procedure returns the calling user. The rights page describes caller's and owner's rights but does not state this. | https://docs.snowflake.com/en/developer-guide/stored-procedure/stored-procedures-rights (does not state it) | The review procedure `REVIEW_NODE` records the reviewer from `CURRENT_USER()` (D25). | A caller's-rights procedure returns `CURRENT_USER()`; it equals the session user. | Stop if it returns the owner. |

Local facts (no Snowflake), checked in Phase 9 and recorded in `.context/evidence/compiler_local_<date>.md`:

| # | Fact | Phase 9 check |
| --- | --- | --- |
| L-F1 | `dbt parse` with dbt-core 1.12.3 and dbt-snowflake runs with no warehouse connection. | `uv tool run --from 'dbt-core==1.12.3' --with 'dbt-snowflake' dbt parse --project-dir tests/fixtures/dbt_hello --profiles-dir tests/fixtures/dbt_hello` exits 0 with no network to Snowflake. |
| L-F2 | oletools runs on 3.12 with the project's pinned set. | `uv run python -c "import oletools.olevba"` after `uv lock`. |

---

## 3. Architecture

```mermaid
flowchart LR
  U[User in Snowsight] --> A[SiS app 3.11]
  A -- put_stream --> S[(@UPLOADS/sha.xlsx)]
  A -- CALL CREATE_RUN --> C[CREATE_RUN 3.12 owner's rights]
  A -- CALL RUN_PIPELINE block=False --> P[RUN_PIPELINE 3.12 caller's rights]
  P -- CALL EXECUTE_RUN --> E[EXECUTE_RUN 3.12 owner's rights<br/>land_bronze, extract, graph, lift, generate]
  E --> W[(WB_* tables)]
  E -- put_stream --> D[(@DBT_SRC/run_id/)]
  P -- dbt_build stage --> X[CREATE DBT PROJECT FROM @DBT_SRC/run_id<br/>EXECUTE DBT PROJECT]
  X --> O[(schema DEPLOY__R_run_id: seeds, models, marts, test failures)]
  X -- calls --> F[Python UDFs BK_* from runtime/]
  P -- CALL EXECUTE_RUN again --> V[verify stage]
  V --> R[(WB_REPORTS, @DBT_SRC/run_id/report.md)]
  A -- SELECT by run_id --> R
```

### 3.1 Where each stage runs

| Stage (registry order) | Runs in | Reads | Writes |
| --- | --- | --- | --- |
| `land_bronze` | `EXECUTE_RUN` (Phase 5–6) | `@UPLOADS` | `LANDED_FILES`, `BRONZE_ROWS` |
| `extract` | `EXECUTE_RUN` | `@UPLOADS` | Raw layer: `WB_SHEETS`, `WB_CELLS`, `WB_DEFINED_NAMES`, `WB_TABLES`, `WB_VBA_MODULES`, `WB_VBA_PROCEDURES`, `WB_MACRO_WRITES`, `WB_UNSUPPORTED` |
| `graph` | `EXECUTE_RUN` | Raw layer | Dictionary: `WB_NODES`, `WB_EDGES`; adds to `WB_UNSUPPORTED` |
| `lift` | `EXECUTE_RUN` | Raw, Dictionary, `WB_REVIEWS` | Dictionary: `WB_NODES`, `WB_NAMES`, IR YAML on `@DBT_SRC/<run_id>/ir.yaml` |
| `generate` | `EXECUTE_RUN` | IR | `@DBT_SRC/<run_id>/` (dbt project, docs); `WB_GENERATED_FILES` |
| `dbt_build` | `RUN_PIPELINE` (caller's rights, F15) | `@DBT_SRC/<run_id>/` | dbt project object `BK_DBT_<run_id>`; schema `<DEPLOY>__R_<run_id>` |
| `verify` | `EXECUTE_RUN` (second call) | `WB_CELLS`, the dbt output schema | `WB_REPORTS`, `@DBT_SRC/<run_id>/report.md` |

`RUN_PIPELINE(run_id)` does three things in order. It calls `EXECUTE_RUN(run_id)`. It runs the `dbt_build`
stage in its own process. It calls `EXECUTE_RUN(run_id)` again. Each call runs only the stages it may run (D18).
The app calls `RUN_PIPELINE` in place of `EXECUTE_RUN`, with `block=False`, and polls as before.

Measure first (Phase 11). If one stage on one golden exceeds the procedure limits, `RUN_PIPELINE` calls
`EXECUTE_RUN` once per stage (D16).

### 3.2 Stage context

A core stage receives only the run id (`Stage = Callable[[str], str | None]`, D3). A context variable in
`bob_killer.service.context` carries a `RunContext` for the call:

- `workbooks: WorkbookRepository` (the store for the `workbook.db` layers),
- `blobs: BlobStore` (`read_upload(run_id) -> bytes`, `write_files(run_id, files) -> None`,
  `read_file(run_id, path) -> bytes`),
- `target: TargetConfig` (contract: database, deployment schema, role, warehouse, dbt version).

The CLI sets a SQLite store, a local directory blob store (`build/<run_id>/`) and a local target. The procedure
handler sets `SnowflakeWorkbookStore`, a stage blob store (`@UPLOADS`, `@DBT_SRC`) and the target from
`CURRENT_DATABASE()`, `CURRENT_SCHEMA()`, `CURRENT_ROLE()`, `CURRENT_WAREHOUSE()`. Each stage has one
implementation for both hosts. This is the D4 pattern, used for every compiler stage.

### 3.3 `workbook.db` in Snowflake (RunRepository and dialect pattern)

Every `workbook.db` table of core decision 9 is one strict model in `src/bob_killer/contracts/workbook.py`.
`WORKBOOK_TABLES` lists them. The SQLite dialect and the Snowflake dialect of `contracts/ddl.py` generate the DDL
(D2). There is no hand-written DDL.

| Core table (decision 9) | Model | SQLite table | Snowflake table | Primary key (informational in Snowflake, F4) |
| --- | --- | --- | --- | --- |
| `sheets` | `WbSheet` | `wb_sheets` | `WB_SHEETS` | `run_id, sheet_index` |
| `cells` | `WbCell` | `wb_cells` | `WB_CELLS` | `run_id, sheet, row, col` |
| `defined_names` | `WbDefinedName` | `wb_defined_names` | `WB_DEFINED_NAMES` | `run_id, name, scope` |
| `tables` | `WbTable` | `wb_tables` | `WB_TABLES` | `run_id, table_name` |
| `vba_modules` | `WbVbaModule` | `wb_vba_modules` | `WB_VBA_MODULES` | `run_id, module` |
| (VBA detail, §6) | `WbVbaProcedure`, `WbMacroWrite` | `wb_vba_procedures`, `wb_macro_writes` | `WB_VBA_PROCEDURES`, `WB_MACRO_WRITES` | `run_id, module, procedure` / `run_id, module, procedure, target` |
| `unsupported` | `WbUnsupported` | `wb_unsupported` | `WB_UNSUPPORTED` | `run_id, kind, origin` |
| `nodes` | `WbNode` | `wb_nodes` | `WB_NODES` | `run_id, node_id` |
| `names` | `WbName` | `wb_names` | `WB_NAMES` | `run_id, node_id` |
| `relationships` | `WbEdge` | `wb_edges` | `WB_EDGES` | `run_id, src, dst` |
| `reviews` | `WbReview` | `wb_reviews` | `WB_REVIEWS` | `review_id` (not per run: decisions reapply across runs by origin and fingerprint) |
| (host) | `WbGeneratedFile` | `wb_generated_files` | `WB_GENERATED_FILES` | `run_id, path` |
| (host) | `EquivalenceReport` row `WbReport` | `wb_reports` | `WB_REPORTS` | `run_id` |

Rules:

- Every per-run model has `run_id` as its first key column, in both dialects. One schema holds many runs (D7).
- A cell value is the contract `CellValue` (D21). It is a nested model, so it is `VARIANT` in Snowflake and JSON
  text in SQLite. Its number is `float.hex()` text. No double is stored as `FLOAT` or `REAL` in `workbook.db`.
- An optional field (`str | None`) becomes a nullable column in both dialects. Phase 11 adds this rule to both
  dialects. The `TABLES` DDL does not change (no optional field), so `snapshots/v1/ddl.sql` stays byte-identical.
- `WorkbookRepository` is a Protocol in `src/bob_killer/store/__init__.py`, next to `RunRepository`. `WorkbookStore`
  (`store/workbook.py`) implements it on SQLite. `SnowflakeWorkbookStore` (`hosts/snowflake/store.py`) implements it on
  a session. One shared suite runs on both (Phase 4 pattern).
- Bulk writes in Snowflake use the batched `INSERT … SELECT PARSE_JSON(?)` writer of Phase 5, moved to
  `hosts/snowflake/batch.py` as `BatchWriter` and used by bronze and by the workbook store (a refactor commit).
  A stage that runs again for a run first deletes that run's rows in its own layer, in one transaction (F10).
- Reads validate every row with the strict model. A bad value from the database raises.
- `SNOWFLAKE_TABLES` adds `WORKBOOK_TABLES`. The ODCS contract (D13) is regenerated from it.
- The host creates one view `WB_INPUT_CELLS`: the `WB_CELLS` rows whose node kind in `WB_NODES` is `input` or
  `frozen_volatile`. It is the only `workbook.db` object that a generated dbt model may read (D22).

### 3.4 How generated files reach a stage and a dbt project

1. The `generate` stage calls every entry of `registry.generators` in name order. Each returns a `GeneratedProject`
   (contract: a tuple of `GeneratedFile(path, content, sha256)`, sorted by path, with no timestamps).
2. `blobs.write_files(run_id, files)` writes each file to `@DBT_SRC/<run_id>/<path>` with `auto_compress=False`
   (F6, F25). It writes one `WbGeneratedFile` row per file.
3. The `dbt_build` stage (in `RUN_PIPELINE`) runs, in order:
   `CREATE DBT PROJECT <db>.<deploy>.BK_DBT_<run_id> FROM '@<db>.<deploy>.DBT_SRC/<run_id>/dbt' DBT_VERSION = '<pinned>'`;
   `EXECUTE DBT PROJECT … ARGS = 'build --exclude tag:bk_parity'`;
   `EXECUTE DBT PROJECT … ARGS = 'test --select tag:bk_parity'`;
   `EXECUTE DBT PROJECT … ARGS = 'docs generate --static'`.
   The first two must return `SUCCESS = TRUE`, or the stage fails with `EXCEPTION` as its detail. The parity test
   result is recorded, not raised: the `verify` stage reads it and fails the run on any mismatch.
4. The stage detail holds the three `OUTPUT_ARCHIVE_URL` values as JSON text.
5. The CLI path writes the same files to `build/<run_id>/`. You deploy them by hand with
   `uv run --project ../.. snow dbt deploy -c bob_killer BK_DBT_<run_id> --source build/<run_id>/dbt --dbt-version <pinned>` (F18).

Objects per deployment schema `<DEPLOY>` (`APP` or `TEST_<uuid8>`): stage `DBT_SRC` (internal, server-side
encryption, directory on), view `WB_INPUT_CELLS`, the `WB_*` tables, the `BK_*` UDFs, the procedures
`RUN_PIPELINE` and `REVIEW_NODE`. Per run: project object `BK_DBT_<run_id>` and output schema
`<DEPLOY>__R_<run_id>`. `99_teardown.sql <schema>` also drops every schema named `<schema>__R_%` (Phase 15).

### 3.5 Boundary rules (additions to `docs/SPEC.md` §5.3)

- `bob_killer.generate` never imports `bob_killer.runtime` (import-linter, Phase 9). A generator reads function
  metadata from `registry.functions` only. It never evaluates Excel semantics.
- Stages never import each other (the existing `|` layer). The IR in `contracts/ir.py` is the only contract between
  stages (core SPEC "DRY rules").
- Only `hosts/snowflake/procedure.py` and `hosts/snowflake/dbt.py` get a session from Snowpark.
- Generated SQL never holds user data as a literal except through the hex encoding of D21 inside a seed or a var.
  Identifiers in generated SQL come from `WB_NAMES` and are quoted by one function.

---

## 4. The dbt generator design

### 4.1 Shape

`src/bob_killer/generate/base.py` defines the `Generator` Protocol: `generate(ir: WorkbookIR, target: TargetConfig) -> GeneratedProject`.
`src/bob_killer/generate/dbt/` registers `"dbt"` in `registry.generators`. `src/bob_killer/generate/docs/` registers
`"docs"`. Core never has `if target ==` (core SPEC extension points).

Inside the dbt generator:

- **Step handlers.** A `Registry[StepHandler]` keyed by step kind. A test asserts that every name in
  `registry.step_kinds` has a handler. Adding a kind means one handler per generator (core IR rules).
- **Expression renderer.** A `Registry[NodeRenderer]` keyed by expr AST node type. A function call renders as
  `{{ bk_fn('<NAME>', <args>) }}`. An operator renders as `{{ bk_op('<OP>', <a>, <b>) }}`. Each macro emits a
  qualified UDF call (§4.4).
- **SQL-exact set.** A node renders as plain SQL only if its `FunctionSpec.sql_exact` is true (D20). The initial set
  holds only: cell reference, parameter reference, literal. An operator joins the set only after Phase 12 records a
  live differential proof that the SQL operator and the runtime give the same `CellValue` for 10 000 hypothesis
  cases and for every golden cell that uses it. Excel's `+` and `-` (near-zero snapping), `/` (`#DIV/0!`), `*`
  (Excel underflow) are not exact in SQL until proven.
- **Templates.** Jinja2 templates and partials in `generate/dbt/templates/`. A pattern used by two templates becomes
  one partial (core DRY rules).
- **Determinism.** The same IR gives the same bytes. Files sorted, no timestamps, no random ids.

### 4.2 IR node → dbt artifact

| IR node | dbt artifact | Generated file(s) | Rule |
| --- | --- | --- | --- |
| `source` (file, sha256) | project and vars | `dbt/dbt_project.yml` | `name: bk_<sha256[:12]>`; `vars: bk_run_id`, `bk_host_schema`, `bk_source_sha256`; `seeds: +column_types` all `varchar`; `models: +materialized: table`. |
| (host target) | profile | `dbt/profiles.yml` | F14: `type: snowflake`, empty `account` and `user`, role, warehouse, database from the target, `schema: <DEPLOY>__R_<run_id>`. |
| `inputs` (scalar and table) | source and staging model | `dbt/models/sources.yml`, `dbt/models/staging/stg_input__<id>.sql` | Source `bk` = `{{ var('bk_host_schema') }}` with table `WB_INPUT_CELLS` (filtered by `bk_run_id`) and `BRONZE_ROWS` (lineage only, D22). One row per IR row, one wire column per IR column, plus `_row` and `_col` for Excel order. |
| `lookups` | seed and staging model | `dbt/seeds/lkp_<id>.csv`, `dbt/seeds/_seeds.yml`, `dbt/models/staging/stg_lookup__<id>.sql` | Seed columns are text. A number is `float.hex()` text (D21). The staging model builds wire objects. |
| `parameters` (promoted hardcodes) | vars and one model | vars `p_<id>: '<hex>'` in `dbt_project.yml`; `dbt/models/staging/stg_parameters.sql` | Macro `bk_param('<id>')` gives the wire object. `stg_parameters` has one row per parameter, so parameters show in dbt docs and lineage. |
| step `scalar_expr` | rows in a level model | `dbt/models/intermediate/int_<sheet>__l<level>.sql` | One model per sheet and topological level (D26). One row per cell: `sheet`, `row`, `col`, `node_id`, `value` (wire). |
| step `column_expr` | one model | `dbt/models/intermediate/int_<step_id>.sql` | Row-wise over its `over` input. One row per cell of its origin range. |
| step `aggregate` | one model | `dbt/models/intermediate/int_<step_id>.sql` | `ARRAY_AGG(<wire>) WITHIN GROUP (ORDER BY <order from FunctionSpec>)` passed to the UDF (F23). |
| step `lookup` | one model | same | The lookup range reaches the UDF as an ordered array. Never a SQL `JOIN` (Excel match rules differ from SQL equality). |
| step `conditional` | one model | same | `bk_fn('IF', …)` unless every operand is SQL-exact and the condition is a typed boolean. |
| step `vba_procedure` | one model per translated procedure | `dbt/models/intermediate/int_vba__<procedure>.sql` | Only for a translation with status `translated_verified` (§6). Tag `vba`. |
| `outputs` | mart | `dbt/models/marts/mart_<output_id>.sql`, `dbt/models/marts/_marts.yml` | Label and format from the IR. Columns: `sheet`, `row`, `col`, `value`, plus the decoded display columns. |
| every formula cell in the denominator | fact model | `dbt/models/marts/fct_formula_cells.sql` | `UNION ALL` of the per-cell rows of every intermediate model. One row per computed cell. |
| oracle (cached values) | seed | `dbt/seeds/bk_oracle.csv` | One row per denominator cell: `sheet,row,col,wire_json`. Built from `WB_CELLS` cached values at generation time. Only tests may reference it (D22). |
| exact parity | generic test | `dbt/tests/generic/bk_exact_parity.sql`, test on `fct_formula_cells` in `_marts.yml` | `FULL OUTER JOIN` of `bk_oracle` and `fct_formula_cells` on `sheet,row,col`. A row fails when either side is missing or `NOT <host>.BK_VALUES_EQUAL(expected, actual)`. Tag `bk_parity`. `store_failures: true`. |
| IR keys | generic tests | `dbt/tests/generic/bk_unique_cell.sql` | Unique `sheet,row,col` and not null on `value` for every model with cell rows. No dbt package (D28). |
| labels, origins, formulas | descriptions | every `_*.yml`; `dbt/models/overview.md` (`{% docs %}` blocks) | From the IR and the docs generator (§4.6). |
| `unsupported` | nothing generated | docs and report | Listed with origin and reason. |
| macros | macros | `dbt/macros/bk_fn.sql`, `bk_op.sql`, `bk_param.sql`, `bk_wire.sql`, `bk_ident.sql` | Each emits `{{ var('bk_host_schema') }}.BK_*` calls and quoted identifiers. |

### 4.3 Sources, seeds and vars

- **Sources.** The dbt project reads the run's inputs from `WB_INPUT_CELLS`, filtered by `var('bk_run_id')`. It does
  not read `WB_CELLS`. `BRONZE_ROWS` is a declared source for lineage and docs. No model selects from it, because
  bronze is a landing copy, never a parity source (`docs/SPEC.md` §5.3).
- **Seeds.** Lookup tables and the oracle. Every seed column is `varchar` (`+column_types`), so dbt's CSV type
  inference never parses a number. Numbers are hex text (D21).
- **Vars.** One var per promoted parameter, value = hex text. A run with overridden vars is a what-if run. The
  parity test is tagged `bk_parity`, and the report marks a what-if run as unverified (L2).

### 4.4 Python UDFs from `runtime/`

- `src/bob_killer/runtime/` holds all Excel semantics (core DRY rules). Each function registers with
  `@excel_function("<NAME>", spec=FunctionSpec(...))`. `FunctionSpec` is a contract (`contracts/runtime.py`):
  `name`, `arg_kinds` (scalar or range), `range_order`, `volatile`, `sql_exact`.
- Excel operators (`+ - * / ^ & = <> < > <= >=`, unary `-`, `%`) are registered runtime functions named `OP_<NAME>`.
- `src/bob_killer/hosts/snowflake/udfs.py` holds one handler per registered function. Each handler decodes wire
  objects to `CellValue`, calls the runtime function, and encodes the result as a wire object.
- The same module renders `hosts/snowflake/sql/30_udfs.sql` from `registry.functions`: one
  `CREATE OR REPLACE FUNCTION BK_FN_<NAME>(…) RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION = '3.12'
  IMPORTS = ('<build zip>') PACKAGES = (…) HANDLER = 'bob_killer.hosts.snowflake.udfs.<handler>'` per function,
  `IMMUTABLE` unless `volatile`. Range arguments are `ARRAY`, scalars are `VARIANT`. A golden test is a drift guard.
  `uv run python -m bob_killer.hosts.snowflake.udfs` regenerates it.
- Three host UDFs exist in addition: `BK_VALUES_EQUAL(VARIANT, VARIANT) RETURNS BOOLEAN` (calls
  `verify.config.values_equal`), `BK_WIRE_DECODE_NUMBER(VARIANT) RETURNS FLOAT` (display only, never parity), and
  `BK_PING()` (F19).
- Deployment: `snow snowpark build` and `snow snowpark deploy` upload the build zip (F8). Then
  `uv run --project ../.. snow sql -c bob_killer -f hosts/snowflake/sql/30_udfs.sql` creates the UDFs with the zip
  path from the deploy output. The live fixture does the same in the TEST_ schema.

### 4.5 Marts and the oracle seed

- A mart per IR output gives the user the result tables they asked for.
- `fct_formula_cells` holds every computed denominator cell. It is the only relation that the parity test checks.
- `bk_oracle.csv` holds the cached value of every denominator cell. The generator builds it from `WB_CELLS`. A
  generated model never references `bk_oracle` or `WB_CELLS` (D22). Phase 14 proves this from `manifest.json`.

### 4.6 Docs

The `docs` generator writes `docs/<workbook>.md` per run: sheets; inputs, parameters, lookups and outputs with
label, origin and type; each step with its Excel formula, its IR expression, its fingerprint and its precedents;
the unsupported list; the VBA inventory and the macro-writable cells; a link to `report.md`. The text is
deterministic templates. No LLM writes docs in Phases 9–16 (core: LLM output only fills `description`, later, with review).
The dbt generator reuses the same partials for the `description` fields and `overview.md`, so the dbt docs archive
(F16) shows the same text. Files land on `@DBT_SRC/<run_id>/docs/`.

---

## 5. Parity and oracle design

### 5.1 The oracle

- The oracle is the cached values of the goldens (D15, core decision 1). Each cached value covers one input set.
- A golden is a valid oracle only if (a) `docProps/app.xml` names Microsoft Excel as the application, and (b) every
  formula cell has a cached value. Phase 11 enforces both. A golden that fails is reported and leaves the goal set
  only by a user decision (core rule: swap the golden; never lower the gate).
- `tests/oracle/*.json` holds only facts from documents (with `source` and `verified_by`), for example the list of
  volatile functions. It never holds an expected cell value.
- Expected values in tests come from the golden files at test time, read by an independent reader (D30). No test
  holds an expected number as a literal (`no_oracle_literals`).

### 5.2 The denominator

`denominator = formula cells − macro-writable cells − frozen volatile cells`.

- Cells of unsupported features stay in the denominator. They fail until supported (L12).
- A cell written by a translated VBA procedure with status `translated_verified` rejoins the denominator (§6).
- The report lists each excluded cell with its reason.

### 5.3 The comparator

One comparator: `verify/config.py` `values_equal`. Phase 12 changes its argument type from `CellScalar` to the
contract `CellValue`. The rules are: the same kind; a number is the same IEEE-754 double (by `float.hex()`, sign of
zero included); text is equal case-sensitively; a boolean is equal; an error is the same error type; blank, empty
text and zero are three different values. It has no tolerance in any form (`exact_parity` gate). It is used in:

1. the runtime corpus tests (Phase 12), the lift tests (Phase 13) and the generator tests (Phase 14);
2. the UDF `BK_VALUES_EQUAL`, which the dbt parity test calls;
3. the `verify` stage.

### 5.4 Two independent checks per run

1. **In dbt.** `bk_exact_parity` on `fct_formula_cells` against `bk_oracle`. Its failing rows are stored.
2. **In `verify`.** The stage reads `fct_formula_cells` from the run's output schema and the cached values from
   `WB_CELLS` directly (not from the seed). It compares with `values_equal` in Python.

The two must agree on the set of mismatched cells. A disagreement fails the run with the detail
`parity channels disagree`. This catches a broken seed encoding and a broken UDF.

### 5.5 The equivalence report

Contract `EquivalenceReport` (`contracts/report.py`), one row per run in `WB_REPORTS`, and `report.md` on the stage:

- `cells_checked`, `cells_matched`, `denominator`;
- every mismatch: origin cell, expected wire, actual wire, absolute and relative difference for numbers
  (field names avoid the `exact_parity` gate's tolerance words);
- coverage two ways: formula cells (matched / denominator) and IR steps (generated / total);
- unverified items: other input sets (L2), what-if runs, macro-writable cells, frozen volatile cells, VBA
  translations without a cached-value match, functions that no golden exercises (L3), assumption A1 (L4);
- the unsupported list;
- the dbt `OUTPUT_ARCHIVE_URL` values and the dbt test result.

The app shows the report counts and the mismatch table (Phase 16).

### 5.6 What stays unverified

Everything in the "unverified items" list above. These are listed in every report, never approximated, never
allowlisted to make a gate pass. The Excel oracle runner (out of scope) is the only way to verify them.

---

## 6. VBA

- **Inventory (Phase 11).** The `extract` stage reads `vbaProject.bin` with `oletools.olevba` (core SPEC stage 1;
  F20, F21, D23). It writes one `WbVbaModule` per module (name, type, source text, source SHA-256) and one
  `WbVbaProcedure` per procedure. It never executes VBA.
- **Macro-writable cells (Phase 11).** A static scanner in `extract/vba.py` finds write targets: `Range("…")`,
  `Cells(r, c)` with literal arguments, named ranges, and `.Value`/`.Formula` assignments. A resolved target becomes a
  `WbMacroWrite` row with the range. A target it cannot resolve (computed address, `Cells(i, j)` in a loop,
  `ActiveSheet`) marks the whole sheet that the procedure names as macro-writable, or every sheet if no sheet is
  named. That is conservative: it removes cells from the denominator and lists them. It never hides a cell.
- **Classification (Phase 16).** Each procedure gets one class from a registry of detectors (`registry.detectors`):
  `navigation_ui` (`Select`, `Activate`, `Goto`, `MsgBox`, `UserForm`), `external` (`CreateObject`, `Shell`, file I/O,
  COM; core non-goal), `pure_computation` (reads and writes cells, arithmetic, loops only), `unknown`.
- **Translation (Phase 16).** Only `pure_computation` procedures. The `lift` stage asks `AI_COMPLETE` (F28, D27)
  for a translation into IR steps (the IR expression language), never into Python or SQL. The answer must validate
  as strict IR models. It is stored in `WB_VBA_PROCEDURES` with the prompt version and the source SHA-256, and it is
  reused while the source SHA-256 is the same (LLM output is not deterministic). The status starts `needs_review`.
- **Test of a translation.** The runtime evaluates the translated steps on the workbook's inputs. If the result
  equals the cached value of every cell the procedure writes (`values_equal`), the status becomes
  `translated_verified` after a human review row in `WB_REVIEWS`. Its cells rejoin the denominator. If any cell
  differs, the status is `translated_unverified`, and its cells stay out of the denominator and in the report (L7).
- **Goldens.** SGEC macros are navigation only (core decision 6), so SGEC is a full non-VBA test. JEDI needs macros
  to run; its non-VBA cells are in the goal; its macro-written cells are listed.

---

## 7. Decisions

Numbers continue from `docs/SPEC.md` §7 (D1–D16).

| ID | Question | Decision | Rejected |
| --- | --- | --- | --- |
| D17 | Where do compiler stages get their store and files? | A `RunContext` context variable (workbook repository, blob store, target), set by the CLI or the procedure handler (§3.2). One implementation per stage. | Host-specific stage copies (two code paths); widening the `Stage` signature (breaks D3 and every stage). |
| D18 | How does dbt run, given F15? | `execute_run(store, run_id, *, foreign: frozenset[str] = frozenset())` runs pending stages in registry order and stops before the first stage in `foreign`; the run stays `running`. A later call resumes at the first pending stage. The run is final only when no stage is pending. `EXECUTE_RUN` passes `foreign={"dbt_build"}`. The new caller's-rights `RUN_PIPELINE` calls `EXECUTE_RUN`, runs `dbt_build`, then calls `EXECUTE_RUN` again, so `verify` runs inside `EXECUTE_RUN` (D16). D1's two procedures do not change. With `foreign` empty, `execute_run` behaves as in Phase 4. | Making `EXECUTE_RUN` caller's rights (changes D1 and F5's schema rule); the app calling three procedures (orchestration in the 3.11 app). |
| D19 | dbt Python models? | Not used (F17, L10). Excel semantics run in Python UDFs called from SQL models. | dbt Python models (undocumented on Snowflake; a second code path for semantics). |
| D20 | Which steps are plain SQL? | Only nodes whose `FunctionSpec.sql_exact` is true. The initial set is references and literals. An operator joins after a recorded live differential proof (§4.1). Everything else calls a `BK_FN_*`/`BK_OP_*` UDF built from `runtime/`. | SQL `+ - * /` by default (Excel snaps near-zero sums and returns `#DIV/0!`; core decisions 1 and 5); a SQL re-implementation (D14 rejects it). |
| D21 | How do values cross SQL? | One wire format: the JSON dump of the contract `CellValue` with `exclude_none=True`: `{"k":"n","h":"<float.hex()>"}`, `{"k":"s","t":…}`, `{"k":"b","b":…}`, `{"k":"e","e":"#DIV/0!"}`, `{"k":"z"}` (blank). Stored as `VARIANT`; seeds and vars hold the same hex text. No exact value depends on F24. | `FLOAT` columns and binds (F24 is undocumented); decimal text in seeds (dbt and agate parse it as a decimal, F22). |
| D22 | How do we stop a model from copying the oracle? | Models read only `WB_INPUT_CELLS`, seeds `lkp_*` and vars. `bk_oracle` has only test children. Phase 14 asserts both from `manifest.json` for each golden. The `verify` stage reads cached values only from `WB_CELLS`. | Trust the templates (no mechanical check). |
| D23 | oletools in Snowflake (F21: not on Anaconda) | PyPI through the artifact repository (F20). Fallback: the pure-Python oletools wheel and its pure-Python deps in the build zip. If both fail, Phase 10 stops blocked (D16). | A hand-written OLE/VBA reader (large; olevba handles the compression format). |
| D24 | Volatile cells | Frozen at the cached value as IR inputs of kind `frozen_volatile`, listed, out of the denominator. Dependents stay in. | Excluding dependents (hides real formulas); computing `NOW`/`RAND` (cannot match). This is a new rule: see the open questions. |
| D25 | Name review in Snowflake (core decision 3) | Kept as written: generation fails while an output-facing node is `needs_review`. The caller's-rights procedure `REVIEW_NODE(run_id, node_id, new_id, label, reason)` writes `WB_REVIEWS` with `CURRENT_USER()` as reviewer (F29) and the time. Reviews reapply by origin and fingerprint. A review whose origin no longer matches is flagged, never dropped. | API-key reviewer (no FastAPI in the host); letting fallback names pass (changes core decision 3 without the user). |
| D26 | Model granularity | One model per vectorized step; scalar steps grouped into one model per sheet and topological level. All models `materialized: table`, so each UDF runs once per cell. | One model per cell (thousands of models, slow builds, F27); views (re-evaluate UDF chains at every level). |
| D27 | VBA translation engine | `AI_COMPLETE` in Snowflake (F28), output = IR steps only, validated, stored, reviewed, tested against cached values (§6). | LLM-written Python or SQL (unreviewable semantics, a second runtime); translation on the Mac (the goal is Snowflake). |
| D28 | dbt packages | None. Generic tests are generated. No `dbt deps`, so no external access integration on the project. | `dbt_utils` (needs network or a vendored copy). |
| D29 | dbt version | `DBT_VERSION = '1.12.3'` on create and execute (F13); local `dbt parse` uses the same version through `uv tool run` (L-F1), outside the project's lock. | Account default (1.9.4 when unset, deprecated by dbt Labs); dbt-core in the project's `uv.lock` (dependency conflicts with the core's pins). |
| D30 | Independent test oracle reader | `tests/conftest.py` reads each golden's sheet XML with `zipfile` and `xml.etree` (stdlib) to get formulas and cached values. Extraction is tested against it. | Testing openpyxl output against openpyxl (same code on both sides). |
| D31 | Contract versions | All compiler contracts are in `contracts/`. A phase that changes them bumps `SCHEMA_VERSION` once and runs `scripts/export_contracts.py`. `snapshots/vN/ddl.sql` (from `TABLES`) stays identical to v1. Phase 9 adds `workbook_ddl.sql` (from `WORKBOOK_TABLES`) to the snapshot set. `src/bob_killer_sis/schemas.json` is refreshed in the same commit (Phase 7 identity test). | One big contract phase up front (the IR shape is learned in Phases 11–13). |
| D32 | Committed snapshots of generated output | Hash manifests: `tests/snapshot/dbt_<golden>.sha256.json` (path → SHA-256). | Committing generated content (holds golden data; L11). |

---

## 8. Execution plan

Each phase ends with its exit criteria met and `uv run python scripts/gates.py --base <run-base-sha>` green.
Do the phases in order. "Allowed paths" are relative to `labs/bob_killer/`, plus `.context/runs/` and
`.context/evidence/` at the repo root. Phase 9 is Claude Code's own phase (gate-change). Phases 10–16 are CoCo
phases under `docs/SPEC.md` §1.2 and §1.9. The phase prompt (§1.8) names this file in place of `docs/SPEC.md §8`.

Rules for every phase:

- RED: `uv run python scripts/record_run.py --phase red <test paths>`; for live tests
  `uv run python scripts/record_run.py --phase red -- -m live <test paths>`. Commit the test and the run record together.
- GREEN: minimum code. Do not change an existing assertion. Then `uv run pytest -q`, `uv run lint-imports`,
  `uv run mypy src`, and for live phases `uv run pytest -m live tests/live`.
- Before work: `uv run python scripts/fetch_golden.py` (hash-pinned; `golden/` is gitignored and not in the clone).
- Tests (AGENTS.md): one `FakeSession` in `tests/fakes/snowpark.py`, extended; one live fixture in
  `tests/live/conftest.py`, extended; a new case is a new `parametrize` row; shared builders go in the nearest
  `conftest.py`; no new test file when a file for the same unit exists. The golden corpus fixture
  (`golden_workbooks`, parametrized over the goal set) lives in `tests/conftest.py`. A missing golden file fails the
  test with "run scripts/fetch_golden.py". It never skips.
- Expected values come from the goldens through the D30 reader, from `tests/oracle/*.json` (document facts), or from
  an independent computation. Never a literal in an `assert`.
- A contract change follows D31.

### Phase 9: Compiler gate and dependency prep

Done by Claude Code, not CoCo (`TDD-Phase: gate-change`; you review at the PR). Allowed paths: `pyproject.toml`,
`uv.lock`, `scripts/bk_gates/`, `tests/gates/`, `golden.lock`, `AGENTS.md`, `tests/fixtures/dbt_hello/`,
`../../tools/`, `../../.github/workflows/bob-killer.yml`, `../../.gitignore`.

- Dependencies (core): `openpyxl>=3.1`, `jinja2~=3.1`, `pyyaml>=6`, `oletools>=0.60`. Keep the `snowflake` extra.
  `uv lock`. Record L-F2.
- import-linter: `bob_killer.generate` must not import `bob_killer.runtime`.
- `contracts_versioned`: also snapshot `workbook_ddl.sql` from `WORKBOOK_TABLES` when the name exists (D31). Gate test
  first: a tmp repo with a changed workbook model and no bump fails.
- `no_oracle_literals`: add `tests/snapshot` to `SCOPES`.
- `[tool.mutmut] paths_to_mutate`: add `src/bob_killer/verify/`.
- CI: a step `uv run python scripts/fetch_golden.py` before the tests, cached by the `golden.lock` hash.
- `golden.lock`: find the direct URLs for `iwarm`, `sgec_current`, `jedi_wind`; download every goal-set entry;
  `uv run python scripts/fetch_golden.py --accept <id>` for each. You review the URLs and hashes at the PR. An entry
  that has no direct URL stops the phase blocked for your decision.
- `tests/fixtures/dbt_hello/`: a minimal static dbt project (one seed, one model, one test, `profiles.yml` per F14) for
  F11–F18 and L-F1. Record L-F1.
- `AGENTS.md`: add `../../docs/SPEC-compiler-dbt.md` to the reading list after `../../docs/SPEC.md`, as the authority
  on the compiler in Snowflake and the dbt target.
- `../../.gitignore`: `labs/bob_killer/build/`.

Exit: gate tests red then green; `gates.py`, `lint-imports` and the offline suite pass; every goal-set entry in
`golden.lock` is `resolved` with a pinned SHA-256; L-F1 and L-F2 are recorded.

### Phase 10: Platform facts for the compiler

Allowed paths: `tests/live/test_platform.py`, `tests/live/conftest.py`, `tests/fakes/snowpark.py`,
`hosts/snowflake/sql/20_compiler_objects.sql`, `hosts/snowflake/sql/99_teardown.sql`,
`src/bob_killer/hosts/snowflake/session.py`, `.context/evidence/`.

- RED: one parametrized live test per fact F11–F16, F19–F23, F25, F26, F28, F29 in `tests/live/test_platform.py`
  (rows in the existing fact table), plus the F24 boundary test with hypothesis. They fail because `DBT_SRC` and the
  hello objects do not exist.
- GREEN: `20_compiler_objects.sql` creates the stage `DBT_SRC`; the live fixture deploys it and the hello project
  into the TEST_ schema. `99_teardown.sql` drops `<schema>__R_%` schemas too.
- Record F17, F18, F21, F24 results and the F20-or-fallback path in `.context/evidence/snowflake_compiler_<date>.md`.

Exit: every "Stop" fact is confirmed by a live test, or the phase is blocked with the fact named; every other fact is
recorded with its result and its chosen fallback.

### Phase 11: workbook.db in Snowflake, Extract and Graph

Allowed paths: `src/bob_killer/contracts/`, `src/bob_killer/store/`, `src/bob_killer/service/context.py`,
`src/bob_killer/extract/`, `src/bob_killer/graph/`, `src/bob_killer/registry.py`,
`src/bob_killer/hosts/snowflake/{ddl.py,store.py,batch.py,bronze.py,procedure.py,odcs.py}`,
`src/bob_killer_sis/schemas.json`, `src/bob_killer/cli.py`, `hosts/snowflake/sql/10_tables.sql`,
`hosts/snowflake/snowflake.yml`, `hosts/snowflake/contracts/`, `tests/conftest.py`, `tests/fakes/snowpark.py`,
`tests/unit/`, `tests/live/`, `tests/oracle/`, `.context/evidence/`.

- RED/GREEN `contracts/workbook.py` (`CellValue`, `CellKind`, `ExcelError`, the §3.3 models), strict-model tests
  (wrong type, extra key, a `CellValue` whose fields do not match its kind). Nullable `str | None` in both dialects;
  `snapshots/v1/ddl.sql` unchanged. D31 bump. ODCS regenerated.
- RED/GREEN `WorkbookRepository` shared suite (`tests/unit/test_workbook_store.py`, store factory parametrized over
  SQLite and the `FakeSession` store). `BatchWriter` refactor: the bronze tests stay green with no assertion change.
- RED/GREEN `RunContext` (D17) and the stage list `extract`, `graph` registered at `procedure.py` import (the D4
  pattern). Registry order test: `land_bronze`, `extract`, `graph`.
- RED/GREEN `extract` over `golden_workbooks`: for every sheet, the set of formula cells, each formula text and each
  cached value equal the D30 reader's; defined names and tables equal the workbook XML; every VBA module that
  `olefile` lists under `VBA/` is in `WB_VBA_MODULES`; `WbMacroWrite` rows for scanner cases from
  `tests/oracle/vba_write_patterns.json` (`source`: the VBA language reference URL, `verified_by`); a golden not saved by
  Excel, or with a formula cell without a cached value, is rejected (L5). Unsupported detectors (`registry.detectors`):
  pivot, Power Query, data table, chart, external link, each listed in `WB_UNSUPPORTED`.
- RED/GREEN `graph`: parse then render equals the formula text for every golden formula (normalized per a documented
  rule); every edge goes from an earlier to a later node in the topological order (hypothesis property and goldens);
  cycles equal those found by an independent DFS in `tests/conftest.py`; volatile and dynamic functions from
  `tests/oracle/volatile_functions.json` (`source`: Microsoft docs URL) are flagged. Write the function frequency
  table across the goal set to `.context/evidence/function_frequency_<date>.md` (core SPEC roadmap note).
- Live (`tests/live/test_compiler.py`, parametrized over the goal set): `CREATE_RUN` then `EXECUTE_RUN` in the TEST_
  schema; the `WB_CELLS` row count and the multiset of `(sheet,row,col,formula,cached)` equal the local SQLite run on
  the same bytes. Record run time and peak memory per golden and stage in `.context/evidence/compiler_timing_<date>.md`.

Exit: every goal-set golden extracts and graphs in Snowflake, equal to SQLite; all VBA modules and macro-writable
cells are listed; the frequency table and the timings are recorded; coverage ≥ 90%.

### Phase 12: Excel runtime and Python UDFs

Allowed paths: `src/bob_killer/runtime/`, `src/bob_killer/registry.py`, `src/bob_killer/contracts/runtime.py`,
`src/bob_killer/contracts/__init__.py`, `src/bob_killer/contracts/snapshots/`, `src/bob_killer_sis/schemas.json`,
`src/bob_killer/verify/config.py`, `src/bob_killer/hosts/snowflake/udfs.py`, `hosts/snowflake/sql/30_udfs.sql`,
`hosts/snowflake/snowflake.yml`, `tests/conftest.py`, `tests/fakes/snowpark.py`, `tests/unit/`, `tests/live/`,
`tests/oracle/`, `.context/evidence/`.

- RED/GREEN `values_equal` on `CellValue` (§5.3): new rows in `tests/unit/test_verify_config.py`'s parametrize table
  (kinds, sign of zero, blank vs empty text vs zero, error types). The `exact_parity` gate stays green.
- RED/GREEN hex wire round trip: hypothesis over all doubles, `-0.0`, subnormals, NaN rejected.
- RED/GREEN the corpus test (`tests/unit/runtime/test_corpus.py`): for every denominator formula cell of every
  goal-set golden, `runtime.eval_cell(ast, precedents from cached values)` equals the cell's cached value by
  `values_equal`. One test, parametrized over cells. The runtime adds functions in frequency order (Phase 11 table),
  leaves first (core loop). Coercion, 1900 dates with the leap-year bug, 15-digit rounding, near-zero snapping and the
  reduction order go in `runtime/` only.
- A second assertion in the same file: the set of functions used by denominator cells is a subset of
  `registry.functions`. This makes the corpus filter honest: no cell leaves the test because its function is missing.
- RED/GREEN UDF handlers and `30_udfs.sql` from the registry (FakeSession records the DDL; golden drift guard).
- Live: deploy the build zip and the UDFs into the TEST_ schema; load every corpus case as wire objects into a TEST_
  table; one query calls the UDFs; every result equals the Python runtime result by `values_equal`. Record the
  differential proofs for any operator proposed as `sql_exact` (D20).
- Nightly `mutation` on `runtime/` ≥ 80% killed; record it in `.context/evidence/mutation_phase12_<date>.txt`.

Exit: the corpus test passes for 100% of denominator cells of the goal set; the UDFs give the same results in
Snowflake; mutation ≥ 80%. A function that cannot match Excel stops the phase blocked with its root cause (no
allowlist row without your decision).

### Phase 13: Lift, IR and naming

Allowed paths: `src/bob_killer/lift/`, `src/bob_killer/ir/`, `src/bob_killer/contracts/`,
`src/bob_killer_sis/schemas.json`, `src/bob_killer/store/`, `src/bob_killer/registry.py`,
`src/bob_killer/hosts/snowflake/{procedure.py,store.py,ddl.py,odcs.py}`, `hosts/snowflake/sql/`,
`hosts/snowflake/contracts/`, `hosts/snowflake/reviews/`, `tests/conftest.py`, `tests/fakes/snowpark.py`,
`tests/unit/`, `tests/live/`, `tests/oracle/`, `.context/evidence/`.

- RED/GREEN `contracts/ir.py` and `contracts/expr.py` (the core IR example shape: parameters, inputs, lookups, steps
  with the closed kind registry, outputs, unsupported, vba). D31 bump.
- RED/GREEN fingerprinting (R1C1 normalization) and vectorizing: property test that each vectorized step evaluated by
  the runtime equals cell-by-cell evaluation, for every step of every golden (core test layers).
- RED/GREEN parameter promotion and frozen volatile inputs (D24).
- RED/GREEN the full-chain test: the runtime evaluates the IR from inputs, parameters and lookups only (no cached
  value of a formula cell) in topological order; every denominator cell equals its cached value. This is the parity
  goal in Python, before dbt.
- RED/GREEN naming rules in core decision 3's priority order; each `WbName` records the rule; collisions, ties and
  fallbacks are `needs_review`; `generate` raises while an output-facing node is `needs_review` (D25).
- RED/GREEN round trip: `workbook.db` → YAML → `workbook.db` is identical, on SQLite and on the FakeSession store.
- RED/GREEN `REVIEW_NODE` (caller's rights, D25) and reapplication by origin and fingerprint; a stale review is flagged.
- Live: the `lift` stage in the TEST_ schema; the IR YAML on `@DBT_SRC/<run_id>/ir.yaml` has the same SHA-256 as the
  local run on the same bytes and reviews.
- Human step (L9): Claude Code writes the review queue of output-facing nodes per golden to
  `.context/evidence/review_queue_<golden>.md`. You decide each name. Your decisions are committed as
  `hosts/snowflake/reviews/<golden>.yaml` (reviewer, reason) by Claude Code, and the live fixture applies them through
  `REVIEW_NODE`. CoCo never writes a review.

Exit: the full-chain test passes for 100% of denominator cells of the goal set; the IR round-trips; the Snowflake IR
equals the local IR; after your reviews no output-facing node is `needs_review`.

### Phase 14: dbt and docs generators

Allowed paths: `src/bob_killer/generate/`, `src/bob_killer/contracts/`, `src/bob_killer_sis/schemas.json`,
`src/bob_killer/registry.py`, `src/bob_killer/hosts/snowflake/{dbt.py,procedure.py}`, `hosts/snowflake/sql/`,
`tests/conftest.py`, `tests/fakes/snowpark.py`, `tests/unit/`, `tests/snapshot/`, `tests/live/`,
`.context/evidence/`.

- RED/GREEN `Generator` Protocol; `dbt` and `docs` registered; `generate` iterates `registry.generators` (a test with a
  stub generator proves no target branch).
- RED/GREEN every name in `registry.step_kinds` has a dbt handler and a docs handler (parametrized over the names).
- RED/GREEN expression renderer: a node that is not `sql_exact` always renders as a `bk_fn`/`bk_op` call (hypothesis
  over generated expr ASTs; the rendered text has no bare arithmetic operator outside the SQL-exact set).
- RED/GREEN per golden (parametrized): the generated files match `tests/snapshot/dbt_<golden>.sha256.json` (D32;
  regenerated only by an explicit command); `dbt parse` (L-F1, through a `tests/conftest.py` helper) exits 0; from
  `manifest.json`: one model per D26 group, every model's dependencies are `WB_INPUT_CELLS`, `lkp_*` seeds,
  `stg_parameters` or other models, `bk_oracle` has only test children (D22), `bk_exact_parity` is tagged `bk_parity`
  with `store_failures`; every model and column has a description; the docs page lists every IR node. Expected sets
  come from the IR, never from literals.
- RED/GREEN `bk_oracle.csv` round trip: decoding each row gives the `CellValue` in `WB_CELLS`.
- Live (`tests/live/test_compiler.py`, new rows): for each golden, generate locally, put the files on `DBT_SRC` in the
  TEST_ schema, `CREATE DBT PROJECT … DBT_VERSION = '1.12.3'`, `EXECUTE DBT PROJECT … ARGS = 'build'`: `SUCCESS = TRUE`
  and zero rows in the parity failures table. Record model count and build time per golden.

Exit: every goal-set golden's generated project parses, has a stable hash manifest, builds in Snowflake, and passes
its parity test; docs are generated for each.

### Phase 15: The compiler pipeline inside Snowflake

Allowed paths: `src/bob_killer/service/runs.py`, `src/bob_killer/service/context.py`, `src/bob_killer/registry.py`,
`src/bob_killer/verify/`, `src/bob_killer/contracts/`, `src/bob_killer_sis/schemas.json`,
`src/bob_killer/hosts/snowflake/{procedure.py,dbt.py,store.py,ddl.py,odcs.py}`, `hosts/snowflake/snowflake.yml`,
`hosts/snowflake/sql/`, `hosts/snowflake/contracts/`, `tests/conftest.py`, `tests/fakes/snowpark.py`, `tests/unit/`,
`tests/integration/`, `tests/live/`, `.context/evidence/`.

- RED/GREEN D18 `execute_run(…, foreign=…)`: stops before a foreign stage, run stays `running`; a second call resumes;
  final state only when nothing is pending; with `foreign` empty, the Phase 4 shared suite passes unchanged.
- RED/GREEN the `generate` stage writes files through `BlobStore` (FakeSession records `put_stream` with
  `auto_compress=False`, or the F25 fallback); `WbGeneratedFile` rows.
- RED/GREEN the `dbt_build` stage with FakeSession scripted results for `CREATE DBT PROJECT` and the three `EXECUTE`
  calls (§3.4 step 3): a `SUCCESS = FALSE` on build fails the stage with `EXCEPTION`; a parity failure does not.
- RED/GREEN `RUN_PIPELINE` handler (caller's rights): the call order `EXECUTE_RUN`, `dbt_build`, `EXECUTE_RUN`.
- RED/GREEN the `verify` stage and `EquivalenceReport` (§5.4, §5.5): two-channel agreement; a seeded mismatch in a
  FakeSession result appears in both channels and in the report; a channel disagreement fails the run.
- `snowflake.yml`: `RUN_PIPELINE`, `REVIEW_NODE` (caller's rights), packages per F21/D23.
- Live: on `mt_dot_budget` and `sgec_current`, `CREATE_RUN` then `RUN_PIPELINE` in the TEST_ schema: every stage
  `succeeded`; `WB_REPORTS` has `cells_matched == cells_checked == denominator`; teardown drops `<schema>__R_%`.

Exit: one upload runs the whole pipeline inside Snowflake for two goldens; offline and live suites green.

### Phase 16: VBA translation, app report, and the goal on every golden

Allowed paths: `src/bob_killer/extract/vba.py`, `src/bob_killer/lift/`, `src/bob_killer/registry.py`,
`src/bob_killer/contracts/`, `src/bob_killer/verify/`, `src/bob_killer_sis/`, `src/bob_killer/hosts/snowflake/`,
`hosts/snowflake/`, `tests/conftest.py`, `tests/fakes/snowpark.py`, `tests/unit/`, `tests/live/`, `tests/oracle/`,
`.context/evidence/`.

- RED/GREEN procedure classification detectors (§6), cases in `tests/oracle/vba_write_patterns.json` style with a
  documented source.
- RED/GREEN translation path with a FakeSession scripted `AI_COMPLETE` answer: an invalid answer is rejected by the
  strict IR models; a valid one is stored with the prompt version and source SHA-256 and reused; status
  `needs_review`; a translation whose evaluation equals the cached values of its write targets becomes
  `translated_verified` only after a review row; a mismatch stays `translated_unverified` and its cells stay out of the
  denominator. Never execute VBA.
- RED/GREEN app (`src/bob_killer_sis/`, Python 3.11, AppTest with the injected fake session): calls `RUN_PIPELINE`
  with `block=False`; shows the report counts, the mismatch table, the unverified list, and the docs path; a report row
  that fails the JSON Schema shows an error.
- Live (`tests/live/test_compiler.py`, all goal-set rows): from one upload per golden through `CREATE_RUN` and
  `RUN_PIPELINE`, the eight checks of §1.2.
- Evidence: `.context/evidence/goal_<date>.md` with, per golden, the run id, stage table, report counts, the dbt
  project object, the three `OUTPUT_ARCHIVE_URL` values, the VBA inventory and classification counts, and the list of
  unverified items.

Exit (the goal): for every workbook in the goal set, the dbt project runs in Snowflake and parity holds:
`EXECUTE DBT PROJECT` succeeds, the parity test has zero failing rows, the report says
`cells_matched == cells_checked == denominator` with no mismatch and no unsupported denominator cell, the docs exist,
and VBA is inventoried and classified with every macro-writable cell listed. After the merge you deploy to `APP`,
upload each goal-set workbook in Snowsight, and check the same signals.

---

Open questions for you: confirm the goal set and any golden swap if a URL or the Excel-saved check fails; accept
frozen volatile cells (D24); accept "translated VBA rejoins the denominator only on an exact cached-value match plus
your review" (§6); approve Cortex `AI_COMPLETE` and name the model (D27); confirm the dbt 1.12.3 pin (D29) and the
per-run output schema `<DEPLOY>__R_<run_id>` (§3.4).

## Decisions approved by the user (2026-10-16)

The user approved the six defaults of the open questions. They are binding; no phase stops on them.

1. **Goal set.** The five golden workbooks of core SPEC "Golden sample set". If a golden has no direct URL or fails
   the Excel-saved check (cached values present), Phase 9 swaps it for the nearest public Excel-saved workbook of the
   same complexity tier and records the swap and its reason in `golden.lock` and `.context/evidence/`.
2. **D24 frozen volatile cells**: accepted as written.
3. **VBA denominator rule**: a translated procedure rejoins the parity denominator only on an exact cached-value match
   plus a human review row; accepted.
4. **D27 Cortex `AI_COMPLETE`**: approved. Model: the first model in Phase 10's F28 evidence list, in this order of
   preference: a Claude model, then a Llama 3.x 70B+ model, then any other model the region serves. Phase 10 records
   which one; Phase 16 uses it.
5. **D29 dbt pin 1.12.3**: confirmed.
6. **Per-run output schema `<DEPLOY>__R_<run_id>`**: confirmed.

