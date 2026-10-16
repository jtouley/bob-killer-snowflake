#!/usr/bin/env bash
# setup-ci-secrets.sh [--connection NAME] [--repo OWNER/REPO] [--dry-run] [--accept-admin-risk]
#
# Set the GitHub Actions secrets and variables that the CI `live` job needs, from one connection in
# ~/.snowflake/connections.toml. Run it once in your own fork or clone; the CI `live` job then runs on
# its own whenever these secrets exist, and skips with a notice when they do not.
#
# Secrets:   SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PRIVATE_KEY
# Variables: SNOWFLAKE_ROLE, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA, BK_EXPECTED_ROLE
#
# Safety:
# - The private key goes from its file to `gh secret set` on stdin. It is never printed or written elsewhere.
# - Key-pair connections only (authenticator = SNOWFLAKE_JWT). Passwords and PATs are refused.
# - Before upload, the script asks Snowflake for the user's roles. If the user holds ACCOUNTADMIN,
#   SECURITYADMIN, SYSADMIN or ORGADMIN, it stops: a key in CI would carry that power. Pass
#   --accept-admin-risk only if you mean it.
# - --dry-run shows what would be set (names and non-secret values only) and changes nothing.
set -euo pipefail

conn="bob_killer"; repo=""; dry=0; accept_admin=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --connection) conn="$2"; shift 2 ;;
    --repo) repo="$2"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    --accept-admin-risk) accept_admin=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
toml="${SNOWFLAKE_CONNECTIONS_FILE:-$HOME/.snowflake/connections.toml}"
command -v gh >/dev/null || { echo "gh CLI not found" >&2; exit 2; }
[[ -f "$toml" ]] || { echo "no connections file: $toml" >&2; exit 2; }
[[ -n "$repo" ]] || repo="$(cd "$root" && gh repo view --json nameWithOwner -q .nameWithOwner)"

# Read one [connection] table. Python 3.11+ has tomllib in the standard library.
read_conn() {
  uv run --quiet --no-project --python 3.12 python - "$toml" "$conn" <<'PY'
import sys, tomllib, shlex
data = tomllib.load(open(sys.argv[1], "rb"))
c = data.get(sys.argv[2])
if c is None:
    sys.exit(f"no [{sys.argv[2]}] connection in {sys.argv[1]}")
for k in ("account", "user", "authenticator", "private_key_file", "role", "warehouse", "database", "schema", "password", "token"):
    print(f"c_{k}={shlex.quote(str(c.get(k, '')))}")
PY
}
parsed="$(read_conn)" || { echo "could not read connection [$conn] from $toml" >&2; exit 3; }
eval "$parsed"

[[ "$(tr "[:lower:]" "[:upper:]" <<<"$c_authenticator")" == "SNOWFLAKE_JWT" ]] || { echo "connection [$conn] is not key-pair (authenticator=SNOWFLAKE_JWT); refusing" >&2; exit 3; }
[[ -z "$c_password$c_token" ]] || { echo "connection [$conn] has a password or token; refusing (key-pair only)" >&2; exit 3; }
key="${c_private_key_file/#\~/$HOME}"
[[ -f "$key" ]] || { echo "private key file not found: $key" >&2; exit 3; }
grep -q "BEGIN PRIVATE KEY" "$key" || { echo "key file is not an unencrypted PKCS#8 PEM: $key" >&2; exit 3; }
for v in account user role warehouse database; do
  val="c_$v"; [[ -n "${!val}" ]] || { echo "connection [$conn] has no $v" >&2; exit 3; }
done
schema="${c_schema:-APP}"

# Admin-role check against Snowflake itself (needs the connection to work).
roles="$(cd "$root" && uv run snow sql -c "$conn" --format json -q "SHOW GRANTS TO USER IDENTIFIER('\"${c_user}\"')" 2>/dev/null \
  | python3 -c 'import json,sys; print(" ".join(r.get("role","") for r in json.load(sys.stdin)))' || true)"
[[ -n "$roles" ]] || { echo "could not read the grants of $c_user with connection [$conn]; check: tools/smoke-test" >&2; exit 4; }
admin="$(tr ' ' '\n' <<<"$roles" | grep -xE 'ACCOUNTADMIN|SECURITYADMIN|SYSADMIN|ORGADMIN' | tr '\n' ' ' || true)"
if [[ -n "$admin" && $accept_admin -eq 0 ]]; then
  echo "REFUSED: $c_user holds admin role(s): $admin" >&2
  echo "A key in GitHub Actions would carry that power. Revoke first, for example:" >&2
  echo "  REVOKE ROLE ACCOUNTADMIN FROM USER $c_user;" >&2
  echo "or re-run with --accept-admin-risk." >&2
  exit 5
fi

echo "repo:       $repo"
echo "connection: [$conn] user=$c_user role=$c_role warehouse=$c_warehouse database=$c_database schema=$schema"
echo "user roles: $roles"
echo "secrets:    SNOWFLAKE_ACCOUNT SNOWFLAKE_USER SNOWFLAKE_PRIVATE_KEY (values not shown)"
echo "variables:  SNOWFLAKE_ROLE=$c_role SNOWFLAKE_WAREHOUSE=$c_warehouse SNOWFLAKE_DATABASE=$c_database SNOWFLAKE_SCHEMA=$schema BK_EXPECTED_ROLE=$c_role"
if [[ $dry -eq 1 ]]; then echo "dry run: nothing changed"; exit 0; fi

printf '%s' "$c_account" | gh secret set SNOWFLAKE_ACCOUNT --repo "$repo"
printf '%s' "$c_user"    | gh secret set SNOWFLAKE_USER --repo "$repo"
gh secret set SNOWFLAKE_PRIVATE_KEY --repo "$repo" < "$key"
gh variable set SNOWFLAKE_ROLE      --repo "$repo" --body "$c_role"
gh variable set SNOWFLAKE_WAREHOUSE --repo "$repo" --body "$c_warehouse"
gh variable set SNOWFLAKE_DATABASE  --repo "$repo" --body "$c_database"
gh variable set SNOWFLAKE_SCHEMA    --repo "$repo" --body "$schema"
gh variable set BK_EXPECTED_ROLE    --repo "$repo" --body "$c_role"
echo "done. The CI live job now runs on pushes and PRs to $repo. Remove with: gh secret delete <name> --repo $repo"
