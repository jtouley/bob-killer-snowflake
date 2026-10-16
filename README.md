# bob-killer-snowflake

Bob Killer (Excel workbook → Workbook IR → app, docs, equivalence tests) hosted in Snowflake.
Claude Code runs the Cadence pipeline; Snowflake CoCo (Cortex Code CLI) builds each phase on Snowflake credits.

- **Spec (the one handoff):** [`docs/SPEC.md`](docs/SPEC.md)
- **Core:** [`labs/bob_killer/`](labs/bob_killer/) — imported with history from `jtouley/sandbox@40987f0`. Its `SPEC.md`, `CLAUDE.md` and gates apply.
- **Sources:** `docs/sources/bob_killer.txt` and `docs/sources/donor.txt` (gitingest digests of the core and of `jtouley/snowflake-excel-streamlit`).

## Setup

```bash
uv sync                                   # root tooling project: Snowflake CLI
uv run snow --version
curl -qLsS https://ai.snowflake.com/static/cc-scripts/install.sh | sh   # CoCo CLI (not on PyPI)
tools/record-cli-evidence                 # CLI versions + help text → .context/evidence/
```

Then write `~/.snowflake/connections.toml` with a `[bob_killer]` connection (key-pair; see `docs/SPEC.md` §1.4),
have an admin run the bootstrap SQL, and check it:

```bash
tools/smoke-test
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
