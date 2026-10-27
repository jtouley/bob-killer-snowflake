# MVP step 8 blocked on sgec_current: long dbt builds abort inside a procedure (2026-10-27)

Account: <ACCOUNT>, role BOB_KILLER_OWNER, warehouse BOB_KILLER_WH, dbt 1.12.3.

## What works

- mt_dot_budget, one `CALL RUN_PIPELINE` (caller's rights): every stage succeeded, dbt `build`
  SUCCESS, `bk_exact_parity` 0 failures, report 31 / 31 / 31, channels agree. Proven in TEST_
  schemas (tests/live/test_pipeline.py[mt_dot_budget] passed, run record
  .context/runs/20261027T212834Z-1af8b7d2) and in APP (.context/evidence/mvp_20261027.md).
- sgec_current: every one of 2796 formula cells lifts, and every IR step, evaluated from cached
  precedents, equals Excel's cached value exactly (tests/golden, offline). In Snowflake the
  pipeline runs land_bronze through generate inside RUN_PIPELINE (539 files, 4790 input cells).

## What fails

| Attempt | What ran | Result |
| --- | --- | --- |
| tests/live/test_pipeline.py[sgec_current] | CALL RUN_PIPELINE | 000603 "Processing aborted due to error 300005:4227727749; incident 6831212" after 594 s; its EXECUTE DBT PROJECT build child had run 343 s and was cancelled "upon parent jobs termination" |
| reproduction, fresh TEST_ schema (deploy.sh) | CALL RUN_PIPELINE | same error, incident 6486414, after 561 s; dbt child cancelled after 318 s |
| minimal caller's-rights procedure, `collect_nowait()` + poll every 15 s | EXECUTE DBT PROJECT of the same project | same 000603 internal error after 376 s |
| control: caller's-rights procedure, `time.sleep(720)` | — | completed, 725 s |
| control: caller's-rights procedure, `SELECT SYSTEM$WAIT(720)` | — | completed, 725 s |
| the same sgec_current build from a client session (not a procedure) | EXECUTE DBT PROJECT | ran 80+ min without this error; cancelled by me, unfinished |

So a procedure can run 12 minutes, and a short dbt build (mt_dot_budget, about 2 min) runs
inside one, but a dbt build longer than about 5 minutes inside a procedure aborts with an
internal incident, blocking or polling. F15 requires a caller's-rights procedure for
EXECUTE DBT PROJECT, so neither the single RUN_PIPELINE call nor the D18 split (also a
procedure) can host sgec_current's build as it is generated today.

## Why the sgec_current build is long

Each Python UDF call site in a query costs about 1.7 s to start (TEST_ schema: a pure-Python UDF
at 1, 16 and 64 call sites took 3.6, 23 and 121 s; one call site over 3000 rows took 5 s). A query
may hold at most 128 call sites (129 fail with 100370). The generator renders every IR call and
operator as its own UDF call site (D20), about 14 000 for sgec_current, so its build takes hours.

## Options (your decision)

1. Generate one UDF call site per model: a BK_EVAL UDF evaluates each cell's IR expression with
   the runtime (as tests/golden IrEvaluator does), fed by joins of the cells it reads. Measured
   cost suggests minutes for sgec_current. It changes D20 and replaces the per-node rendering that
   tests/unit/test_generate.py pins (frozen assertions), so it needs your sign-off.
2. Run dbt outside a procedure (a Snowflake task, or the app session) and keep RUN_PIPELINE for the
   other stages: changes D18 and the one-call MVP shape.
3. Open a Snowflake support case with the incident numbers above.
