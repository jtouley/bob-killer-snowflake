# bob-killer-snowflake

> Every company has a Bob. Bob built the spreadsheet everything runs on.
> Bob Killer makes sure the business survives Bob's holiday.

*A Snowflake hackathon entry.* No Bobs are harmed. Only the key-person risk is.

## The problem

The pricing model, the budget, the emissions report. Somewhere there's a 40-tab `.xlsm` with VLOOKUPs into
hidden sheets and a macro nobody dares touch, and one person who understands it. When Bob is out, quarter-end
waits. When Bob leaves, the logic leaves too. Auditors file this under "end-user computing risk". It turns up in
the news as the London Whale VaR spreadsheet, the Reinhart–Rogoff error, and the UK's lost COVID test results.

The usual fixes don't hold up. A manual rewrite drifts from the original, and nobody can prove it matches.
Moving the workbook into a SaaS tool swaps Bob for a vendor.

## What Bob Killer does

Upload the workbook in Snowsight. Inside Snowflake, Bob Killer pulls it apart (cells, formulas, cached values,
names, VBA), builds the dependency graph, lifts it into a typed Workbook IR, and generates:

1. **A dbt project that runs in Snowflake.** Bob's logic as versioned, governed models with lineage.
   Excel's semantics come from one shared runtime deployed as Python UDFs. They are never re-guessed in SQL.
2. **Docs.** What Bob knew, written from the formulas themselves.
3. **Exact-parity tests.** Every formula output must equal Excel's own cached value bit for bit, with no tolerances.
   Finance won't trust "close enough", so neither do we. Anti-cheat gates in CI reject any commit that loosens a
   comparison, hard-codes an expected value or skips a test.

Status: the upload → bronze landing path runs live in Snowflake. A first golden workbook (Montana DOT budget
worksheet) has gone workbook → dbt project → `EXECUTE DBT PROJECT` with 24/30 formula cells exact, and the misses
trace to functions that have since landed. The rest of the wiring is in
[`docs/review/MVP_ONESHOT_PROMPT.md`](docs/review/MVP_ONESHOT_PROMPT.md); the review is in
[`docs/review/REVIEW_2026-10-26.md`](docs/review/REVIEW_2026-10-26.md).

## How it's built

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

Start order: `docs/SPEC.md` §1.3 → §1.4 → §1.5 → §1.6 (gate-change PR) → §1.7 (probe) → §1.10 (`/cadence`).
