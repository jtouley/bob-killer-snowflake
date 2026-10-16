# Bob Killer on Snowflake — Build Spec (Claude Code + Cadence orchestrates, CoCo builds)

Oct 16, 2026 · Jason Touleyrou · Status: r5 (P3 r1 + r2 applied; CLI facts verified on v1.2.14; see §13)

This document is the one handoff for building the Bob Killer Snowflake host. It joins two repositories
into one service that runs in Snowflake. It holds the operating model, the CLI setup, the scope, the
decisions, the phased plan, the agent instructions, and the review record.

Two agents share the work:

- **Claude Code** runs the Cadence pipeline. It writes and reviews the plan, delegates each build phase,
  checks every result, closes each phase, and runs the PR reviews.
- **CoCo** (Snowflake Cortex Code CLI) builds. It writes the code under TDD, runs SQL, deploys, and runs
  the live tests. Its usage bills to your Snowflake account.

| Source | Ref | Role |
| --- | --- | --- |
| `~/Projects/bob-killer-snowflake` (new repo) | `main` | **The code home.** The core at `labs/bob_killer/` (imported with its history), the tooling in `tools/`, this spec in `docs/`, and the host code that this spec adds. |
| `github.com/jtouley/sandbox`, path `labs/bob_killer/` | branch `ccr-0d94cccb-c40ohp` @ `40987f0` | Where the core came from: core SPEC Phase 0 skeleton of Bob Killer (Excel → IR → app + docs + tests compiler). Its `SPEC.md`, `CLAUDE.md` and gates stay in force. Its old Cadence artifacts are in `docs/history/sandbox-gh-5/`, outside `.context/`. |
| `github.com/jtouley/snowflake-excel-streamlit` | `main` @ `257f9e8` | The donor: a Streamlit upload UI and a bronze ingest to Snowflake. CoCo ports the useful behavior. CoCo does not copy the code. Digest: `docs/sources/donor.txt`. |

**Phase names.** "Phase N" in this file is a **host** phase (§8). A core phase is always written "core SPEC Phase N".

---

## 1. Operating model and setup

### 1.1 Who does what

| Step / Cadence block | Runs in | Who pays | Notes |
| --- | --- | --- | --- |
| Step 0a–0e (before Cadence) | You + Claude Code | Anthropic | CLIs, connection, bridge, gate-change PR, probe. A human approves the PR. §1.3–1.7. |
| A1–A5 | Claude Code | Anthropic | The vibe-test target is this file. |
| P1–P9 | Claude Code | Anthropic | The P1 plan copies §8 and keeps the `### Phase N:` headers (the phase ledger reads the P1 plan, not this file). P3 and P6 run as separate Claude Code agents. |
| **E1, one call per phase** | **CoCo through `tools/coco-phase`** | **Snowflake** | CoCo builds and commits the phase in its isolated clone. |
| E1 checks and phase close | Claude Code | Anthropic | §1.9. Claude Code makes the `phase N` close commit only after every check passes. |
| E2–E4 | Claude Code | Anthropic | |
| R1–R7 | Claude Code reviews; CoCo fixes | Both | Each must-fix finding goes to CoCo as a fix prompt. Claude Code re-reviews. |

Most of the token spend is in E1 and the fix loops. That spend goes to Snowflake.

### 1.2 The trust boundary

Cadence edit hooks guard Claude Code's Write and Edit calls. They do not see what CoCo does inside a
`cortex exec` subprocess, and the Bash hook sees only the `tools/coco-phase …` command line. CoCo has a
shell. So the controls for E1 are these:

1. **Clone isolation.** CoCo works in a separate **clone** (`../bob-killer-snowflake-coco`, made by
   `tools/coco-clone`) on branch `coco/<run-branch>`, with **no remotes**. A clone has its own `.git`
   (hooks, config, refs), so nothing CoCo does to git touches the run repo. Claude Code fetches CoCo's
   commits from the clone with `git fetch`, which runs no hooks in the run repo.
2. **State guard.** `tools/coco-guard snapshot` hashes the protected state before each call: all of the run
   repo's `.context/` (except `.context/coco/`), `.claude/`, `tools/`, the run repo's git hooks, git config
   and every ref, its `git status`, the Cadence skill tree (`~/.claude/skills/cadence`),
   `~/.claude/settings.json`, and `git ls-remote origin`. It prints one digest; Claude Code keeps that digest
   in its transcript. `tools/coco-guard verify` after the call lists every change. Any change outside the
   Step 0e noise list is a Cadence hard stop `security`.
3. **Clone check.** `tools/coco-guard clone-check`: the clone is clean, has no remotes, has no active git
   hooks and no `core.hooksPath`.
4. **History gates.** The bob_killer gates read git history (`tdd_order`, `assertions_frozen`,
   `no_oracle_literals`, `no_silent_skips`, `exact_parity`, `contracts_versioned`). Claude Code runs them on
   the fetched commits before it merges. They catch a cheating commit no matter who made it.
5. **Path allowlist.** Each phase in §8 lists the paths it may touch. A commit outside the list fails the phase.
6. **No gate changes during the run.** All gate, CI, tooling, dependency and import-linter changes happen in
   Step 0d under human review. A CoCo commit with `TDD-Phase: gate-change`, or one that touches `tools/`,
   `scripts/bk_gates/`, `scripts/gates.py`, `scripts/record_run.py`, `.github/`, `pyproject.toml` or
   `uv.lock`, fails the phase as a Cadence hard stop `security`.
7. **Tool blocklist.** `tools/coco-flags.sh` blocks git push, remote, reset, rebase, amend, worktree,
   checkout, switch, branch, tag, update-ref, config, stash, clean, filter-branch, gc and recursive `rm`. This
   is a speed bump only: a blocklist cannot list every command, and file writes into `.git/` cannot be
   blocked. Controls 1–3 are the guard.
8. **CI.** Step 0d makes the workflow run on pushes to every branch and on PRs. Claude Code pushes the run
   branch after each phase close (Cadence E4 owns the PR).

### 1.3 Step 0a — the CLIs and their evidence (done 2026-10-16)

- **Snowflake CLI 3.29.0**: a dev dependency of the root uv project. `uv sync`, then `uv run snow --version`.
- **CoCo CLI v1.2.14**: not on PyPI. Installed with Snowflake's script
  (`curl -qLsS https://ai.snowflake.com/static/cc-scripts/install.sh | sh`) into `~/.local/bin/cortex`.
- `tools/record-cli-evidence` wrote `.context/evidence/coco_cli_20261016.txt`.

**Verified facts (v1.2.14).** `cortex exec` accepts `--file`, `-c`, `-w/--workdir`, `--format text|json`,
`--allowed`, `--blocked`, `--bypass`, `--max-turns`, `--private`, `--no-mcp`, `-o` and `--cloud`. Three
docs-era claims are false for this version: the flag is `--format json`, not `--output-format stream-json`;
the allowlist flags are `--allowed` / `--blocked`, not `--allowed-tools`; `cortex mcp serve` does not exist.
CoCo loads Claude Code's MCP servers from `~/.claude.json` unless `--no-mcp` is set. CoCo updates itself on
launch, so `tools/coco-phase` refuses to run when `cortex --version` is not in the newest evidence file;
re-run `tools/record-cli-evidence`, review the help diff, then retry.

**Unproven until Step 0e:** whether `--blocked` without `--bypass` lets every other tool run (exec rejects
interactive prompts). `tools/coco-probe` settles it.

### 1.4 Step 0b — service user and connection (no secret in any repo file)

`cortex exec` runs with no person at the keyboard, so it cannot type a password or finish a browser SSO
login. The build uses its own Snowflake **service user**, `BOB_KILLER_SVC` (`TYPE = SERVICE`), with
**key-pair** auth:

- The **private key** stays on your Mac (`~/.snowflake/keys/bob_killer_rsa.p8`, mode 600). It works like a
  password. Never paste it anywhere.
- The **public key** goes into Snowflake: `CREATE USER BOB_KILLER_SVC … RSA_PUBLIC_KEY = '<key body>'`.
  It is not secret; it only lets Snowflake check the private key.

```bash
mkdir -p ~/.snowflake/keys && cd ~/.snowflake/keys
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out bob_killer_rsa.p8 -nocrypt
openssl rsa -in bob_killer_rsa.p8 -pubout -out bob_killer_rsa.pub
chmod 600 bob_killer_rsa.p8
grep -v -- '-----' bob_killer_rsa.pub | tr -d '\n'; echo     # the key body for RSA_PUBLIC_KEY
```

```toml
# ~/.snowflake/connections.toml  (mode 600; never in a repo)
[bob_killer]
account          = "<ACCOUNT>"
user             = "BOB_KILLER_SVC"
authenticator    = "SNOWFLAKE_JWT"
private_key_file = "~/.snowflake/keys/bob_killer_rsa.p8"
role             = "BOB_KILLER_OWNER"
warehouse        = "BOB_KILLER_WH"
database         = "BOB_KILLER"
```

**Bootstrap order.** `labs/bob_killer/hosts/snowflake/sql/00_admin_bootstrap.sql` creates the role, the
service user (with the public key), the warehouse, the compute pool, the database, the PyPI network rule and
integration, and the grants. It needs an admin role, so it cannot run as the user it creates. Step 0b is:
Claude Code (or CoCo, under your own admin connection, as a one-time interactive step) drafts the file; you
read it; you run it as admin. The build connection `bob_killer` never has an admin role.

Then `tools/smoke-test` checks the connection with `snow` and with CoCo's real flags.

### 1.5 Step 0c — the bridge

The bridge is the Claude Code Bash tool calling `cortex exec`. Snowflake documents `exec` for automation:
plan mode off, interactive prompts rejected. There is no MCP route (`cortex mcp serve` does not exist;
`cortex acp` is for editors). `cortex exec --cloud` (a Snowflake-side sandbox) is not used, because the
gates need the local clone and uv toolchain.

| Tool | Does |
| --- | --- |
| `tools/coco-flags.sh` | Connection name, clone path, timeout (6600 s), and the flags of every call: `--format json`, `--no-mcp`, `--private`, `--max-turns 200`, `--blocked …`. No `--bypass` unless Step 0e proves it is needed. |
| `tools/coco-clone <run-branch>` | Makes the isolated clone on `coco/<run-branch>` and removes its remote. `--sync <run-branch>` fast-forwards it after a phase close. |
| `tools/coco-phase <prompt> <log>` | One call: lock (one call at a time), version check, `cortex exec -w <clone>/labs/bob_killer`, watchdog. The log always ends with `COCO_EXIT <code>`, also on timeout (143) or kill. Final message in `<log>.last.md`. |
| `tools/coco-guard snapshot / verify / clone-check` | §1.2 controls 2 and 3. |
| `tools/coco-probe` | Step 0e permission probe in a throwaway repo with a local bare remote. |
| `tools/record-cli-evidence`, `tools/smoke-test` | §1.3, §1.4. |

These behaviors were tested offline with a stub `cortex` on 2026-10-16: normal exit, timeout → `COCO_EXIT 143`,
second call blocked by the lock, version mismatch refused, a changed `.context/` file caught by `verify`, a
planted hook in the clone caught by `clone-check`.

**Waiting.** Claude Code starts `tools/coco-phase` with `run_in_background: true` and `timeout: 7200000`, then
waits with the `Monitor` tool until the log contains `COCO_EXIT`. The wrapper's own timeout (6600 s) ends
first, so the log always gets `COCO_EXIT`. Claude Code does not end the turn while E1 is open, because the
Cadence stop guard blocks that.

### 1.6 Step 0d — the gate-change PR (human-reviewed, before Cadence)

Cadence does not stop for human approval between A1 and R7. So every gate, CI, dependency and config change
that the host needs lands first, in one PR into `main`, with `TDD-Phase: gate-change` commits. It needs a
GitHub remote (open question §12).

1. **import-linter** (`labs/bob_killer/pyproject.toml`): `root_packages = ["bob_killer", "bob_killer_sis"]`;
   add `bob_killer.hosts` to the top layer (`bob_killer.api | bob_killer.cli | bob_killer.hosts`); forbidden
   contracts: `bob_killer.hosts.snowflake` must not import `bob_killer.api`, `fastapi`, `uvicorn`;
   `bob_killer_sis` must not import `bob_killer`. Add stub packages `src/bob_killer/hosts/__init__.py`,
   `src/bob_killer/hosts/snowflake/__init__.py` and `src/bob_killer_sis/__init__.py` (docstring only) so the
   contracts resolve; `lint-imports` must pass on `main`.
2. **pytest**: register marker `live`; add `-m "not live"` to `addopts`.
3. **`contracts_versioned` discovery**: `default_models()` imports every module of the `bob_killer.contracts`
   package with `pkgutil.iter_modules`, not a fixed list. It works before `contracts/bronze.py` exists and
   picks it up after.
4. **`no_oracle_literals` scope**: `SCOPES = ("tests/unit", "tests/integration", "tests/live")`.
5. **Dependencies**: optional extra `snowflake = ["snowflake-snowpark-python", "openpyxl"]`; dev group adds
   `snowflake-snowpark-python`, `openpyxl`, `types-openpyxl`, `streamlit>=1.50`, `jsonschema`,
   `types-jsonschema`. `uv lock`. No phase may change dependencies; a phase that needs one stops blocked.
6. **3.11 check for the app**: `src/bob_killer_sis/ruff.toml` with `target-version = "py311"`; CI step
   `uv run --no-project --python 3.11 python -m compileall -q src/bob_killer_sis` (works: uv fetches 3.11).
7. **CI** (`.github/workflows/bob-killer.yml`): `push` on all branches; a `live` job (manual dispatch, PRs,
   pushes) that runs `uv run pytest -m live tests/live` with a key-pair secret, required before merge. Step 0d
   adds one live test, `tests/live/test_connection.py`: `CURRENT_ROLE()` equals the role named in the
   `BK_EXPECTED_ROLE` environment variable (not a literal), so the job has a real test from day one.
8. **Gate tests** in `tests/gates/` (tmp-repo pattern of `test_evasions.py`): a red commit under
   `tests/unit/hosts/` passes `tdd_order`; a green commit that edits an assertion in `tests/live/` fails
   `assertions_frozen`; a literal expected value in `tests/live/` fails `no_oracle_literals`; an
   `import bob_killer` in `src/bob_killer_sis/` fails `boundaries`.

Exit: the PR is green and you approved and merged it.

### 1.7 Step 0e — the probe and the dry run

1. `tools/coco-probe`. It asks CoCo, with the real flags, to write a file, commit, push to a local bare
   remote, write a git hook, and set `core.hooksPath`. Pass = the file was written and committed, and the push
   did not reach the remote. If the write or commit fails, the `--blocked`-only mode does not let tools run:
   change `tools/coco-flags.sh` to `--bypass` plus the same `--blocked` list (human review), and probe again.
   The probe output (`.context/evidence/coco_probe_*.txt`) records what the blocklist does not stop.
2. Dry run of the guard: `tools/coco-guard snapshot`, one `Monitor` wait of 60 s with no CoCo call, then
   `tools/coco-guard verify`. Any entry that changed was written by Claude Code's own hooks: add its path
   pattern to `NOISE_RE` in `tools/coco-guard` (human review). Keep the list short.

### 1.8 The phase prompt (Claude Code writes one per call)

`.context/coco/prompts/phase-<n>.md` in the run repo, passed by absolute path:

```markdown
Read AGENTS.md and the documents it names.
Do Phase <n> of ../../docs/SPEC.md §8. Touch only the paths that the phase allows.
Follow the TDD loop. Do not write "phase" followed by a number in any commit subject.
Base sha for gates: <run-base-sha>.
Stop when the phase exit criteria pass, or when a hard rule stops you.
End with this block and nothing after it:

COCO_RESULT
phase: <n>
status: done | blocked
commits: <sha> <subject> (one per line)
gates: <last line of `uv run python scripts/gates.py --base <run-base-sha>`>
evidence: <paths, relative to the repo root>
blocked_reason: <text or none>
```

A fix prompt has the same shape and names the finding ids and files.

### 1.9 Claude Code checks around each CoCo call, then the phase close

Before each call:

1. `python3 "$SKILL_ROOT/scripts/entry_invariant.py" --phase execution --check`.
2. `tools/coco-clone --sync <run-branch>` (the clone starts from the newest close commit).
3. `D=$(tools/coco-guard snapshot .context/coco/manifest-<n>.txt)`; keep `D` in the transcript.
4. Start `tools/coco-phase` in the background (§1.5) and wait with `Monitor` for `COCO_EXIT`.

After each call:

1. The log has `COCO_EXIT 0` and a `COCO_RESULT` block. If not: record it in the Cadence findings ledger and
   retry once. A second failure counts as a failed fix call.
2. `tools/coco-guard verify .context/coco/manifest-<n>.txt "$D"` and `tools/coco-guard clone-check` pass.
3. `git fetch "$COCO_CLONE" coco/<run-branch>:refs/coco/<run-branch>`. Every commit in
   `<run-branch>..refs/coco/<run-branch>` has a `TDD-Phase` trailer (red, green, refactor or scaffold), a
   subject prefix `p<n>/<tdd-phase>:` with no "phase <number>" text, and touches only allowed paths (§1.2
   controls 5 and 6).
4. In the clone, from `labs/bob_killer/`: `uv run python scripts/gates.py --base <run-base-sha>`,
   `uv run pytest -q`, and for phases with live work `uv run pytest -m live tests/live`.
5. All pass: `git merge --ff-only refs/coco/<run-branch>` into the run branch. Then the close commit:
   `git commit --allow-empty -m "phase <n>: <title> verified" --trailer "TDD-Phase: scaffold"`
   (`tdd_order` ignores an empty commit; `phase_ledger.py` marks the phase done only here). Push the run branch.
6. A check fails: write a fix prompt. After 3 failed fix calls on one phase, Cadence hard stop `retries`.

### 1.10 Start the run

1. Steps 0a–0e are done and the Step 0d PR is merged.
2. Make branch `snowflake-host` from `main`. Commit the AGENTS.md in §1.11 on it. Open a GitHub issue for the run.
3. `tools/coco-clone snowflake-host`.
4. In Claude Code, in `~/Projects/bob-killer-snowflake` on that branch:
   `/cadence Build the Bob Killer Snowflake host per docs/SPEC.md. Delegate each E1 phase to CoCo with tools/coco-phase and check per §1.9.`

### 1.11 AGENTS.md for CoCo (put this in `labs/bob_killer/AGENTS.md`)

```markdown
# Bob Killer — working agreement for CoCo

You build. Claude Code checks your work against git history and the gates, then merges it.
Each call gives you one phase or one fix. Do only that.

Your working directory is labs/bob_killer/ in your own clone. Code paths below are relative to it.
The run evidence directories are at the repo root: ../../.context/runs/ and ../../.context/evidence/.

Read these files before any task, in this order:
1. SPEC.md            (core design; the authority on the compiler)
2. CLAUDE.md          (the TDD loop and the hard rules; they apply to you too)
3. ../../docs/SPEC.md (the authority on the Snowflake host)

If two documents conflict, stop with status blocked and name the conflict. Do not choose for yourself.

## The loop (do not skip a step)
1. RED: write the test first, under tests/ only. Record it:
   `uv run python scripts/record_run.py --phase red <test paths>`
   For a live test: `uv run python scripts/record_run.py --phase red -- -m live <test paths>`
   (the default options deselect live tests). Confirm it fails for the reason you state.
   Commit the test and the run record together.
2. GREEN: write the minimum code to pass. Do not change an existing assertion or test function.
3. REFACTOR: remove duplication. All tests stay green.
4. Commit subject: `p<n>/<red|green|refactor|scaffold>: <what>`. Never write "phase" and a number in a subject.
   ONE final trailer paragraph: `TDD-Phase: red|green|refactor|scaffold`.
5. Before you stop: `uv run python scripts/gates.py --base <base sha from the prompt>` exits 0.
   End with the COCO_RESULT block.

## Hard rules
- Exact parity. No tolerances. No skip, xfail, approx or isclose without an ALLOWLIST.md row.
- Every type is defined once, in src/bob_killer/contracts/, as a strict Pydantic model. No second copy of
  a type in the app or in SQL. DDL and JSON Schema are generated from the contracts.
- pandas is not a dependency anywhere.
- No credentials or passwords in files. Never use an admin role.
- Do not push, add remotes, rebase, amend, squash, reset, switch branches, or edit anything under .git/.
- Touch only the paths that the phase allows. In ../../.context/ touch only runs/ and evidence/.
- Never change ../../tools/, scripts/bk_gates/, scripts/gates.py, scripts/record_run.py, ../../.github/,
  pyproject.toml or uv.lock. Never write TDD-Phase: gate-change. If you need one of these, stop blocked.
- Snowflake: run DDL only in schemas named TEST_* that a test fixture creates, or in the schema the phase
  names. Never DROP anything else.
- If a fact in ../../docs/SPEC.md §4 is false in this account, stop with status blocked.
- If a tool, scope or policy refuses an action, stop with status blocked. Never route around it with
  another tool (for example the snow CLI in place of the SQL tool).

## Commands (from labs/bob_killer/)
- uv run pytest -q                                  # all offline tests (live is deselected)
- uv run pytest -m live tests/live                  # live tests, connection bob_killer
- uv run python scripts/gates.py --base <sha>       # all gates
- uv run python scripts/export_contracts.py         # only after a SCHEMA_VERSION bump
- uv run --project ../.. snow snowpark build|deploy -c bob_killer --project hosts/snowflake
- uv run --project ../.. snow streamlit deploy -c bob_killer --project hosts/snowflake
```

---

## 2. Purpose and scope

### 2.1 Goal

One Snowflake-native service. A user opens a Streamlit app in Snowsight and uploads a workbook. One
upload does three things:

1. **Lands** the file on an internal stage, keyed by its SHA-256.
2. **Writes bronze rows**: each data row of each sheet as a VARIANT payload with lineage (the donor's
   feature, fixed).
3. **Runs Bob Killer**: the core `create_run` then `execute_run`, with run and stage status in Snowflake
   tables. The app shows the status.

### 2.2 Honest scope

The core is at core SPEC Phase 0. Its stage registry is empty, so today a run has one stage only: the
host's `land_bronze`. This work builds the **Snowflake host**: storage, upload, landing, bronze, run status
and deployment. Later core phases add stages. Some will need host work too (for example, core decision 9
`workbook.db` storage and long runs). This spec does not promise that they run with no host change.

This work does **not** build core SPEC Phase 6 (the Snowflake Streamlit generator for converted workbooks).
It does record the platform facts that core Phase 6 needs.

### 2.3 Non-goals

- Compiler stages (extract, graph, lift, generate, verify).
- The Excel oracle. `UnavailableOracle` stays.
- `.xls` input. The core rejects it (415). The donor accepted `.xls`; this is a deliberate change.
- Silver and gold layers, Iceberg as default, multi-tenant access control, Native App packaging.
- The FastAPI app inside Snowflake. FastAPI stays the local and CI surface.

### 2.4 Success signals

- A user uploads a fixture workbook in Snowsight. The app shows the run `succeeded` and its stages.
- `BRONZE_ROWS` holds one row per data row per sheet, with the file SHA-256 and the run id.
- A second upload of the same bytes makes a new run and adds **zero** bronze rows. Two parallel uploads of
  the same bytes add the rows once.
- An `.xls` file (415), a zip bomb (413) and a file over 50 MB (413) are rejected with the core's messages,
  and no run row is written.
- `gates.py` passes on the run branch.

---

## 3. Source inventory

### 3.1 Core (`labs/bob_killer/`, imported from sandbox @ `40987f0`)

| Module | State | Use here |
| --- | --- | --- |
| `contracts/` (`StrictModel`, `Run`, `StageStatus`, `RunView`, `UploadLimits`, `SCHEMA_VERSION=1`) | v1 snapshots (`ddl.sql`, `schemas.json`, `openapi.json`) | Add `contracts/bronze.py`; maybe v2 (D2) |
| `contracts/ddl.py` | SQLite only; raises `TypeError` on unmapped types | Refactor into a dialect registry; SQLite output unchanged |
| `store/db.py` `RunStore` | SQLite; stage order by `rowid` | Extract `RunRepository` Protocol |
| `service/runs.py` | `create_run`, `execute_run`; hint is concrete `RunStore`; success detail is `""` | Protocol hint; stage may return a detail (D3) |
| `service/uploads.py` | Zip checks: 50 MB, 500 MB, 10 000 members, ratio 100 | The only upload check |
| `registry.py` | `Stage = Callable[[str], None]`; `add` raises on a duplicate | `Stage` returns `str | None` (D3) |
| `api/`, `cli.py` | FastAPI + CLI | Type hint change only |
| Gates (`scripts/gates.py`) | `tdd_order`, `assertions_frozen`, `no_oracle_literals`, `no_silent_skips`, `exact_parity`, `contracts_versioned`, `append_only_log`, `types_lint`, `boundaries`, `coverage` (≥ 90% of `src/`), `mutation` (nightly, `runtime/` only) | Host code goes in `src/` and `tests/`, so the gates cover it. Step 0d adds the few changes. |
| `pyproject.toml` deps | `pydantic~=2.11`, `fastapi~=0.115`, `python-multipart`. openpyxl is **not** a dependency | Step 0d adds the `snowflake` extra |

### 3.2 Donor (`snowflake-excel-streamlit` @ `257f9e8`)

| Behavior | Decision | Reason |
| --- | --- | --- |
| Streamlit multi-file upload with preview | **Port** as a thin client | The user surface |
| Row JSON: `metadata.column_names`, `metadata.dtypes` (Python class names of pandas values, `serializers.py:45`), `data` | **Port the meaning**, new typed payload (§6.1). The README documents the mapping | Downstream readers |
| Injected `id` column = DataFrame index (`bronze.py:60`) | **Drop**; key = `(file_sha256, sheet, row_number)` | Index restarts per file |
| Batches of 10 000 | **Port** as config | Same intent |
| `pandas.read_excel` (first sheet only) | **Drop**; openpyxl, all sheets | pandas forbidden; data loss |
| Dedup by filename in `st.session_state` | **Drop**; dedup by SHA-256 in a table | Wrong for same name, new bytes; lost on reload |
| Password auth from YAML / env | **Drop**; SiS session; key-pair locally | No secrets in files |
| Import-time singletons | **Drop** | Hidden global state |
| `raw_data STRING` in Iceberg (needs external volume) | **Change**: standard table, VARIANT | No external volume to start |
| `uploaded_at` from `CURRENT_TIMESTAMP()` | **Keep the idea**: `landed_at` set by Snowflake | |
| `.xls` accepted | **Drop** | Core rejects `.xls` |
| README claims tests | **Note**: the repo has none | |
| `sample.xlsx` | **Not a fixture** | Written by openpyxl, not Excel (`creator=openpyxl`); one sheet, 30 024 data rows, no formulas. Breaks the "saved in real Excel" fixture rule. Use only as an optional volume check. |

---

## 4. Platform facts and constraints

From Snowflake docs, opened 2026-10-16. Phase 1 verifies each one in your account and writes the output
to `.context/evidence/snowflake_platform_<date>.md`. A false fact stops the run.

| # | Fact | Consequence | Phase 1 check |
| --- | --- | --- | --- |
| F1 | SiS **container runtime** supports **Python 3.11 only**, installs from `pyproject.toml` with uv, needs Streamlit ≥ 1.50, runs on a compute pool. | The app cannot import the core (3.12, PEP 695 syntax). The app is the separate package `bob_killer_sis`. | Deploy a hello app; show `sys.version` and `get_active_session().get_current_role()`. |
| F2 | Python stored procedures support runtimes 3.10–3.13. | The core runs in 3.12 stored procedures (D1). | A 3.12 procedure that imports `bob_killer.contracts`, builds a `Run`, and returns `sys.version`. |
| F3 | Procedure packages come from the Anaconda channel, or from PyPI through an artifact repository. | The import set must resolve for 3.12: `pydantic` 2.11.x, `pydantic-core`, `annotated-types`, `typing-extensions`, `typing-inspection`, `openpyxl`, `et-xmlfile`, `snowflake-snowpark-python`. Not `fastapi`. | `SELECT package_name, version FROM information_schema.packages WHERE language='python' AND runtime_version='3.12' AND package_name IN (...)`. If one is missing, prove the artifact-repository path. Record which path works. |
| F4 | Standard tables do not enforce PRIMARY KEY or UNIQUE, and have no CHECK constraints. They do enforce NOT NULL. | Enum and key rules live in code: strict models on write and on read, `MERGE` for upserts and dedup. | In a TEST_ schema: a duplicate PK insert succeeds; a NULL into NOT NULL fails. |
| F5 | A SiS app and an owner's-rights procedure run as the owner role; inside an owner's-rights procedure the current schema is the procedure's schema. | One role owns everything; tables are named without a schema, so one deployment = one schema (D7). | A procedure returns `CURRENT_SCHEMA()`. |
| F6 | `session.file.put_stream` compresses by default (`auto_compress=True`). | The app uploads with `auto_compress=False` and `overwrite=False`. | Put a fixture, list the stage, compare SHA-256 after `session.file.get_stream` inside a procedure. |
| F7 | A container-runtime app installs packages from PyPI, so it needs an external access integration. | The bootstrap SQL creates a network rule and integration for `pypi.org` and `files.pythonhosted.org`, unless the account has a Snowflake-provided one. | Deploy the hello app with and without the integration. Record what works. |
| F8 | `snow snowpark deploy` deploys what `snow snowpark build` made. Imports are zips or files on a stage. | Deploy = `snow snowpark build` then `snow snowpark deploy`. The core and host code ship as the build zip. | Run both; `DESCRIBE PROCEDURE` shows the imports. |
| F9 | Snowpark `session.call(name, *args, block=False)` returns an `AsyncJob`. | The app starts the run without blocking and polls tables. | Call a procedure with `block=False`; check `is_done()`. |
| F10 | `save_as_table` and other DDL commit implicitly. | Bronze writes use `INSERT … SELECT PARSE_JSON(...)` with bound values inside `BEGIN … COMMIT`, never DDL inside the transaction. | A live test (Phase 4). |

---

## 5. Architecture

```mermaid
flowchart LR
  U[User in Snowsight] --> A[SiS app, Python 3.11<br/>src/bob_killer_sis]
  A -- put_stream, auto_compress=False --> S[(@UPLOADS/sha256.xlsx)]
  A -- CALL CREATE_RUN --> C[Procedure 3.12<br/>bob_killer.hosts.snowflake]
  C --> R[(RUNS, STAGE_STATUS)]
  A -- CALL EXECUTE_RUN block=False --> E[Procedure 3.12]
  E --> R
  E -- land_bronze --> B[(LANDED_FILES, BRONZE_ROWS)]
  E -- get_stream --> S
  A -- SELECT by run_id, JSON Schema check --> R
```

### 5.1 Code layout

Repo root: `tools/` (CLI tooling, Step 0 only), `pyproject.toml` (root uv project for `snow`),
`.github/`, `.context/`. Everything below is under `labs/bob_killer/`.

| Path | Python | Contents |
| --- | --- | --- |
| `src/bob_killer/contracts/bronze.py` | 3.12 | `LandedFile`, `BronzeRow`, `BronzePayload`, `CellJson` |
| `src/bob_killer/contracts/ddl.py` | 3.12 | `ddl_dialects` registry; `sqlite` built in |
| `src/bob_killer/store/__init__.py` | 3.12 | `RunRepository` Protocol |
| `src/bob_killer/hosts/snowflake/ddl.py` | 3.12 | Registers the `snowflake` dialect |
| `.../hosts/snowflake/store.py` | 3.12 | `SnowflakeRunStore(session)` |
| `.../hosts/snowflake/bronze.py` | 3.12 | `rows_from_workbook(data) -> Iterator[BronzeRow]` (pure); `BronzeWriter` (MERGE + batched INSERT) |
| `.../hosts/snowflake/procedure.py` | 3.12 | Handlers `create_run_handler`, `execute_run_handler`; registers `land_bronze` once at import |
| `src/bob_killer_sis/streamlit_app.py` | **3.11** | The app; never imports `bob_killer` (Step 0d contract) |
| `src/bob_killer_sis/schemas.json` | — | Copy of the core JSON Schema snapshot; a test checks it is identical |
| `tests/unit/hosts/`, `tests/unit/sis/` | | Offline tests: fake session that records SQL text and binds; AppTest |
| `tests/live/` | | `@pytest.mark.live`; real account, TEST_ schema per session |
| `hosts/snowflake/snowflake.yml`, `hosts/snowflake/sql/` | | Snowflake CLI project; generated DDL; bootstrap and teardown SQL |

Because host code is in `src/` and its tests are in `tests/`, `tdd_order`, `assertions_frozen`,
`no_oracle_literals`, `no_silent_skips`, `types_lint` and `coverage` apply with no gate change. `coverage`
runs the offline suite, so the host reaches 90% through fake-session unit tests, not live tests.

### 5.2 One upload

1. The app reads the bytes and computes SHA-256. It puts them at `@UPLOADS/<sha256>.xlsx`
   (`auto_compress=False`, `overwrite=False`; an existing file with the same name has the same bytes).
   The path has only the hex digest, so the user's filename cannot change the path.
2. The app calls `CREATE_RUN(stage_file, filename, sha256)` (blocking, short). The handler reads the staged
   bytes with `session.file.get_stream`, checks the SHA-256, and calls core `create_run`. It returns
   `{"run_id": ...}` or `{"rejected": {"status": 413|415, "detail": ...}}`. A rejection writes no run row.
3. The app calls `EXECUTE_RUN(run_id)` with `block=False`, keeps the `AsyncJob` in `st.session_state`, and
   polls `RUNS` and `STAGE_STATUS` by `run_id` every 2 s until the run state is final or the job is done.
4. `execute_run` runs the stages. `land_bronze(run_id)` resolves `run_id → sha256 → stage file`, then:
   `BEGIN; MERGE INTO LANDED_FILES …` on `file_sha256`. If the MERGE inserted 0 rows, `COMMIT` and return
   detail `already landed`. If it inserted 1, insert `BRONZE_ROWS` in batches of `batch_size` with
   `INSERT … SELECT PARSE_JSON(?) …`, then `COMMIT`. Any error: `ROLLBACK`, raise. Snowflake serializes the
   two MERGE statements on one table, so parallel uploads land the rows once (the live test proves it).
5. Every row the app reads is validated against the JSON Schema snapshot after the column names are
   lowercased. A failed row shows an error, not a crash.

### 5.3 Boundary rules

- `bob_killer_sis` never imports `bob_killer` (import-linter, Step 0d).
- `bob_killer.hosts.snowflake` never imports `bob_killer.api`, `fastapi` or `uvicorn` (import-linter).
- Core never imports `bob_killer.hosts` (layers contract).
- Only `procedure.py` gets a session from Snowpark. `store.py` and `bronze.py` receive it.
- SQL text never contains user data. Every value is bound. Table names come from contracts.
- Bronze reads cached values only. Bronze is a landing copy, never a parity source.

---

## 6. Contracts and Snowflake objects

### 6.1 New models (`contracts/bronze.py`)

```python
CellJson = float | int | str | bool | None      # dates as ISO-8601 text; errors as their text (#DIV/0!)

class BronzePayload(StrictModel):
    column_names: tuple[str, ...]
    dtypes: dict[str, str]          # openpyxl data_type per column: n, s, b, d, e (not donor class names)
    data: dict[str, CellJson]

class LandedFile(StrictModel):
    table_name = "landed_files"; primary_key = ("file_sha256",)
    file_sha256: str                # 64 lowercase hex
    filename: str                   # display only
    stage_file: str                 # <sha256>.xlsx
    size_bytes: int
    first_run_id: str
    # landed_at is the Snowflake dialect column _written_at, not a model field

class BronzeRow(StrictModel):
    table_name = "bronze_rows"; primary_key = ("file_sha256", "sheet", "row_number")
    file_sha256: str
    sheet: str
    row_number: int                 # Excel row number, 1-based
    run_id: str
    payload: BronzePayload          # VARIANT
```

Header rules: the first non-empty row of a sheet is the header. A blank header becomes
`column_<letter>`; a duplicate becomes `<name>_2`, `<name>_3`. Blank cells are `null`. Cell values are not coerced.

### 6.2 Tables and dialects (D2)

- `TABLES` (SQLite) stays `(Run, StageStatus)`. SQLite DDL does not change.
- `SNOWFLAKE_TABLES = TABLES + (LandedFile, BronzeRow)`, defined in the host.
- The `snowflake` dialect maps `str→VARCHAR`, `int→NUMBER(38,0)`, `float→FLOAT`, `bool→BOOLEAN`,
  `datetime→TIMESTAMP_TZ`, enum→`VARCHAR`, nested model→`VARIANT`, all `NOT NULL`, PK as informational.
  It adds two dialect columns to every table: `_seq NUMBER AUTOINCREMENT ORDER` (insert order, like SQLite
  `rowid`) and `_written_at TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()` (this is `landed_at`).
- `SnowflakeRunStore.stages` orders by `_seq`. Its upsert is a `MERGE` that updates state and detail.

### 6.3 Objects

| Object | Name |
| --- | --- |
| Database | `BOB_KILLER` |
| Deployment schema | `APP` for production; `TEST_<uuid8>` per live-test session. Every object below lives in one schema. |
| Tables | `RUNS`, `STAGE_STATUS`, `LANDED_FILES`, `BRONZE_ROWS` |
| Stage | `UPLOADS` (internal, server-side encryption, directory on) |
| Procedures | `CREATE_RUN(VARCHAR, VARCHAR, VARCHAR) RETURNS VARIANT`, `EXECUTE_RUN(VARCHAR) RETURNS VARIANT`, runtime 3.12, owner's rights |
| App | `BOB_KILLER_APP`, container runtime |
| Compute | warehouse `BOB_KILLER_WH` (XS, auto-suspend 60 s); compute pool `BOB_KILLER_POOL` (smallest CPU, auto-suspend) |
| Network | network rule + external access integration for PyPI (F7) |
| Role | `BOB_KILLER_OWNER` (granted to SYSADMIN, to your user, and to `BOB_KILLER_SVC`) |
| Service user | `BOB_KILLER_SVC`, `TYPE = SERVICE`, key-pair, default role `BOB_KILLER_OWNER` |
| Account grant | `BIND SERVICE ENDPOINT` to `BOB_KILLER_OWNER` (container runtime) |

`hosts/snowflake/sql/00_admin_bootstrap.sql` creates the role, service user, warehouse, pool, database,
network rule (`PYPI_RULE`), integration (`BOB_KILLER_PYPI_EAI`) and grants. Applied 2026-10-16 as ACCOUNTADMIN.
The first run also made schemas `CORE` and `BRONZE`; D7 uses one schema per deployment, so `APP` replaces them
(`CREATE SCHEMA BOB_KILLER.APP`; drop `CORE` and `BRONZE` while they are empty). `99_teardown.sql <schema>` drops one deployment schema.

### 6.4 Live tests

A session fixture creates `TEST_<uuid8>`, deploys tables, stage and both procedures into it, runs the
tests, and drops the schema in teardown. Without a working connection the live suite **fails**; it never skips.

---

## 7. Decisions

| ID | Question | Decision | Rejected |
| --- | --- | --- | --- |
| D1 | Where does the core run? | Two 3.12 owner's-rights procedures, `CREATE_RUN` and `EXECUTE_RUN`, in-process (core decision 7). | SPCS FastAPI service (infra with no load to justify it); backport to 3.11 (rewrites PEP 695 code). |
| D2 | Snowflake DDL | Dialect registry in `contracts/ddl.py`; SQLite output byte-identical; Snowflake set adds bronze models and dialect columns. If `contracts_versioned` reports a snapshot diff (for example, new schemas in `schemas.json`), bump `SCHEMA_VERSION` to 2; a test asserts `v2/ddl.sql == v1/ddl.sql`. | Hand-written SQL (second type definition). `StageStatus.ordinal` (changes SQLite DDL and every `StageStatus` call site). |
| D3 | Stage contract | `Stage = Callable[[str], str | None]`; `execute_run` writes the returned text as the success detail. Existing stages return `None` (detail `""`, unchanged). | A side channel for the detail. |
| D4 | Bronze placement | Stage `land_bronze`, registered once at `procedure.py` import (`if "land_bronze" not in registry.stages`). A context variable carries the session and config per call. A test asserts it is the first stage. | A step before `create_run` (no status, no run lineage). |
| D5 | Dedup | SHA-256, by `MERGE` inside a transaction (§5.2 step 4). | Filename; check-then-insert. |
| D6 | Bronze table type | Standard table, VARIANT. Iceberg is a later option. | Iceberg default (needs an external volume). |
| D7 | One schema per deployment | Unqualified table names; the procedure's schema decides. Test isolation is a TEST_ schema. | CORE/BRONZE split (procedures could not be pointed at test tables). |
| D8 | App ↔ contracts | JSON Schema snapshot copy, identity-tested. | Import (impossible on 3.11); copy models. |
| D9 | Code home | New repo `bob-killer-snowflake`. The core is imported at `labs/bob_killer/` with its git history (`git subtree split` from sandbox `40987f0`), so paths, gates and CI work unchanged. Host code goes in the core's `src/` and `tests/`. | Stay in sandbox (the user asked for a new repo); separate host distribution (every gate hard-codes core paths). |
| D10 | Excel reader | openpyxl `read_only=True, data_only=True`, in the `snowflake` extra. | pandas (forbidden); Polars `read_excel` (adds fastexcel). |
| D11 | Mutation scope | Core `[tool.mutmut]` stays `runtime/`. Host tests are scored by Cadence R2 (`/test-benchmark`). | A host mutmut config (a config change during the run). |

---

## 8. Execution plan

Each phase ends with its exit criteria met and `uv run python scripts/gates.py --base <run-base-sha>` green.
Do the phases in order. "Allowed paths" are relative to `labs/bob_killer/`, plus `.context/runs/` and
`.context/evidence/` at the repo root.

### Phase 1: Platform proof

Allowed paths: `hosts/snowflake/`, `src/bob_killer/hosts/snowflake/session.py`, `tests/live/test_platform.py`, `tests/live/conftest.py`, `tests/unit/hosts/test_session.py`, `.context/evidence/`.

- The bootstrap is already applied (Step 0b). Commit `hosts/snowflake/sql/00_admin_bootstrap.sql` as it ran,
  and write `99_teardown.sql`. If the `BOB_KILLER_OWNER` role is missing, stop with status blocked.
- Red first: tests import `bob_killer.hosts.snowflake.session` (not yet written), so they fail for a stated
  reason. Green: `session.py` with `open_session(connection_name)` and the `test_schema()` context manager
  (create `TEST_<uuid8>`, yield, drop). The F2, F4, F5, F6, F9 checks are live tests that use them.
- Evidence for F1, F3, F7, F8: the commands and outputs in `.context/evidence/snowflake_platform_<date>.md`.

Exit: every F1–F10 fact is confirmed in evidence, or the phase stops blocked with the false fact named.

### Phase 2: Contracts and DDL dialects

Allowed paths: `src/bob_killer/contracts/`, `src/bob_killer/hosts/__init__.py`, `src/bob_killer/hosts/snowflake/__init__.py`, `src/bob_killer/hosts/snowflake/ddl.py`, `tests/unit/`, `hosts/snowflake/sql/10_tables.sql`.

- Red: `ddl_dialects["sqlite"]` output for `TABLES` equals `snapshots/v1/ddl.sql`, read from the file.
- Green: refactor `ddl.py` into the registry. No output change.
- Red/green: strict-model tests for `BronzePayload`, `LandedFile`, `BronzeRow` (wrong type, extra key rejected).
- Red/green: the `snowflake` dialect; an unmapped type raises `TypeError`; golden test against
  `hosts/snowflake/sql/10_tables.sql`, generated by `uv run python -m bob_killer.hosts.snowflake.ddl`.
- Run `contracts_versioned`. On a diff: bump to v2, run `scripts/export_contracts.py`, add the
  `v2/ddl.sql == v1/ddl.sql` test.

Exit: SQLite DDL unchanged; `contracts_versioned` green.

### Phase 3: Repository Protocol, stage detail, SnowflakeRunStore

Allowed paths: `src/bob_killer/store/`, `src/bob_killer/service/runs.py`, `src/bob_killer/registry.py`, `src/bob_killer/api/main.py`, `src/bob_killer/cli.py`, `src/bob_killer/hosts/snowflake/store.py`, `tests/unit/`, `tests/integration/`, `tests/live/`.

- Red: a shared `RunRepository` suite (insert, get missing → None, set_state, upsert twice → one row,
  stages in insert order after `create_run` + `execute_run`). It takes a store factory.
- Green: extract the Protocol; type `service/runs.py`, `api/main.py`, `cli.py` against it; the suite runs on `RunStore`.
- Red/green (D3): a stage that returns `"x"` gets detail `"x"`; a stage that returns `None` gets `""`.
- Red/green: `SnowflakeRunStore` with the fake session (SQL text, binds, MERGE shape, read validation:
  a bad enum value from the database raises).
- Live: the shared suite on `SnowflakeRunStore` in the TEST_ schema.

Exit: shared suite green on both stores, offline and live; coverage ≥ 90%.

### Phase 4: Bronze landing

Allowed paths: `src/bob_killer/hosts/snowflake/bronze.py`, `tests/unit/`, `tests/live/`, `tests/fixtures/workbooks/bronze_*.xlsx`, `tests/oracle/`.

- Fixtures saved in real Excel (cached values present): two sheets; blanks; an error cell; a date;
  duplicate and blank headers; an empty sheet. Expected values come from the cached values or from
  `tests/oracle/*.json` with `source` and `verified_by`. No literal expected values. If a fixture cannot be
  made in real Excel, stop with status blocked (you make it and commit it).
- Red/green: `rows_from_workbook`: all sheets, Excel row numbers, header rules, dtypes, nulls, errors, empty sheet → no rows.
- Red/green: `BronzeWriter` with the fake session: MERGE then batches (batch size 2 in the test), bound
  values, `ROLLBACK` on error.
- Live: first landing writes rows; second landing of the same bytes writes zero and returns `already landed`;
  two parallel landings write the rows once; a writer that raises after batch 1 leaves zero rows.

Exit: offline and live suites green.

### Phase 5: Procedures and deployment

Allowed paths: `src/bob_killer/hosts/snowflake/procedure.py`, `hosts/snowflake/snowflake.yml`, `hosts/snowflake/sql/`, `tests/unit/`, `tests/live/`, `tests/fixtures/workbooks/`.

- Red/green with the fake session: SHA mismatch fails; `UploadRejected` → the `rejected` JSON; `land_bronze`
  is the first stage; registration twice in one interpreter does not raise; returned JSON validates
  against `schemas.json`.
- `snowflake.yml` for both procedures: runtime 3.12, packages per the F3 evidence, the build zip as import.
- Live: deploy into the TEST_ schema with `snow snowpark build` + `snow snowpark deploy`; `CREATE_RUN` then
  `EXECUTE_RUN` on a staged fixture → `succeeded` with rows; `.xls` → 415, zip-bomb fixture → 413,
  51 MB → 413, and no run row in each case.

Exit: one build+deploy command pair deploys to any schema; live suite green.

### Phase 6: Streamlit app

Allowed paths: `src/bob_killer_sis/`, `hosts/snowflake/snowflake.yml`, `tests/unit/sis/`, `tests/live/`.

- `streamlit_app.py`: upload (`.xlsx`, `.xlsm`, many files); preview of the first 5 rows per sheet with
  openpyxl; SHA-256; `put_stream` (`auto_compress=False`); `CREATE_RUN`; `EXECUTE_RUN` with `block=False`;
  polling; run and stage display; the `rejected` message.
- AppTest with an injected fake session: stage path, bound args, rejected message, a row that fails JSON
  Schema shows an error.
- Test: `src/bob_killer_sis/schemas.json` equals the core snapshot file.
- `snowflake.yml` app entry: container runtime, compute pool, the PyPI integration (F7), `streamlit>=1.50`.
- Live: deploy into the TEST_ schema with `snow streamlit deploy`; check that the app object exists and its URL resolves.

Exit: deploy works in a TEST_ schema. After the merge, you deploy to `APP`, open the app, and check the
§2.4 signals; the query outputs go to `.context/evidence/`.

### Phase 7: Docs

Allowed paths: `hosts/snowflake/README.md`, `README.md` (the bob_killer one).

- Setup, bootstrap, deploy, teardown, rollback (§11), the donor payload mapping: old `metadata.dtypes`
  held Python class names per cell (`int`, `float`, `str`, `bool`, `Timestamp`, `Timedelta`, `NoneType`); new
  `dtypes` hold openpyxl codes (`n`, `s`, `b`, `d`, `e`). The old `data.id` (DataFrame index) is gone; use
  `(file_sha256, sheet, row_number)`.
- A separate PR to the donor repo adds a README pointer. Claude Code opens it, not CoCo.

Exit: a clean clone deploys to a new TEST_ schema by following the README.

---

## 9. Gates and how CoCo works under them

- The core's Claude Code hooks (`labs/bob_killer/.claude/settings.json`) load only when Claude Code starts in
  `labs/bob_killer/`. This run starts at the repo root, so they do not load, and CoCo never triggers them.
  Claude Code does not edit `src/` or `tests/` in this run. The controls are §1.2. Do not touch `.context/hooks.log`; only Claude Code hooks append to it.
- `no_silent_skips` is a static scan of `tests/`. Live tests use the registered `live` marker, not `skip`.
  pytest reports deselected tests, so the offline run hides nothing.
- Red evidence: `scripts/record_run.py --phase red` before each green commit.
- Do not squash. If a squash is needed, Claude Code uses the verified-squash rule in `CLAUDE.md`.
- Use `--base <run-base-sha>` with `gates.py`: its default base is the merge-base with `main`.
- Cost: one CoCo call per phase or per fix. The logs in `.context/coco/` record each call.

---

## 10. Acceptance criteria

1. §2.4 signals, each shown by a test or a query output in `.context/evidence/`.
2. `uv run pytest -q`, `uv run pytest -m live tests/live`, `gates.py` green; SQLite DDL unchanged.
3. Coverage ≥ 90% of `src/` from the offline suite; R2 test-benchmark has no HIGH item.
4. No pandas, no password, no ACCOUNTADMIN in any repo file.
5. One documented deploy path for procedures and app; one teardown script.

---

## 11. Risks and rollback

| Risk | Mitigation |
| --- | --- |
| pydantic 2.11 not on the Anaconda channel for 3.12 | F3 proves the artifact-repository path. If neither works, stop. |
| Procedure run time for later compiler stages | Record the limit in Phase 1 evidence for core planning. |
| Idle compute pool cost | Auto-suspend in the bootstrap. |
| No PK/UNIQUE/CHECK enforcement (F4) | Strict models on write and read; MERGE; live tests that write bad rows by raw SQL. |
| CoCo acts outside its phase | §1.2 controls; hard stop `security`. |
| Generated apps (core Phase 6) must run on 3.11 | Out of scope. Phase 1 evidence feeds a core ticket. |
| Core changes in sandbox after the import | The import is a snapshot at `40987f0`. Bring later sandbox changes with `git subtree pull` in a human-reviewed PR. |

**Rollback.**
- Code: before merge, revert the run branch (CoCo's branch is disposable). After merge, revert the PR.
- Contracts: a v2 snapshot cannot be removed after merge (append-only by design). Before merge, drop the commit.
- Snowflake: each deployment is one schema. `99_teardown.sql <schema>` drops it. To roll back production,
  check out the previous tag and run the build + deploy pair into `APP`. Bronze data in `APP` survives a code rollback.
- Local SQLite: the SQLite DDL does not change, so no local reset is needed.

---

## 12. Open questions (defaults apply if no answer)

| Q | Default |
| --- | --- |
| Database, role, schema names | `BOB_KILLER`, `BOB_KILLER_OWNER`, `APP` |
| Key-pair or PAT | Key-pair; PAT only if CoCo rejects key-pair |
| GitHub remote for the new repo | Private `jtouley/bob-killer-snowflake`, created on your go |
| Run branch | `snowflake-host` from `main` after Step 0d merges |
| `CORE` / `BRONZE` schemas from the first bootstrap | Replace with `APP` (D7) |

---

## 13. Review record

| Round | Reviewer | Verdict | Result |
| --- | --- | --- | --- |
| P3 r1 (on r2) | Cadence plan-review | NOT READY (MF-1–14, NTH-1–9) | Applied in r3/r4, first table |
| P3 r2 (on r4) | Cadence plan-review | NOT READY (MF-1–6, NTH-1–8) | Applied in r5, second table |

| ID | Fix in r3 |
| --- | --- |
| MF-1 gates miss host paths | D9: host code in the core's `src/` and `tests/`; Step 0d gate tests |
| MF-2 v2 / SQLite break | D2: SQLite `TABLES` unchanged; Snowflake set; `_seq` dialect column; no `ordinal` |
| MF-3 stage contract | D3 detail return; D4 register once, context variable |
| MF-4 polling | Two procedures; `block=False`; poll by run_id (§5.2) |
| MF-5 dedup race, transaction | MERGE in `BEGIN…COMMIT`; INSERT…SELECT; F10; fault-injection live test |
| MF-6 live repeatability | D7 one schema per deployment; TEST_ schema deploy |
| MF-7 coverage / mutation | Fake-session unit tests; D11 |
| MF-8 deploy facts | F7, F8; build + deploy; PyPI integration |
| MF-9 put_stream | F6; `auto_compress=False` |
| MF-10 openpyxl not core | §3.1; Step 0d extra; F3 import set; import-linter forbid fastapi |
| MF-11 rollback | §11 |
| MF-12 trust boundary | §1.2 controls 1–8; gate changes moved to Step 0d |
| MF-13 ledger / stop guard | Claude Code close commit only; `p<n>/` prefixes; Monitor wait; P1 keeps headers |
| MF-14 cortex flags | Verified on v1.2.14 (§1.3); flags in `tools/coco-flags.sh` |
| NTH-1 | §1.4 key-pair first |
| NTH-2 | §3.1 real gate names; `--base` |
| NTH-3 | §3.2 donor facts corrected |
| NTH-4 | `int` in `CellJson`; `landed_at` is a dialect column |
| NTH-5 | Lowercase keys before JSON Schema (§5.2) |
| NTH-6 | F4 reworded |
| NTH-7 | §2.2 reworded |
| NTH-8 | §1.8 entry invariant before each call |
| NTH-9 | §1.8 step 1 logs to a Cadence-approved path |

| r2 ID | Fix in r5 |
| --- | --- |
| MF-1 Step 0d breaks gates | §1.6 items 1 and 3: stub packages + `root_packages`; `pkgutil` discovery |
| MF-2 CoCo permissions unproven; blocklist gaps | §1.7 `tools/coco-probe`; §1.2 control 7 says the list is a speed bump; clone isolation (control 1) |
| MF-3 `no_oracle_literals` skips `tests/live` | §1.6 item 4 |
| MF-4 post-call checks miss state | `tools/coco-guard` hashes all of `.context/`, refs, hooks, config, Cadence skill; clone-check; remote check handles no origin |
| MF-5 background wait can hang | Wrapper watchdog (6600 s) always writes `COCO_EXIT`; lock; `timeout: 7200000`; tested with a stub |
| MF-6 phases blocked by allowed paths; CI fails | §1.6 items 5–7: full dependency set, `uv run --no-project --python 3.11`, a real live test from day one |
| NTH CI on run-branch pushes | §1.6 item 7; §1.2 control 8 |
| NTH Phase 1 red impossible | Phase 1 tests red against `session.py` |
| NTH red records for live tests | AGENTS.md: `record_run.py --phase red -- -m live` |
| NTH `.context` paths ambiguous | AGENTS.md names `../../.context/` |
| NTH old Cadence files | Moved to `docs/history/sandbox-gh-5/` |
| NTH CoCo self-update | `tools/coco-phase` version check against evidence |
| NTH core hooks wording | §9 |
| NTH `entry_invariant --check` | §1.9 before-call step 1 |

