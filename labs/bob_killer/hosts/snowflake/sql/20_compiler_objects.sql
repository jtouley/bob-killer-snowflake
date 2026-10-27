-- Compiler objects of one deployment schema (docs/SPEC-compiler-dbt.md §3.4).
-- Run as BOB_KILLER_OWNER in the deployment schema (APP, or a TEST_<uuid8> schema), after 10_tables.sql.
-- DBT_SRC holds each run's files: @DBT_SRC/<run_id>/{workbook.db, ir.yaml, dbt/, docs/}.
CREATE STAGE IF NOT EXISTS DBT_SRC
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  DIRECTORY = (ENABLE = TRUE);
