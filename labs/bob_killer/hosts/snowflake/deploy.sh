#!/usr/bin/env bash
# Deploy the Bob Killer host and compiler into one schema, from labs/bob_killer:
#   bash hosts/snowflake/deploy.sh            # the connection's schema (APP)
#   bash hosts/snowflake/deploy.sh TEST_1A2B3C4D
# Uses the `bob_killer` connection (override with BK_CONNECTION) and its role, never an admin role.
# Steps: build and deploy the core zip and procedures (F8), create the tables, stages, UDFs and
# RUN_PIPELINE, put the name review files on @DBT_SRC/_reviews/, then create the Streamlit app
# from its files on @APP_SRC (snow 3.29 cannot deploy artifacts from outside the project root).
set -euo pipefail
cd "$(dirname "$0")/../.."
CONNECTION="${BK_CONNECTION:-bob_killer}"
TARGET=()
if [ $# -gt 0 ]; then TARGET=(--schema "$1"); fi
snow() { uv run --project ../.. snow "$@" -c "$CONNECTION" ${TARGET[@]+"${TARGET[@]}"}; }
trap 'rm -f src.zip hosts/snowflake/requirements.snowflake.txt' EXIT
snow snowpark build --project hosts/snowflake
snow snowpark deploy --replace --project hosts/snowflake
for script in 10_tables 20_compiler_objects 30_udfs 40_run_pipeline; do
  snow sql -f "hosts/snowflake/sql/${script}.sql"
done
for review in hosts/snowflake/reviews/*.yaml; do
  snow stage copy "$review" @DBT_SRC/_reviews/ --overwrite --no-auto-compress
done
uv run python -m bob_killer.hosts.snowflake.app --artifacts | while read -r src dest; do
  snow stage copy "$src" @APP_SRC/ --overwrite --no-auto-compress
done
snow sql -f hosts/snowflake/sql/50_app.sql
