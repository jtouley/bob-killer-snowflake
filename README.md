# bob-killer-snowflake

Bob Killer (Excel workbook → Workbook IR → app, docs, equivalence tests) hosted in Snowflake.
Claude Code runs the Cadence pipeline; Snowflake CoCo (Cortex Code CLI) builds each phase on Snowflake credits.

- **Spec (the one handoff):** [`docs/SPEC.md`](docs/SPEC.md)
- **Core:** [`labs/bob_killer/`](labs/bob_killer/) — imported with history from `jtouley/sandbox@40987f0`. Its `SPEC.md`, `CLAUDE.md` and gates apply.
- **Sources:** `docs/sources/bob_killer.txt` and `docs/sources/donor.txt` (gitingest digests of the core and of `jtouley/snowflake-excel-streamlit`).

## Status (2026-10-16)

| Area | State |
| --- | --- |
| Platform Phases 1–3 (gates, CI, platform proof, contracts, DDL, ODCS v3.2.0) | Done, merged |
| Phase 4 core (RunRepository, registry isolation, run claim) | Merged; Snowflake store pending |
| Compiler: Extract, Graph, Excel runtime, Workbook IR, dbt + docs generators | Merged (contracts v5) |
| Golden tests, 5 government workbooks (`tests/golden/`) | 8,681 / 8,681 formulas parse; 207 / 207 cells the runtime evaluates alone match Excel's cached values exactly. An evidence probe that adds its own `+ - * /` and cross-sheet refs: 921 / 921 exact. The runtime has no operator layer yet; operators, SUMIF, ISNA, ISBLANK, SUMPRODUCT, VLOOKUP are the next gaps. |
| Live Snowflake suite | 18 / 18 pass on merged code |
| Not done | Snowflake store + bronze, procedures + app, lift, runtime UDFs in Snowflake, dbt deploy + execute, parity in Snowflake (the goal: `docs/SPEC-compiler-dbt.md` Phase 16) |

## Recreate it in your own Snowflake account

You need: macOS or Linux, `git`, [`uv`](https://docs.astral.sh/uv/), `gh` (optional, for CI secrets), and a
Snowflake account where you can use an admin role once.

**1. Clone and install.**

```bash
git clone https://github.com/jtouley/bob-killer-snowflake.git && cd bob-killer-snowflake
git checkout snowflake-host
uv sync                                    # root tooling project: Snowflake CLI (uv run snow ...)
cd labs/bob_killer && uv sync && cd ../..  # the core and host packages (Python 3.12)
curl -qLsS https://ai.snowflake.com/static/cc-scripts/install.sh | sh   # CoCo CLI, only to use the CoCo bridge
```

**2. Make a key pair for the service user** (the private key never leaves your machine):

```bash
mkdir -p ~/.snowflake/keys && cd ~/.snowflake/keys
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out bob_killer_rsa.p8 -nocrypt
openssl rsa -in bob_killer_rsa.p8 -pubout -out bob_killer_rsa.pub
chmod 600 bob_killer_rsa.p8
grep -v -- '-----' bob_killer_rsa.pub | tr -d '\n'; echo   # the public key body for step 3
cd -
```

**3. Bootstrap Snowflake once, as an admin.** Open
`labs/bob_killer/hosts/snowflake/sql/00_admin_bootstrap.sql`, replace `<PUBLIC_KEY_BODY>` with your public key body,
run `SET MY_USER = '<your Snowflake user>';` first, read the file, and run it in a Snowsight worksheet as ACCOUNTADMIN. It creates the role
`BOB_KILLER_OWNER`, the service user `BOB_KILLER_SVC` (key-pair only), the warehouse, the database
`BOB_KILLER` with schema `APP`, the compute pool and the PyPI network integration. The build never uses an admin
role after this.

**4. Write the connection** (mode 600, never in the repo):

```toml
# ~/.snowflake/connections.toml
[bob_killer]
account          = "<your org>-<your account>"   # SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME();
user             = "BOB_KILLER_SVC"
authenticator    = "SNOWFLAKE_JWT"
private_key_file = "~/.snowflake/keys/bob_killer_rsa.p8"
role             = "BOB_KILLER_OWNER"
warehouse        = "BOB_KILLER_WH"
database         = "BOB_KILLER"
schema           = "APP"
```

**5. Check it works.**

```bash
tools/smoke-test                                   # snow + CoCo connect as BOB_KILLER_SVC / BOB_KILLER_OWNER
cd labs/bob_killer
uv run python scripts/fetch_golden.py              # the 5 pinned government workbooks into golden/ (gitignored)
uv run pytest -q                                   # offline suite (live tests are deselected)
uv run python scripts/gates.py --base 77fcc0781036da5accec50e0389b8c7e75653485   # the 10 anti-cheat gates
export BK_EXPECTED_ROLE=BOB_KILLER_OWNER
uv run pytest -m live tests/live                   # live Snowflake suite
```

**6. Optional: live tests in CI.** `tools/setup-ci-secrets.sh --dry-run`, then without `--dry-run`. It refuses a
Snowflake user that holds an admin role.

Never commit `connections.toml`, the `.p8` key, or your account identifier. Evidence files redact the account to
`<ACCOUNT>`.

## CLI evidence

```bash
tools/record-cli-evidence                 # CLI versions + help text → .context/evidence/
```

## The CoCo bridge

| Tool | Does |
| --- | --- |
| `tools/coco-flags.sh` | Connection, clone path, timeout and flags of every CoCo call (verified against `cortex exec --help`, v1.2.14). Human review to change. |
| `tools/coco-clone <run-branch>` | Makes CoCo's isolated clone `../bob-killer-snowflake-coco` on `coco/<run-branch>`, with no remotes. `--sync` fast-forwards it. |
| `tools/coco-phase <prompt> <log>` | One CoCo build call in the clone: lock, version check, watchdog. The log always ends with `COCO_EXIT <code>`. |
| `tools/coco-guard` | `snapshot` / `verify` the state CoCo must not touch; `clone-check` the clone. |
| `tools/coco-probe` | Proves what the flags allow and block, in a throwaway repo. |
| `tools/record-cli-evidence` | Records CLI versions and help output. Re-run after each CoCo update. |
| `tools/smoke-test` | Checks the `bob_killer` connection with `snow` and with CoCo's real flags. |
| `tools/setup-ci-secrets.sh` | Sets the CI `live` job's GitHub secrets and variables from a key-pair connection (`--dry-run` first). Refuses a user with an admin role unless `--accept-admin-risk`. Optional: without the secrets, CI runs the offline suite and the live job skips with a notice. |

Start order: `docs/SPEC.md` §1.3 → §1.4 → §1.5 → §1.6 (gate-change PR) → §1.7 (probe) → §1.10 (`/cadence`).
