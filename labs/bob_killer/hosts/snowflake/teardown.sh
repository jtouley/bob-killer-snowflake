#!/usr/bin/env bash
# Drop one deployment schema and its run output schemas (<schema>__R_%), from labs/bob_killer:
#   bash hosts/snowflake/teardown.sh TEST_1A2B3C4D
# Refuses APP: removing production is a separate, deliberate `snow sql -f 99_teardown.sql`.
set -euo pipefail
cd "$(dirname "$0")/../.."
SCHEMA="${1:?usage: teardown.sh <schema>}"
if [ "$SCHEMA" = "APP" ]; then echo "refusing to drop APP" >&2; exit 2; fi
uv run --project ../.. snow sql -c "${BK_CONNECTION:-bob_killer}" \
  -f hosts/snowflake/sql/99_teardown.sql -D "schema=${SCHEMA}"
