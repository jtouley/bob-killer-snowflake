# Bob Killer Snowflake host

Everything a workbook needs runs inside one Snowflake schema: the upload app, the procedures,
the Python UDFs built from `runtime/`, the dbt Project, and the equivalence report.

## Deploy (one command)

From `labs/bob_killer/`, with the `bob_killer` connection in `~/.snowflake/connections.toml`
(its role, never an admin role):

```bash
bash hosts/snowflake/deploy.sh                 # into the connection's schema (APP)
bash hosts/snowflake/deploy.sh TEST_1A2B3C4D   # into an existing scratch schema
```

It builds and deploys the core zip and the procedures (`snow snowpark build`/`deploy`), runs
`sql/10_tables.sql`, `20_compiler_objects.sql`, `30_udfs.sql` and `40_run_pipeline.sql`, puts
the name review files of `reviews/` on `@DBT_SRC/_reviews/`, copies the app files to `@APP_SRC`
and creates `BOB_KILLER_APP` with `50_app.sql`.

## Teardown (one command)

```bash
bash hosts/snowflake/teardown.sh TEST_1A2B3C4D
```

It drops the schema and every run output schema `<schema>__R_<run_id>` (and dbt's
`..._DBT_TEST__AUDIT`). It refuses `APP`; removing production is a deliberate
`snow sql -f sql/99_teardown.sql -D schema=APP`.

## What runs where

| Object | Rights | Does |
| --- | --- | --- |
| `BOB_KILLER_APP` (Streamlit, container runtime 3.11) | owner | Upload, preview, start a run, show stages, the report and the docs path |
| `CREATE_RUN(stage_file, filename, sha256)` | owner | Checks the staged upload, creates the run with its stage rows |
| `RUN_PIPELINE(run_id)` | **caller** | `land_bronze → extract → graph → lift → generate → dbt_build → verify` in one call |
| `EXECUTE_RUN(run_id)` | owner | Bronze landing only (Phase 6) |
| `BK_FN_*`, `BK_OP_*` | — | One Python 3.12 UDF per `registry.functions` entry; arguments as one array of wire values |
| `BK_VALUES_EQUAL`, `BK_WIRE_DECODE_NUMBER` | — | The exact comparator; a display-only number |

`RUN_PIPELINE` is caller's rights because `EXECUTE DBT PROJECT` fails in an owner's-rights
procedure (F15, checked in this account). Per run, files land on `@DBT_SRC/<run_id>/`
(`workbook.db`, `ir.yaml`, `dbt/`, `docs/`), the dbt Project is `BK_<run_id8>`, its models land in
`<schema>__R_<RUN_ID>`, and the report row in `WB_REPORTS`.

Regenerate the generated SQL after a change: `uv run python -m bob_killer.hosts.snowflake.ddl`
(10, 20), `.udfs` (30), `.run_pipeline` (40), `.app` (50). Regenerate a golden's name reviews
with `uv run python -m bob_killer.hosts.snowflake.reviews golden/<file> --name <id> --reviewer
<who> --reason "<why>"`.

## Platform limits found while building it

- A query runs at most 128 Python UDF call sites (129 fail with error 100370, not documented);
  the dbt generator splits a level model into parts below that.
- A Python UDF in an untaken `CASE` branch is not evaluated, which the lazy `IF` relies on
  (observed, not documented; the live parity runs prove it per golden).
- Snowflake CLI 3.29 does not deploy Streamlit artifacts from outside the project root, so the
  app is created by SQL from `@APP_SRC`.
