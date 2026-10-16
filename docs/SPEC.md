# Bob Killer on Snowflake — Build Spec (Claude Code + Cadence orchestrates, CoCo builds)

Oct 16, 2026 · Jason Touleyrou · Status: r8 (plan settled decisions folded; goal §2.0; D11–D16)

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
| Step 0a–0c, 0e (before Cadence) | You + Claude Code | Anthropic | CLIs, connection, bridge, probe. Done 2026-10-16. |
| **Phase 1** gate prep | **Claude Code** | Anthropic | §1.6. Gate-change commits; you review them at the PR. |
| A1–A5 | Claude Code | Anthropic | The vibe-test target is this file. |
| P1–P9 | Claude Code | Anthropic | The P1 plan copies §8 and keeps the `### Phase N:` headers (the phase ledger reads the P1 plan, not this file). P3 and P6 run as separate Claude Code agents. |
| **E1, Phases 2–8, one call per phase** | **CoCo through `tools/coco-phase`** | **Snowflake** | CoCo builds and commits the phase in its isolated clone. |
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
   in its transcript. `tools/coco-guard verify` after the call lists every change, and any change is a Cadence
   hard stop `security`. Cadence's own mutable files (`.context/breadcrumbs/`, `.context/cadence-session*.json`,
   `.context/sessions/`) are not hashed raw; the run identity fields of the session file are compared instead
   (`pipeline_run_id`, `task_id`, `branch`, `worktree`, `hard_stop`, `resume_slug`, `status`).
3. **Clone check.** `tools/coco-guard clone-check`: the clone's `.git/config` is byte-identical to its
   clone-time baseline (so no `core.fsmonitor`, `core.hooksPath` or alias was planted), the clone is clean
   (except the core hooks' output: `.context/hooks.log`, `.context/coco/BLOCKED`, and untracked
   `.context/runs/<id>/` directories that hold a `hook-run.json`; Claude Code archives them to
   `.context/coco/clone-<n>/`), has no remotes and no active git hooks. Every guard git call runs with
   `-c core.fsmonitor=false -c core.hooksPath=/dev/null`.
4. **History gates.** The bob_killer gates read git history (`tdd_order`, `assertions_frozen`,
   `no_oracle_literals`, `no_silent_skips`, `exact_parity`, `contracts_versioned`). Claude Code runs them on
   the fetched commits before it merges. They catch a cheating commit no matter who made it.
5. **Path allowlist.** Each phase in §8 lists the paths it may touch. A commit outside the list fails the phase.
6. **No gate changes by CoCo.** All gate, CI, tooling, dependency and import-linter changes are Phase 1,
   made by Claude Code and reviewed by you at the PR. Claude Code runs `git diff --name-only <run-branch>..$S`
   (§1.9 step 3) and compares each **full repo path** with the list below. It does not match by basename.
   A CoCo commit that touches a listed path, or that has `TDD-Phase: gate-change`, is a Cadence hard stop `security`.
   - Files: `pyproject.toml` and `uv.lock` (repo root); `labs/bob_killer/pyproject.toml`, `labs/bob_killer/uv.lock`;
     `labs/bob_killer/src/bob_killer_sis/pyproject.toml`; `labs/bob_killer/src/bob_killer_sis/ruff.toml`;
     `labs/bob_killer/scripts/gates.py`, `labs/bob_killer/scripts/record_run.py`, `labs/bob_killer/scripts/hook_stop.py`.
   - Directories (every path below them): `tools/`, `.github/`, `labs/bob_killer/scripts/bk_gates/`.
   - Not on the list, and allowed in Phase 2: `labs/bob_killer/hosts/snowflake/hello_app/pyproject.toml`.
7. **Tool allowlist and blocklist.** `tools/coco-flags.sh` allows 18 named tools (no `ask_user_question`,
   no cron, no teams) and blocks git push, remote, reset, rebase, amend, worktree,
   checkout, switch, branch, tag, update-ref, config, stash, clean, filter-branch, gc and recursive `rm`. This
   is a speed bump only: a blocklist cannot list every command, and file writes into `.git/` cannot be
   blocked. Controls 1–3 are the guard.
8. **CI.** Phase 1 makes the workflow run the offline jobs on pushes to every branch and on PRs
   (`push.branches: ["**"]`). The `paths:` filters on `push` and `pull_request` stay as they are, so a push that
   changes only files outside them runs no CI. The `live` job runs automatically only when the `SNOWFLAKE_*`
   secrets exist (D12). It never runs on the nightly `schedule`. It is never a required check. Claude Code pushes
   the run branch after each phase close (Cadence E4 owns the PR).

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

**Proven by `tools/coco-probe` (2026-10-16, `.context/evidence/coco_probe_*.txt`).** `--blocked` alone does
**not** let other tools run: exec denies every tool that would need a prompt, so CoCo could not write a file.
With `--allowed <tool names>` plus `--blocked <patterns>`: file write and `git commit` work; `git push` and
`git config` are "permanently blocked by session policy"; a file write into `.git/hooks/` still works (caught
by `coco-guard clone-check`). CoCo tool names are lowercase (`read`, `write`, `edit`, `bash`, `sql_execute`, …;
listed in the exec `init` event). No `--bypass`.

**Skills.** CoCo loads every skill in `~/.claude/skills/` (the init event lists `cadence`, `ship-feature`,
`vibe-test` and others) and `exec` has no flag to turn that off. AGENTS.md forbids invoking them; `coco-guard`
hashes the Cadence skill tree, and the run repo's `.context/` is outside CoCo's clone.

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
| `tools/coco-flags.sh` | Connection name, clone path, timeout (6600 s), and the flags of every call: `--format json`, `--no-mcp`, `--private`, `--max-turns 200`, `--allowed <18 tool names>`, `--blocked <git and rm patterns>`. No `--bypass` (Step 0e). |
| `tools/coco-clone <run-branch>` | Makes the isolated clone on `coco/<run-branch>` and removes its remote. `--sync <run-branch>` fast-forwards it after a phase close. |
| `tools/coco-phase <prompt> <log>` | One call: lock (one call at a time), version check, `cortex exec -w <clone>/labs/bob_killer`, watchdog. The log always ends with `COCO_EXIT <code>`, also on timeout (124) or a signal (143). Final message in `<log>.last.md`. |
| `tools/coco-guard snapshot / verify / clone-check` | §1.2 controls 2 and 3. |
| `tools/coco-probe` | Step 0e permission probe in a throwaway repo with a local bare remote. |
| `tools/record-cli-evidence`, `tools/smoke-test` | §1.3, §1.4. |

These behaviors were tested offline with a stub `cortex` on 2026-10-16: normal exit, timeout → `COCO_EXIT 143`,
second call blocked by the lock, version mismatch refused (timeout → `COCO_EXIT 124`, signal → 143), a changed `.context/` file caught by `verify`, a
planted hook in the clone caught by `clone-check`.

**Waiting.** Claude Code starts `tools/coco-phase` with `run_in_background: true` and `timeout: 7200000`, then
waits with the `Monitor` tool until the log contains `COCO_EXIT`. The wrapper's own timeout (6600 s) ends
first, so the log always gets `COCO_EXIT`. Claude Code does not end the turn while E1 is open, because the
Cadence stop guard blocks that.

### 1.6 Gate and dependency prep — host Phase 1 (Claude Code does it, inside the run)

Cadence does not stop for human approval between A1 and R7. So the gate, CI, dependency and config changes
are host **Phase 1**, which **Claude Code does itself** (no CoCo call), as `TDD-Phase: gate-change` commits.
You review them in the draft PR before merge; CODEOWNERS requires your review for `scripts/`, `tests/gates/`,
`tools/` and the workflow. CoCo phases (2–8) start only after Phase 1 is closed, and CoCo may not change
any of these files (§1.2 control 6).

0. **Blocked stop for the core Stop hook** (G5): `scripts/hook_stop.py` allows a stop when the file
   `.context/coco/BLOCKED` exists (CoCo writes it with the reason when it stops blocked), and logs a
   `stop_allowed_blocked` event to the hook chain. A test in `tests/gates/` proves that a stop with failing gates
   and no marker is still refused. AGENTS.md tells CoCo to write the marker before it stops blocked.
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
5. **Dependencies**: optional extra `snowflake = ["snowflake-snowpark-python", "openpyxl", "pyyaml"]`; dev group adds
   `snowflake-snowpark-python`, `openpyxl`, `types-openpyxl`, `streamlit>=1.50`, `jsonschema`,
   `types-jsonschema`, `pyyaml`, `types-PyYAML`. Vendor `tests/oracle/odcs-json-schema-v3.2.0.json` from
   `bitol-io/open-data-contract-standard@v3.2.0` with `tests/oracle/odcs_schema.source.json` (url, tag, sha256) (D13). `uv lock`. No phase may change dependencies; a phase that needs one stops blocked.
6. **3.11 check and config for the app** (G19, G20, G21):
   - `src/bob_killer_sis/ruff.toml` with `extend = "../../pyproject.toml"` and `target-version = "py311"`.
   - `src/bob_killer_sis/pyproject.toml` with the app runtime deps (`streamlit>=1.50`, `snowflake-snowpark-python`,
     `openpyxl`, `jsonschema`) and `requires-python = ">=3.11,<3.12"`. It is on the control 6 list. No later phase
     may change it.
   - `[tool.coverage.run] source = ["src/bob_killer", "src/bob_killer_sis"]`, so a plain `pytest --cov` run covers
     the app. The `coverage` gate already runs `pytest --cov=src`, so the gate covers the app either way.
   - CI steps `uv run --no-project --python 3.11 python -m compileall -q src/bob_killer_sis` (uv fetches 3.11) and
     `uv run mypy --strict --python-version 3.11 src/bob_killer_sis`.
7. **CI** (`.github/workflows/bob-killer.yml`, D12):
   - Triggers are workflow-level: `pull_request` and `push` (with `branches: ["**"]`), both with the existing
     `paths:` filters; `schedule` (kept for the `mutation` job); `workflow_dispatch`. Only `push.branches` changes,
     from `[main]` to `["**"]`.
   - The offline jobs run on pushes and PRs, with the two 3.11 steps of item 6.
   - The `live` job has the job-level `if: github.event_name != 'schedule'`, so it runs on pushes, PRs and manual
     dispatch, and never on the nightly schedule. Its checkout uses the PR head commit, the same as `gates`:
     `actions/checkout@v4` with `fetch-depth: 0` and `ref: ${{ github.event.pull_request.head.sha || github.sha }}`.
   - `concurrency:` on the `live` job: `group: bk-live-${{ github.head_ref || github.ref_name }}`,
     `cancel-in-progress: false`. One run and at most one pending run per group. GitHub cancels an older pending
     run when a newer one queues, so the newest commit is tested. That is not a lost run.
   - Step `id: secrets` reads `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER` and `SNOWFLAKE_PRIVATE_KEY` through `env:`
     (a job-level `if:` cannot read `secrets`). It never echoes a value. It writes `present=true` or `present=false`.
     - All three empty (no secrets, or a fork PR): `::notice::live job skipped: no SNOWFLAKE_* secrets; see
       tools/setup-ci-secrets.sh`, exit 0. The job ends green.
     - One or two empty: `::error::` with the names of the empty secrets, exit 1. This is a misconfiguration.
     - All three present: it also reads `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE` and
       `BK_EXPECTED_ROLE` from `vars.*` and writes one `::warning::` per empty name. It does not fail for them.
       `SNOWFLAKE_SCHEMA` is not checked; live tests make their own `TEST_<uuid8>` schema.
   - Every later step has `if: steps.secrets.outputs.present == 'true'`: root `uv sync --locked`,
     `uv sync --python 3.12 --locked` in `labs/bob_killer`, the key file and `[bob_killer]` connection file
     (`umask 077`, `chmod 600`, no echo of a secret), then `uv run pytest -m live tests/live`.
   - The skip is a workflow step condition, not `pytest.skip` and not a marker skip. `no_silent_skips` stays true.
   - The `live` job is never a required check. Missing secrets are never a hard stop.
   - Phase 1 adds one live test, `tests/live/test_connection.py`: `CURRENT_ROLE()` equals the role named in the
     `BK_EXPECTED_ROLE` environment variable (not a literal). `tests/live/conftest.py` has only the connection and
     session setup. It has **no** TEST_ sweep (Phase 2 owns the sweep).
   - Phase 1 does not change `tools/setup-ci-secrets.sh`. It is a user change (`e504f06`, `TDD-Phase: scaffold`).
8. **Gate tests** in `tests/gates/` (tmp-repo pattern of `test_evasions.py`), each red before its gate change:
   a red commit under `tests/unit/hosts/` passes `tdd_order`; a green commit that edits an assertion in
   `tests/live/` fails `assertions_frozen`; a literal expected value in `tests/live/` fails `no_oracle_literals`;
   an `import bob_killer` in `src/bob_killer_sis/` fails `boundaries`; `gates.py --base 0000…` uses the
   merge-base (G17).
9. **Secrets record** (item 0a of the plan, information only): `gh secret list` and `gh variable list` on
   `jtouley/bob-killer-snowflake`, names only, to `.context/evidence/gh_secrets_<date>.txt`, with whether the next
   push runs, skips or fails the `live` job. No stop and no fix call for a missing name. Claude Code sets no secret.

**Local live runs (Phases 1 to 8).** Before each local live run, Claude Code reads the `role` key of the
`[bob_killer]` entry in `~/.snowflake/connections.toml` and exports it as `BK_EXPECTED_ROLE` in the same shell
command. No repo file names the role as a literal (§10.4). The output of each run goes to
`.context/evidence/live_phase<n>_<date>.txt`. A phase exit that says "live suite passes" means this local run
and this file. No phase exit depends on the CI `live` job.

Exit:
- `uv run python scripts/gates.py --base <run-base-sha>` exits 0.
- `uv run python scripts/gates.py --only boundaries` exits 0.
- `uv run pytest -q` passes and reports the live tests as deselected.
- The local live run passes, with output in `.context/evidence/live_phase1_<date>.txt`.
- The first push after item 7 shows the `live` job with the skip notice or a pass. The run URL and result go to
  `.context/evidence/live_ci_phase1_<date>.txt`. A skip is a pass for this check. A failure is not.
- Then the close commit `git -c core.hooksPath=/dev/null commit --allow-empty -m "phase 1: Gate and dependency
  prep verified" --trailer "TDD-Phase: scaffold"`, and push. No other Phase 1 subject has "phase" followed by a
  number. Gate-change subjects use the prefix `p1/gate-change:`.
- After the close: `tools/coco-clone snowflake-host`.

### 1.7 Step 0e — the probe and the dry run

1. `tools/coco-probe` (**passed 2026-10-16**). It asks CoCo, with the real flags, to write a file, commit, push to a local bare
   remote, write a git hook, and set `core.hooksPath`. Pass = the file was written and committed, and the push
   did not reach the remote. If the write or commit fails, the `--blocked`-only mode does not let tools run:
   change the flags (human review) and probe again. The first probe failed this way with `--blocked` alone;
   the `--allowed` list fixed it.
   The probe output (`.context/evidence/coco_probe_*.txt`) records what the blocklist does not stop.
2. Tool tests with a stub binary (`COCO_BIN=<stub>`; never the real `cortex`), 2026-10-16: normal exit; a
   CoCo child that outlives the call is killed; timeout → `COCO_EXIT 124`; the lock refuses a second call and
   leaves its log alone; Cadence breadcrumb noise passes `verify`; a changed evidence file fails it; a planted
   `core.fsmonitor` fails `clone-check` and never runs.

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

1. The log ends with `COCO_EXIT 0` and `<log>.last.md` holds the `COCO_RESULT` block (the JSON log escapes
   it). If not: record it in the Cadence findings ledger and retry once. A second failure is a failed fix call.
2. `tools/coco-guard verify` and `tools/coco-guard clone-check` pass. Copy the clone's `.context/hooks.log`
   to `.context/coco/hooks-<n>.log`.
3. `git -c core.hooksPath=/dev/null fetch "$COCO_CLONE" coco/<run-branch>`; record `S=$(git rev-parse FETCH_HEAD)`.
   Every commit in `<run-branch>..$S` has a `TDD-Phase` trailer (red, green, refactor or scaffold), a subject
   prefix `p<n>/<tdd-phase>:` with no "phase <number>" text, and touches only allowed paths (§1.2 controls 5, 6).
4. In the clone, from `labs/bob_killer/`: `uv run python scripts/gates.py --base <run-base-sha>`,
   `uv run pytest -q`, and for phases with live work `uv run pytest -m live tests/live`. This runs CoCo's code
   as you; it is the same trust as CoCo's own test runs.
5. Run `tools/coco-guard verify` and `clone-check` **again** (step 4 ran CoCo code), and check that the clone's
   `coco/<run-branch>` still points at `$S`.
6. All pass: `git -c core.hooksPath=/dev/null merge --ff-only "$S"` (the sha, not a ref name). Then the close
   commit: `git -c core.hooksPath=/dev/null commit --allow-empty -m "phase <n>: <title> verified" --trailer "TDD-Phase: scaffold"`
   (`tdd_order` ignores an empty commit; `phase_ledger.py` marks the phase done only here). Push the run branch.
   For a phase that deploys (6, 7), tag the close commit `deploy/<phase>-<short-sha>` and push the tag (rollback, §11).
7. A check fails: write a fix prompt. After 3 failed fix calls on one phase, Cadence hard stop `retries`.
8. `status: blocked`: read `blocked_reason`. A false platform fact (§4) or a missing credential is a Cadence hard
   stop (`credentials` or `retries` with the reason). Anything else gets one fix prompt that resolves the block (for
   example a spec conflict that Claude Code can settle from this file); it counts toward the 3-call limit.
9. A `clone-check` or `verify` failure is a Cadence hard stop `security`. It is never a fix prompt.

`<run-base-sha>` is the merge-base of the run branch with `main`, recorded at A1. Claude Code puts it in
every prompt.

### 1.10 Start the run

1. Steps 0a–0c and 0e are done (2026-10-16).
2. Make branch `snowflake-host` from `main`. Commit the AGENTS.md in §1.11 on it. Open a GitHub issue for the run.
3. Claude Code does Phase 1 (§1.6) itself, then `tools/coco-clone snowflake-host` before Phase 2.
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
Exception: for commit subjects, .context/ paths and hooks.log, this file wins over CLAUDE.md.

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
- Tests stay DRY and extensible; no sprawl:
  - one fake Snowflake session (`tests/fakes/snowpark.py` `FakeSession`); extend it, never write a second fake;
  - one live session fixture (`tests/live/conftest.py`); extend it, never open a second connection per file;
  - a new case for an existing rule is a new row in that test's `parametrize` table or oracle file, not a new test;
  - shared builders live in the nearest `conftest.py`; a helper used by two test files moves there;
  - no new test file when an existing file for the same unit exists.
- No credentials or passwords in files. Never use an admin role.
- Do not push, add remotes, rebase, amend, squash, reset, switch branches, or edit anything under .git/.
- Touch only the paths that the phase allows. In ../../.context/ touch only runs/ and evidence/.
  Never commit ../../.context/hooks.log (the core hooks write it; Claude Code archives it).
- Never change ../../tools/, scripts/bk_gates/, scripts/gates.py, scripts/record_run.py, ../../.github/,
  pyproject.toml or uv.lock. Never write TDD-Phase: gate-change. If you need one of these, stop blocked.
- Snowflake: run DDL only in schemas named TEST_* that a test fixture creates, or in the schema the phase
  names. Never DROP anything else.
- If a fact in ../../docs/SPEC.md §4 is false in this account, stop with status blocked.
- To stop blocked: write the reason to ../../.context/coco/BLOCKED (the core Stop hook then lets you stop), then end
  with the COCO_RESULT block (status: blocked).
- Do not invoke the skills cadence, ship-feature, spec-driven, plan-create, plan-review, plan-update,
  pr-review, babysit or commit-push-pr. Claude Code runs the pipeline; you build.
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

### 2.0 The goal (governs everything below; the run fails if this is not met)

**Bob Killer runs in Snowflake end to end.** A user uploads a workbook. Snowflake pulls it apart and gives
back a **dbt project in Snowflake** that reproduces the workbook's calculations, with docs and parity tests:

1. **Extract** every cell, formula, cached value, defined name, table and VBA module (core SPEC stage 1).
2. **Graph** the formulas into a dependency DAG; flag cycles, volatile and dynamic references (stage 2).
3. **Lift** the graph into the Workbook IR: inputs, lookups, parameters (promoted hardcodes), vectorized
   steps, outputs (stage 3), using the shared Excel runtime (`runtime/`, core decision 5).
4. **Generate** from the IR, through the generator registry (no `if target ==` in core):
   - a **dbt project** (D14) deployed as a **dbt Project on Snowflake** and run there;
   - plain-English docs, and the equivalence tests (as dbt tests);
   - the Streamlit app of core SPEC stage 4 stays a registered generator, lower priority than dbt.
5. **Verify** exact parity of the dbt outputs against Excel's cached values (D15), with a report.
6. **VBA**: inventory all modules (stage 1); translate pure-computation procedures behind tests (core SPEC
   Phase 5); cells a macro writes are listed and leave the parity denominator until translated.

Phases 1–8 (§8) are the platform this runs on: storage, upload, bronze landing, run status, procedures, the
app shell, the ODCS contract. Phases 9–16 (§8a) are the compiler and the dbt target. **Done means Phase 16's
exit holds on the golden workbooks**, not only the platform.

### 2.1 Platform goal (Phases 1–8)

One Snowflake-native service. A user opens a Streamlit app in Snowsight and uploads a workbook. One
upload does three things:

1. **Lands** the file on an internal stage, keyed by its SHA-256.
2. **Writes bronze rows**: each data row of each sheet as a VARIANT payload with lineage (the donor's
   feature, fixed).
3. **Runs Bob Killer**: the core `create_run` then `execute_run`, with run and stage status in Snowflake
   tables. The app shows the status. From Phase 9 on, the run's stages are the compiler stages above.

### 2.2 Honest limits

- **Exact parity needs Excel's arithmetic.** Elementwise `+ - * /` on doubles is exact in Snowflake SQL, but
  Excel's summation order, 15-significant-digit rounding, the 1900 leap-year bug and blank-vs-zero coercion are
  not SQL semantics. dbt models that need them call the shared `runtime/` through **Python UDFs** (or dbt Python
  models), never a SQL re-implementation (D14, core decisions 1 and 5).
- **The Excel oracle cannot run in Snowflake.** Parity is proven against the **cached values** of workbooks that
  real Excel saved: the five golden public workbooks of core SPEC "Golden sample set" (EPA, NREL, Montana DOT).
  Other input sets need desktop Excel or Microsoft Graph outside Snowflake; until that runner exists, those
  cases are listed in the report, never approximated (D15).
- **Formula fixtures need real Excel.** Small per-behavior formula fixtures must be saved by Excel. This Mac has
  none, so the golden workbooks' cached values are the fixture oracle for Phases 9–15; a fixture that needs Excel
  and has none is a blocked item with a reason, not a fake.
- **Out-of-scope features stay reported**: pivot tables, Power Query, Solver, data tables, charts, external links
  (core SPEC non-goals) appear in the coverage report.

### 2.3 Non-goals

- The Excel oracle runner (desktop Excel / Microsoft Graph). Its client protocol exists (`verify/oracle.py`).
- `.xls` input until the oracle converts it (core rejects it, 415).
- Multi-tenant access control, Native App packaging, round-tripping back into Excel.

### 2.4 Success signals

Platform (Phases 1–8):
- A user uploads a workbook in Snowsight. The app shows the run and its stages.
- `BRONZE_ROWS` holds one row per non-blank data row per sheet, with the file SHA-256 and the run id.
- A second upload of the same bytes makes a new run and adds **zero** bronze rows; parallel uploads land once.
- `.xls` (415), a zip bomb (413) and a file over 50 MB (413) are rejected; no run row is written.

Bob Killer in Snowflake (Phases 9–16), on each golden workbook:
- The run's stages extract, graph and lift it into an IR; the IR round-trips (`workbook.db` → YAML → `workbook.db`).
- The dbt generator writes a dbt project; it deploys as a dbt Project on Snowflake and `EXECUTE DBT PROJECT` runs it.
- Every non-VBA formula output cell in the dbt marts equals Excel's cached value exactly; the dbt tests prove it;
  the equivalence report lists cells checked, matched, every mismatch, and coverage (formula cells and IR steps).
- VBA modules are inventoried; macro-writable cells are listed; translated procedures match recorded output.
- Docs are generated for each workbook.

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
| Gates (`scripts/gates.py`) | `tdd_order`, `assertions_frozen`, `no_oracle_literals`, `no_silent_skips`, `exact_parity`, `contracts_versioned`, `append_only_log`, `types_lint`, `boundaries`, `coverage` (≥ 90% of `src/`), `mutation` (nightly, `runtime/` only) | Host code goes in `src/` and `tests/`, so the gates cover it. Phase 1 adds the few changes. |
| `pyproject.toml` deps | `pydantic~=2.11`, `fastapi~=0.115`, `python-multipart`. openpyxl is **not** a dependency | Phase 1 adds the `snowflake` extra |

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

From Snowflake docs, opened 2026-10-16. Phase 2 verifies each one in your account and writes the output
to `.context/evidence/snowflake_platform_<date>.md`. A false fact stops the run.

| # | Fact | Consequence | Phase 2 check |
| --- | --- | --- | --- |
| F1 | SiS **container runtime** supports **Python 3.11 only**, installs from `pyproject.toml` with uv, needs Streamlit ≥ 1.50, runs on a compute pool. | The app cannot import the core (3.12, PEP 695 syntax). The app is the separate package `bob_killer_sis`. | Phase 2: the hello app deploys with the container runtime (`DESCRIBE STREAMLIT`). After merge: you open it once; it shows `sys.version` and the role. |
| F2 | Python stored procedures support runtimes 3.10–3.13. | The core runs in 3.12 stored procedures (D1). | A 3.12 procedure that imports `bob_killer.contracts`, builds a `Run`, and returns `sys.version`. |
| F3 | Procedure packages come from the Anaconda channel, or from PyPI through an artifact repository. | The import set must resolve for 3.12: `pydantic` 2.11.x, `pydantic-core`, `annotated-types`, `typing-extensions`, `typing-inspection`, `openpyxl`, `et-xmlfile`, `snowflake-snowpark-python`. Not `fastapi`. | `SELECT package_name, version FROM information_schema.packages WHERE language='python' AND runtime_version='3.12' AND package_name IN (...)`. If one is missing, prove the artifact-repository path. Record which path works. |
| F4 | Standard tables do not enforce PRIMARY KEY or UNIQUE, and have no CHECK constraints. They do enforce NOT NULL. | Enum and key rules live in code: strict models on write and on read, `MERGE` for upserts and dedup. | In a TEST_ schema: a duplicate PK insert succeeds; a NULL into NOT NULL fails. |
| F5 | A SiS app and an owner's-rights procedure run as the owner role; inside an owner's-rights procedure the current schema is the procedure's schema. | One role owns everything; tables are named without a schema, so one deployment = one schema (D7). | A procedure returns `CURRENT_SCHEMA()`. |
| F6 | `session.file.put_stream` compresses by default (`auto_compress=True`). | The app uploads with `auto_compress=False` and `overwrite=False`. | Put a fixture, list the stage, compare SHA-256 after `session.file.get_stream` inside a procedure. |
| F7 | A container-runtime app installs packages from PyPI, so it needs an external access integration. | The bootstrap SQL creates a network rule and integration for `pypi.org` and `files.pythonhosted.org`, unless the account has a Snowflake-provided one. | Deploy the hello app with and without the integration. Record what works. |
| F8 | `snow snowpark deploy` deploys what `snow snowpark build` made. Imports are zips or files on a stage. | Deploy = `snow snowpark build` then `snow snowpark deploy`. The core and host code ship as the build zip. | Run both; `DESCRIBE PROCEDURE` shows the imports. |
| F9 | Snowpark `session.call(name, *args, block=False)` returns an `AsyncJob`. | The app starts the run without blocking and polls tables. | Call a procedure with `block=False`; check `is_done()`. |
| F10 | `save_as_table` and other DDL commit implicitly. | Bronze writes use `INSERT … SELECT PARSE_JSON(...)` with bound values inside `BEGIN … COMMIT`, never DDL inside the transaction. | A live test (Phase 5). |

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
| `.../hosts/snowflake/procedure.py` | 3.12 | Handlers `create_run_handler`, `execute_run_handler`; idempotent `register_stages()` adds `land_bronze`, at import and at each handler entry (D4) |
| `src/bob_killer_sis/streamlit_app.py` | **3.11** | The app; never imports `bob_killer` (Phase 1 contract) |
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
2. The app calls `CREATE_RUN(stage_file, filename, sha256)` (blocking, short). The handler checks, in order:
   - `sha256` matches `^[0-9a-f]{64}$` and `stage_file == f"{sha256}.xlsx"` (G10). Else it returns
     `RunRejected(status=400, detail=…)` and reads nothing.
   - It reads the staged bytes with `session.file.get_stream` and computes their SHA-256. If the result is not
     `sha256`, it returns `RunRejected(status=400, detail="sha256 mismatch")`, removes `@UPLOADS/<sha256>.xlsx`
     by the bound path built from the checked `sha256`, and writes no `RUNS` row.
   - It calls core `create_run`. When the core rejects the file (`UploadRejected`), it returns `RunRejected`
     (413 or 415) and removes `@UPLOADS/<sha256>.xlsx` by the same bound path (G11).
   It returns a `RunCreated` (`run_id`, `state`) or a `RunRejected` (`status` 400, 413 or 415, `detail`).
   A rejection writes no run row and leaves no staged file. `.xlsm` is stored as `<sha>.xlsx` on purpose: the
   core checks the zip content, not the extension.
3. The app calls `EXECUTE_RUN(run_id)` with `block=False`, keeps the `AsyncJob` in `st.session_state`, and
   polls `RUNS` and `STAGE_STATUS` by `run_id` every 2 s until the run state is final or the job is done.
   When the job is done and the run state is not final, the app shows an error with the run id (G9c).
   The app shows "recent runs": the last 20 rows of `RUNS` by `_seq` descending, for all users, so a
   reload can find a run (G9b).
4. The `EXECUTE_RUN` handler calls `register_stages()` (D4), then core `execute_run(store, run_id) -> RunState`.
   - **Claim (G24).** Core `execute_run` first calls `store.claim_run(run_id)`, in place of the first
     `set_state(run_id, RUNNING)`. `claim_run` runs `UPDATE … SET state = 'running' WHERE run_id = ? AND
     state = 'queued'` and returns `True` when one row changed.
   - **Lost claim.** If the claim returns `False`, `execute_run` runs no stage and writes nothing. It reads
     `run = store.get_run(run_id)`, raises `KeyError(run_id)` when `run is None`, and else returns `run.state`.
     An error on this path propagates and writes nothing.
   - **Won claim (G9a).** The stage loop and the final `store.set_state(run_id, final)` are inside one `try`.
     The `except Exception` block calls `store.set_state(run_id, RunState.FAILED)` and re-raises. A stage error
     inside the loop does not change: it is recorded on the stage and gives `failed` with no raise.
   - **Handler.** The handler writes no run state. It never calls `claim_run` or `set_state`. After the core
     call it runs `run = store.get_run(run_id)`, raises `KeyError(run_id)` on `None`, and returns
     `RunView(run=run, stages=store.stages(run_id))`. It does not use the `RunState` return value.
   - **Landing.** `land_bronze(run_id)` resolves `run_id → sha256 → stage file`, then calls `BronzeWriter.land`.
     The writer runs, in order: `BEGIN`; `MERGE INTO LANDED_FILES …` on `file_sha256`; `after_claim()` if set;
     the `BRONZE_ROWS` batches of `batch_size` with `INSERT … SELECT PARSE_JSON(?) …`; `COMMIT`. It decides
     `landed` or `already landed` from the rows-inserted count of that `MERGE` only. It runs no `SELECT` on
     `LANDED_FILES` before the `MERGE`. If the `MERGE` inserted 0 rows, it writes no batch, runs `COMMIT`, and
     returns detail `already landed`. Any error: `ROLLBACK`, raise. `after_claim` is keyword-only and is a test
     seam for the concurrency live test. Production callers pass nothing.
   - **Parallel uploads (D5, G15).** Snowflake serializes the two `LANDED_FILES` `MERGE` statements, so parallel
     uploads land the rows once. The Phase 5 two-writer live test proves it and records, in
     `.context/evidence/parallel_landing_<date>.txt`, the `LANDED_FILES` and `BRONZE_ROWS` row counts for the sha
     and the result of each `land` call. On a failure:
     - **Case 1:** `LANDED_FILES` has 1 row and `BRONZE_ROWS` has more than N rows. The fallback applies, sent
       as the fix prompt: bronze rows go in with `MERGE INTO BRONZE_ROWS … ON (file_sha256, sheet, row_number)
       WHEN NOT MATCHED THEN INSERT`.
     - **Case 2:** `LANDED_FILES` has 2 rows. No fix prompt. Cadence hard stop `retries` with the reason
       "D5 false: Snowflake MERGE on LANDED_FILES does not serialize; see
       .context/evidence/parallel_landing_<date>.txt". The user makes a new design decision.
     - Any other failure is a normal §1.9 step 7 fix prompt. The test stays unchanged in all cases.
   - A landing holds one `LANDED_FILES` transaction from `BEGIN` to `COMMIT`. Snowflake can hold a table lock
     for the `MERGE` until `COMMIT`, so a landing of a different file can wait for the full landing time of a
     large file.
5. Every row the app reads is validated against the JSON Schema snapshot after the column names are
   lowercased. A failed row shows an error, not a crash. Every app query names its columns (no `SELECT *`), so
   `_seq` and `_written_at` do not come back (G7). The app converts `datetime` values with `isoformat()` before
   the check. It uses `jsonschema.Draft202012Validator` with no `FormatChecker`. `SnowflakeRunStore` also names
   its columns.

### 5.3 Boundary rules

- `bob_killer_sis` never imports `bob_killer` (import-linter, Phase 1).
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

Bronze row rules (G18):

- (a) Rows above the header row are ignored.
- (b) A **blank data row** is a row after the header row where every cell value is `None` or the empty string.
  It writes no bronze row. Excel row numbers do not shift.
- (c) `dtypes` is per row: for each column key, the openpyxl `data_type` of that row's cell. A blank cell has
  value `null` and dtype `n`.
- (d) `datetime` and `date` give ISO-8601 text, `time` gives `isoformat()` text, all with dtype `d`.
  `timedelta` gives `total_seconds()` as a float with dtype `d`.

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
| Service user | `BOB_KILLER_SVC`, `TYPE = SERVICE`, key-pair, default role `BOB_KILLER_OWNER`. **2026-10-16: CoCo also granted it ACCOUNTADMIN** (hackathon account). The build never uses it: no `bob_killer_admin` connection, AGENTS.md forbids admin roles. Revoke when not needed: `REVOKE ROLE ACCOUNTADMIN FROM USER BOB_KILLER_SVC;` |
| Account grant | `BIND SERVICE ENDPOINT` to `BOB_KILLER_OWNER` (container runtime) |

`hosts/snowflake/sql/00_admin_bootstrap.sql` creates the role, service user, warehouse, pool, database,
network rule (`PYPI_RULE`), integration (`BOB_KILLER_PYPI_EAI`) and grants. Applied 2026-10-16 as ACCOUNTADMIN.
The first run also made schemas `CORE` and `BRONZE`; D7 uses one schema per deployment, so `APP` replaces them
(`CREATE SCHEMA BOB_KILLER.APP`; drop `CORE` and `BRONZE` while they are empty). `99_teardown.sql <schema>` drops one deployment schema.

### 6.4 Live tests

A session fixture creates `TEST_<uuid8>`, deploys tables, stage and both procedures into it, runs the
tests, and drops the schema in teardown. Without a working connection the live suite **fails**; it never skips.
The CI `live` job skip (§1.6 item 7) is a workflow step condition, not a test skip.

- **Local runs.** Claude Code runs the live suite locally in §1.9 step 4, with `BK_EXPECTED_ROLE` exported as in
  §1.6. The output goes to `.context/evidence/live_phase<n>_<date>.txt`.
- **TEST_ sweep (Phase 2 owns it).** Before the session starts, the live session fixture calls the sweep in
  `src/bob_killer/hosts/snowflake/session.py`:
  - It runs `SELECT CURRENT_DATABASE()`. If the result is `NULL`, it drops nothing and logs
    `sweep skipped: no current database`.
  - Else it runs `SHOW SCHEMAS IN DATABASE "<db>"` and reads `name` and `created_on`. It never runs
    `SHOW SCHEMAS IN ACCOUNT`.
  - It selects a schema only when `name.startswith("TEST_")` in Python (no SQL `LIKE`) and `created_on` is more
    than 24 h before `datetime.now(UTC)`. A `created_on` value with no `tzinfo` raises `ValueError`.
  - It drops with `DROP SCHEMA IF EXISTS "<db>"."<schema>"`. The quoted-name builder doubles each `"` in both
    names. It logs each dropped name. It never touches a schema without the `TEST_` prefix.
- An interrupted run (local or CI) leaves a `TEST_` schema. The sweep drops it at the next live session.

---

## 7. Decisions

| ID | Question | Decision | Rejected |
| --- | --- | --- | --- |
| D1 | Where does the core run? | Two 3.12 owner's-rights procedures, `CREATE_RUN` and `EXECUTE_RUN`, in-process (core decision 7). | SPCS FastAPI service (infra with no load to justify it); backport to 3.11 (rewrites PEP 695 code). |
| D2 | Snowflake DDL | Dialect registry in `contracts/ddl.py`; SQLite output byte-identical; Snowflake set adds bronze models and dialect columns. If `contracts_versioned` reports a snapshot diff (for example, new schemas in `schemas.json`), bump `SCHEMA_VERSION` to 2; a test asserts `v2/ddl.sql == v1/ddl.sql`. | Hand-written SQL (second type definition). `StageStatus.ordinal` (changes SQLite DDL and every `StageStatus` call site). |
| D3 | Stage contract | `Stage = Callable[[str], str | None]`; `execute_run` writes the returned text as the success detail. Existing stages return `None` (detail `""`, unchanged). | A side channel for the detail. |
| D4 | Bronze placement | Stage `land_bronze`. `procedure.py` exposes an idempotent `register_stages()`; it runs at import and at each handler entry. It adds `land_bronze` only `if "land_bronze" not in registry.stages`. A context variable carries the session and config per call. A test asserts it is the first stage. | A step before `create_run` (no status, no run lineage). |
| D5 | Dedup | SHA-256, by `MERGE` inside a transaction (§5.2 step 4). | Filename; check-then-insert. |
| D6 | Bronze table type | Standard table, VARIANT. Iceberg is a later option. | Iceberg default (needs an external volume). |
| D7 | One schema per deployment | Unqualified table names; the procedure's schema decides. Test isolation is a TEST_ schema. | CORE/BRONZE split (procedures could not be pointed at test tables). |
| D8 | App ↔ contracts | JSON Schema snapshot copy, identity-tested. | Import (impossible on 3.11); copy models. |
| D9 | Code home | New repo `bob-killer-snowflake`. The core is imported at `labs/bob_killer/` with its git history (`git subtree split` from sandbox `40987f0`), so paths, gates and CI work unchanged. Host code goes in the core's `src/` and `tests/`. | Stay in sandbox (the user asked for a new repo); separate host distribution (every gate hard-codes core paths). |
| D10 | Excel reader | openpyxl `read_only=True, data_only=True`, in the `snowflake` extra. | pandas (forbidden); Polars `read_excel` (adds fastexcel). |
| D12 | Live tests in CI | **This run needs no CI secret.** The live suite runs locally in Claude Code's §1.9 step 4 after each phase (connection `bob_killer` on this Mac); its output is evidence in `.context/evidence/`. CI always runs the offline suite (fake sessions and the stub). The CI `live` job is automatic: it runs on pushes and PRs **when** the `SNOWFLAKE_*` secrets exist, and otherwise skips with a notice that names `tools/setup-ci-secrets.sh`. Anyone sets the secrets with `tools/setup-ci-secrets.sh [--connection NAME] [--dry-run]`: it reads a key-pair connection from `~/.snowflake/connections.toml`, pipes the key to `gh secret set` on stdin, sets the variables, and refuses when the Snowflake user holds an admin role unless `--accept-admin-risk`. The `live` job is never a required check in this run, and missing secrets are never a hard stop. | Key as a required CI secret now (full account control in a public repo's Actions while the grant exists); hard stop on missing secrets (ends the run in Phase 1). |
| D13 | Data contracts (ODCS) | The Snowflake tables get an **Open Data Contract Standard v3.2.0** contract, generated from the Pydantic contracts and the `snowflake` DDL dialect (one type definition, D2/decision 8). `bob_killer.hosts.snowflake.odcs` writes `hosts/snowflake/contracts/bob_killer_app.odcs.yaml`: `apiVersion: v3.2.0`, `kind: DataContract`, one `servers` entry (`type: snowflake`, database `BOB_KILLER`, schema `APP`; account taken from no file), one `schema` object per table in `SNOWFLAKE_TABLES` with `physicalName`, and per property `logicalType`, `physicalType` (from the dialect), `required`, `primaryKey`/`primaryKeyPosition`, and `description`. Nested models (`BronzePayload`) become `logicalType: object` with their own `properties`. Dialect columns `_seq` and `_written_at` are listed. Tests: the generated file validates against the vendored `tests/oracle/odcs-json-schema-v3.2.0.json` (pinned SHA-256 in `tests/oracle/odcs_schema.source.json`); one parametrized test per table and property checks the ODCS property against the model field; the committed YAML is a drift guard. A contract change without a regenerated YAML fails. | Hand-written ODCS YAML (a second type definition); datacontract-cli as a runtime dependency (heavy; only the JSON Schema is needed to validate). |
| D14 | dbt output target | A `dbt` generator registered in `registry.generators` (core extension point) renders the IR into a dbt project: `sources` = the run's IR tables and bronze; **seeds** = lookup tables and the parity oracle (cached values); **dbt vars** = promoted parameters; **models** = steps in topological order (`scalar_expr`/`column_expr` with exact SQL semantics → SQL models; reductions, rounding, dates, coercion → calls to Python UDFs built from `runtime/`); **marts** = outputs; **dbt tests** = exact-equality parity tests against the oracle seed, plus not-null/unique from the IR. The project deploys with `snow dbt deploy` / `CREATE DBT PROJECT` and runs with `EXECUTE DBT PROJECT` (dbt Projects on Snowflake). The generator is template-driven (Jinja partials, core DRY rules). | A SQL re-implementation of Excel semantics (breaks exact parity); dbt Core outside Snowflake (the goal is dbt in Snowflake). |
| D15 | Parity oracle | Cached values from Excel-saved golden workbooks are the oracle for their one input set; the comparator is `verify/config.py` (exact). New input sets need the external Excel oracle (out of scope); the report lists them as unverified, never approximated. | LibreOffice recalculation (never an oracle, core decision 1). |
| D16 | Where the compiler runs | Extract, graph, lift, generate and verify are registered stages that run inside `EXECUTE_RUN` (3.12 procedure). `workbook.db` (core decision 9) becomes the run's tables in the deployment schema through the `RunRepository`/dialect pattern of Phases 3–4. Generated dbt files are written to a stage and deployed from it. Long runs: if a stage exceeds the procedure limit, split per stage into separate procedure calls (Phase 9 measures it). `oletools` (VBA) must resolve (F3 pattern); if not, VBA inventory runs from a vendored pure-Python reader or the run stops blocked. | Running the compiler only on the Mac (the goal is Snowflake). |
| D11 | Mutation scope | Phase 1 adds `src/bob_killer/service/`, `src/bob_killer/store/` and `src/bob_killer/hosts/snowflake/` to `[tool.mutmut] paths_to_mutate` (test selection stays `tests/unit`, offline, fake sessions; `session.py` live I/O may be excluded with `do_not_mutate`). After Phase 6, `gates.py --only mutation` runs once and its kill rate goes to `.context/evidence/mutation_phase6_<date>.txt` (P7 F3). | Core mutation on `runtime/` only (this run's new logic would have no mutation gate). |

---

## 8. Execution plan

Each phase ends with its exit criteria met and `uv run python scripts/gates.py --base <run-base-sha>` green.
Do the phases in order. "Allowed paths" are relative to `labs/bob_killer/`, plus `.context/runs/` and
`.context/evidence/` at the repo root.

### Phase 1: Gate and dependency prep

Done by Claude Code itself, not CoCo. Allowed paths: `scripts/hook_stop.py`, `../../tools/`, `pyproject.toml`, `uv.lock`, `scripts/bk_gates/`,
`tests/gates/`, `tests/live/test_connection.py`, `tests/live/conftest.py`, `src/bob_killer/hosts/__init__.py`,
`src/bob_killer/hosts/snowflake/__init__.py`, `src/bob_killer_sis/__init__.py`, `src/bob_killer_sis/ruff.toml`,
`src/bob_killer_sis/pyproject.toml` (G21), `tests/oracle/odcs-json-schema-v3.2.0.json`,
`tests/oracle/odcs_schema.source.json` (D13), `../../.github/workflows/bob-killer.yml`, `../../.gitignore`,
`../../docs/SPEC.md`. Phase 1 is the only phase that may touch `src/bob_killer_sis/ruff.toml` and
`src/bob_killer_sis/pyproject.toml`. `tools/setup-ci-secrets.sh` is not changed.

- Every item of §1.6, as `TDD-Phase: gate-change` commits (the gate tests in item 8 first, each red before its
  gate change: `uv run python scripts/record_run.py --phase red tests/gates/<file>`).
- `tests/live/conftest.py` has only the connection and session setup. No TEST_ sweep in Phase 1.
- (P7 F3) `[tool.mutmut] paths_to_mutate` adds `src/bob_killer/service/`, `src/bob_killer/store/`,
  `src/bob_killer/hosts/snowflake/` (D11); test selection stays `tests/unit`.
- `tools/coco-guard`: tolerate and archive the hook output named in §1.2 control 3.
- One probe CoCo call in a throwaway clone: one `edit` of a test file. Record whether `PostToolUse` fired
  (a `.context/runs/<id>/hook-run.json` appears) in `.context/evidence/coco_hooks_<date>.txt`.
- Spec r8: commit this file with subject `docs: spec r8 folds plan settled decisions` and trailer
  `TDD-Phase: scaffold`.
- Trace check, after the close and before the first Phase 2 prompt: Claude Code writes
  `.context/evidence/spec_r8_trace_<date>.md` with one row per settled item and its r8 section and line, and a
  section "Replaced text, must be absent" with a `grep -n` count of 0 for each replaced phrase. A missing row or
  a count above 0 stops E1 before Phase 2. Claude Code fixes this file first. No CoCo call runs on a spec that
  fails this check.
- Exit: §1.6 exit.

### Phase 2: Platform proof

Allowed paths: `hosts/snowflake/` (with `hosts/snowflake/hello_app/`), `src/bob_killer/hosts/snowflake/session.py`, `tests/live/test_platform.py`, `tests/live/conftest.py`, `tests/unit/hosts/test_session.py`, `tests/fakes/`, `.context/evidence/`.

- The bootstrap is already applied (Step 0b, in a CoCo Snowsight session; its text is not on disk). Write
  `hosts/snowflake/sql/00_admin_bootstrap.sql` from §6.3, with the header line `-- RECONSTRUCTED from docs/SPEC.md §6.3;
  applied 2026-10-16`, a placeholder for the public key body, and no ACCOUNTADMIN grant to `BOB_KILLER_SVC`. Do not
  run it. Write `99_teardown.sql <schema>`. If the `BOB_KILLER_OWNER` role is missing, stop with status blocked.
- Red first: tests import `bob_killer.hosts.snowflake.session` (not yet written), so they fail for a stated
  reason. Green: `session.py` with `open_session(connection_name)` and the `test_schema()` context manager
  (create `TEST_<uuid8>`, yield, drop). The F2, F4, F5, F6, F9 checks are live tests that use them.
- (P7 F2) Create the one shared fake: `tests/fakes/snowpark.py` with `FakeSession`. It records `(sql, params)` in
  order, returns scripted results keyed by a statement prefix, and exposes the rows-affected value (MERGE rows
  inserted, UPDATE rows updated). Phases 4–7 **extend** this class; they never write a second fake.
- **TEST_ sweep.** Phase 2 is the only owner. The logic is in `session.py`; `tests/live/conftest.py` calls it
  before the live session starts. The rules are in §6.4:
  - `SELECT CURRENT_DATABASE()`. A `NULL` result drops nothing and logs `sweep skipped: no current database`.
  - Else `SHOW SCHEMAS IN DATABASE "<db>"`, columns `name` and `created_on`. Never `IN ACCOUNT`.
  - Select by `name.startswith("TEST_")` in Python (no SQL `LIKE`) and `created_on` more than 24 h before
    `datetime.now(UTC)`. A `created_on` with no `tzinfo` raises `ValueError`.
  - Drop with `DROP SCHEMA IF EXISTS "<db>"."<schema>"`. The quoted-name builder doubles each `"`. Log each name.
  - Red first, in `tests/unit/hosts/test_session.py` with `FakeSession`: the prefix rule and the age rule;
    `TESTX_OLD` older than 24 h is kept; no statement contains `IN ACCOUNT`; each `DROP` has the quoted
    `"<db>"."<schema>"` form; `CURRENT_DATABASE()` is `NULL` gives no `SHOW` and no `DROP`; `created_on` values in
    UTC and in UTC-08:00, one older and one newer than 24 h, drop only the older; `TEST_A"B` older than 24 h gives
    `DROP SCHEMA IF EXISTS "<db>"."TEST_A""B"`; a `created_on` with no `tzinfo` raises `ValueError`.
- Evidence for F1, F3, F7, F8: the commands and outputs in `.context/evidence/snowflake_platform_<date>.md`.
  - F3 records which package path works for 3.12 (Anaconda channel or artifact repository).
  - F8 uses the real packing layout (G13): `hosts/snowflake/snowflake.yml` packs `../../src/bob_killer` with an
    artifact `src`/`dest` mapping. The evidence records the exact `snowflake.yml` that works. Wheels bundled from
    the Mac are forbidden. If no layout and no package path works, stop blocked.
- **Hello app** (F1, F7): a throwaway probe in `hosts/snowflake/hello_app/` with `streamlit_app.py` and its own
  `pyproject.toml`. It deploys with the container runtime, the compute pool and the PyPI integration into a
  `TEST_<uuid8>` schema. `99_teardown.sql <schema>` drops it. After the `DESCRIBE STREAMLIT` check, the test runs
  `ALTER COMPUTE POOL <pool> SUSPEND`, or the evidence shows `AUTO_SUSPEND_SECS` of 600 or less. It is outside
  `src/`, so `types_lint` and `coverage` do not read it. No later phase imports it. Phase 8 does not document it.

Exit: F2–F6, F8 and F9 are confirmed by live tests or evidence. F1 and F7 are confirmed at deploy level: a hello
  app deploys with the container runtime, the compute pool and the PyPI integration, and `DESCRIBE STREAMLIT` shows
  them (a container app starts only when a person opens it; the runtime check is in the post-merge step of Phase 7).
  F10 is proven in Phase 5. A false fact stops the phase blocked, with the fact named. The offline suite and the
  gates pass. The local live run passes (`.context/evidence/live_phase2_<date>.txt`).

### Phase 3: Contracts and DDL dialects

Allowed paths: `src/bob_killer/contracts/`, `src/bob_killer/hosts/__init__.py`, `src/bob_killer/hosts/snowflake/__init__.py`, `src/bob_killer/hosts/snowflake/ddl.py`, `tests/unit/`, `hosts/snowflake/sql/10_tables.sql`. Also `tests/oracle/snowflake_types.json` (P7 F1 oracle; settled 2026-10-16).

- Red: `ddl_dialects["sqlite"]` output for `TABLES` equals `snapshots/v1/ddl.sql`, read from the file.
- Green: refactor `ddl.py` into the registry. No output change.
- Red/green: strict-model tests for `BronzePayload`, `LandedFile`, `BronzeRow`, and `RunRejected(status: int, detail: str)`
  in `contracts/runs.py` (wrong type, extra key rejected). `RunRejected.status` is 400, 413 or 415 (§5.2 step 2).
  `CREATE_RUN` returns `RunCreated` or `RunRejected`; `EXECUTE_RUN` returns `RunView`. All three are in
  `schemas.json`, so Phase 6 adds no contract.
- (P7 F1) Red/green: one parametrized test per §6.2 type-map row, expected Snowflake type read from
  `tests/oracle/snowflake_types.json` (`source: docs/SPEC.md §6.2`, `verified_by`), plus asserts for `NOT NULL`, the
  informational PK, `_seq` and `_written_at`. The golden file below is a drift guard only, never the oracle.
- Red/green: the `snowflake` dialect; an unmapped type raises `TypeError`; golden test against
  `hosts/snowflake/sql/10_tables.sql`, generated by `uv run python -m bob_killer.hosts.snowflake.ddl`.
- (D13) Red/green: `bob_killer.hosts.snowflake.odcs` builds the ODCS v3.2.0 contract from `SNOWFLAKE_TABLES` and the
  `snowflake` dialect; it validates against `tests/oracle/odcs-json-schema-v3.2.0.json`; one parametrized test per
  table and property; golden `hosts/snowflake/contracts/bob_killer_app.odcs.yaml`, regenerated by
  `uv run python -m bob_killer.hosts.snowflake.odcs`. Allowed paths add `src/bob_killer/hosts/snowflake/odcs.py`
  and `hosts/snowflake/contracts/`.
- Run `uv run python scripts/gates.py --only contracts_versioned`. On a diff: bump `SCHEMA_VERSION` to 2, run
  `scripts/export_contracts.py`, add the `v2/ddl.sql == v1/ddl.sql` test.

Exit: SQLite DDL unchanged; `contracts_versioned` green; `RunCreated`, `RunRejected` and `RunView` are in `schemas.json`.

### Phase 4: Repository Protocol, stage detail, SnowflakeRunStore

Allowed paths: `src/bob_killer/store/`, `src/bob_killer/service/runs.py`, `src/bob_killer/registry.py`, `src/bob_killer/api/main.py`, `src/bob_killer/cli.py`, `src/bob_killer/hosts/snowflake/store.py`, `tests/conftest.py`, `tests/unit/`, `tests/integration/`, `tests/live/`.

- Red: a shared `RunRepository` suite that takes a store factory: insert; get missing → `None`; `set_state`;
  upsert twice → one row; stages in insert order after `create_run` + `execute_run`; a failed stage keeps the
  registry order (G8); two `claim_run` calls on one queued run give `True` then `False` (G24).
- Green: extract the Protocol, with `claim_run(run_id) -> bool`. Type `service/runs.py` against it. In `cli.py`
  and `api/main.py` change only the store type hint. The suite runs on `RunStore`.
- Green (G8): the SQLite upsert changes from `INSERT OR REPLACE` to
  `INSERT … ON CONFLICT(run_id, stage) DO UPDATE SET state, detail`, which keeps the `rowid`. The DDL does not change.
- Green (G24): `RunStore.claim_run` runs `UPDATE runs SET state = 'running' WHERE run_id = ? AND state = 'queued'`
  and returns `rowcount == 1`.
- Red/green (D3): a stage that returns `"x"` gets detail `"x"`; a stage that returns `None` gets `""`.
- Red/green (G1): `Registry.snapshot()` returns a context manager that saves the entries on entry and restores them
  on exit. `Registry.clear()` removes all entries. Tests in `tests/unit/test_registry.py`: `snapshot()` restores an
  entry added inside the block and an entry removed inside the block; `clear()` empties the registry; `len()` is 0
  after `clear()`.
- Fixture (G1): the `tests/conftest.py` autouse fixture runs
  `with registry.stages.snapshot(): registry.stages.clear(); yield`. Each test starts with an empty
  `registry.stages` (the core baseline). Keep the existing builders in `tests/conftest.py`.
- Collection-order regression test (G1): a new file `tests/unit/test_registry_isolation.py` calls
  `registry.stages.add("_import_probe", lambda run_id: None)` at module level. Its test asserts
  `"_import_probe" not in registry.stages` and `len(registry.stages) == 0`.
- Core `execute_run(store, run_id) -> RunState` (G24, G9a), as in §5.2 step 4. It keeps its signature and
  return type. CoCo must not change the return type.
  - It calls `store.claim_run(run_id)` first, in place of the first `store.set_state(run_id, RunState.RUNNING)`.
  - Lost claim: no stage, no write; `run = store.get_run(run_id)`; `KeyError(run_id)` when `run is None`; else
    return `run.state`. No G9a `try` on this path.
  - Won claim: the stage loop and the final `set_state` are inside one `try`. `except Exception`:
    `store.set_state(run_id, RunState.FAILED)`, then re-raise. The stage-error path inside the loop does not change.
- Red/green (G24), SQLite store: `create_run`, then `execute_run` two times on one run. The first call returns
  `RunState.SUCCEEDED`. The second call returns `RunState.SUCCEEDED` (the stored state), runs no stage (a counting
  stage registered in the test is called one time only), and `store.stages(run_id)` is equal before and after it.
  A second test: `execute_run(store, "missing")` raises `KeyError`.
- Red/green (G9a), SQLite store, in `tests/unit/`:
  - (a) A store wrapper whose `upsert_stage` raises `RuntimeError` after the claim, with one counting stage.
    `execute_run` re-raises `RuntimeError`, and `store.get_run(run_id).state` is `RunState.FAILED`.
  - (b) `create_run`, then `execute_run` (returns `SUCCEEDED`). Then a second `execute_run` with a store wrapper
    whose `get_run` raises `RuntimeError`. The call re-raises, and the plain store still reads `RunState.SUCCEEDED`.
  - (c) A store wrapper whose final `set_state(run_id, SUCCEEDED)` raises. `execute_run` re-raises, and the stored
    state is `FAILED`.
- Red/green: `SnowflakeRunStore(session)` with `FakeSession`: SQL text, binds, MERGE shape, named columns with no
  `SELECT *` (G7), and read validation (a bad enum value from the database raises). `claim_run` sends exactly one
  `UPDATE … SET state = 'running' WHERE run_id = ? AND state = 'queued'`, reads the rows-updated count, and sends
  no `BEGIN`, `COMMIT` or `ROLLBACK`.
- Live: the shared suite on `SnowflakeRunStore` in a `TEST_<uuid8>` schema.
- Live overlap test for `claim_run`, in `tests/live/`, one `queued` run, one `threading.Barrier(2)`, two Snowpark
  sessions (one per thread). Claim first in A, then the barrier:
  - Session A: `BEGIN`; `a = store_a.claim_run(run_id)`; `barrier.wait()`; sleep 5 s; record `t_commit`; `COMMIT`.
  - Session B: `ALTER SESSION SET LOCK_TIMEOUT = 60`; `barrier.wait()`; `b = store_b.claim_run(run_id)`; record
    `t_b_end`.
  - Assert `a is True`, `b is False`, `t_b_end >= t_commit`, and the stored state is `running`.
  - Join both threads with `join(timeout=120)`. A thread still alive fails the test with
    `overlap test exceeded 120 s`. A lock timeout error on B fails the test; its text goes to the evidence file.
  - `b is True`: no fix prompt. Run `activate_session.py --hard-stop retries --reason "claim_run does not serialize"`.
  - `b is False` and `t_b_end < t_commit`: the test fails. Record the timings in
    `.context/evidence/live_phase4_<date>.txt`. Phase 4 stops `blocked` with the timings. No fix prompt.
- `tests/integration/test_cli.py` and `tests/integration/test_api.py` do not change and pass unchanged.

Exit: the shared suite is green on both stores, offline and live; coverage ≥ 90%;
`uv run pytest -q tests/unit tests/integration/test_api.py` passes in one process; the local live run passes
(`.context/evidence/live_phase4_<date>.txt`).

### Phase 5: Bronze landing

Allowed paths: `src/bob_killer/hosts/snowflake/bronze.py`, `tests/unit/`, `tests/live/`, `tests/fixtures/workbooks/bronze_*.xlsx`, `tests/fixtures/make_bronze_fixtures.py`, `tests/oracle/`.

- Bronze reads literal cell values only, so its fixtures hold **no formulas** and need no Excel cached values.
  A committed script `tests/fixtures/make_bronze_fixtures.py` writes them with openpyxl: two sheets; blanks; an
  error value (`#DIV/0!` as data type `e`); a date; a time; duplicate and blank headers; rows above the header; a
  fully blank row; an empty sheet. The script is the source of truth; a test regenerates each fixture and compares
  bytes of the cell XML. Expected values come from `tests/oracle/bronze_*.json` with `source` and `verified_by`.
  No literal expected values. (Formula fixtures for the compiler stages still need real Excel; that is core work.)
- Red/green: `rows_from_workbook`: all sheets, Excel row numbers, header rules, the G18 rules (a) to (d) of §6.1,
  dtypes, nulls, errors, empty sheet → no rows.
- Red/green: `BronzeWriter` with `FakeSession`: MERGE then batches (batch size 2 in the test), bound values,
  `ROLLBACK` on error.
- `BronzeWriter.land(..., *, after_claim: Callable[[], None] | None = None)`. The docstring says: "after_claim is a
  test seam for the concurrency live test; production callers pass nothing." The order is `BEGIN`, the
  `LANDED_FILES` `MERGE`, `after_claim()` if set, the bronze batches, `COMMIT` (§5.2 step 4). The writer decides
  `landed` or `already landed` from the rows-inserted count of that `MERGE` only, with no `SELECT` before it.
  - Unit test: the recorded call order is `BEGIN`, `MERGE`, hook, batches, `COMMIT`.
  - Unit test: a `MERGE` that reports 0 rows inserted gives `already landed`, no bronze batch, and `COMMIT`.
- (P7 F1) Every live landing test asserts the exact `BRONZE_ROWS` count for the file SHA-256, read from
  `tests/oracle/bronze_*.json`, and the fault-injection test asserts zero rows in **both** `LANDED_FILES` and `BRONZE_ROWS`.
- Live: first landing writes rows; second landing of the same bytes writes zero and returns `already landed`; a
  writer that raises after batch 1 leaves zero rows.
- Live two-writer test, in a `TEST_<uuid8>` schema, on one generated workbook:
  - Session A calls `land` with `after_claim` that waits on a `threading.Barrier(2)` and then sleeps 5 s.
  - Session B, in a second thread, waits on the same barrier and then calls `land` on the same bytes with no hook.
  - Assert: exactly one call returns `landed` and one returns `already landed`; `LANDED_FILES` has 1 row for the
    sha; `BRONZE_ROWS` has N rows for the sha, with N from `tests/oracle/`; B's `land` ends at or after A's `COMMIT`.
  - `.context/evidence/parallel_landing_<date>.txt` records the start and end time of each statement in each
    session, the `LANDED_FILES` and `BRONZE_ROWS` row counts for the sha, and the result of each `land` call.
  - On a failure, Claude Code reads that file and applies the G15 cases of §5.2 step 4: case 1 gets the bronze
    `MERGE` fallback as the fix prompt; case 2 is hard stop `retries` with no fix prompt; any other failure is a
    normal fix prompt. The test stays unchanged.
- Live batch size (G14): `batch_size` defaults to 10 000. A live test lands a generated 30 000-row workbook (made in
  the test, not `sample.xlsx`) with the default. If the default fails on a Snowflake limit, the fix prompt halves
  the default (10 000, 5 000, 2 500, 1 250, 625, then the floor 500) until the test passes. If 500 fails, Phase 5
  stops `blocked` with the error. The test records the landing time (start, end, seconds) in
  `.context/evidence/live_phase5_<date>.txt`. No assert on the time.

Exit: offline and live suites green. The evidence records each batch-size try and its result, and the landing
time. The local live run output is in `.context/evidence/live_phase5_<date>.txt`.

### Phase 6: Procedures and deployment

Allowed paths: `src/bob_killer/hosts/snowflake/procedure.py`, `hosts/snowflake/snowflake.yml`, `hosts/snowflake/sql/`, `tests/unit/`, `tests/live/`, `tests/fixtures/workbooks/`.

- **Registration (D4, G1).** `procedure.py` defines `register_stages() -> None`. It adds `land_bronze` only if
  `"land_bronze" not in registry.stages`. `procedure.py` calls it at import. `create_run_handler` and
  `execute_run_handler` call it at entry, before the core call. Host tests in `tests/unit/hosts/` may import
  `procedure.py` at the top of the file. Each test that needs `land_bronze` uses a fixture that calls
  `register_stages()`.
- **`EXECUTE_RUN` handler (G24, G9a).** Call core `execute_run(store, run_id)`. Then `run = store.get_run(run_id)`;
  if `run is None`, raise `KeyError(run_id)`; return `RunView(run=run, stages=store.stages(run_id))` (the
  `api/main.py:53-56` pattern). The handler does not call `claim_run` or `set_state` and has no G9a code. A
  `KeyError` from the core call (no such run) propagates and writes no row.
- Red/green with `FakeSession`:
  - a bad `sha256` or a `stage_file` that is not `f"{sha256}.xlsx"` gives `RunRejected` 400 and reads nothing (G10)
  - staged bytes whose SHA-256 is not `sha256` give `RunRejected` 400 with detail `sha256 mismatch`, one `REMOVE`
    on the bound path, and no `RUNS` insert (G10)
  - `UploadRejected` gives `RunRejected` and one `REMOVE` of `@UPLOADS/<sha256>.xlsx` on the bound path (G11). The
    51 MB and zip-bomb inputs are generated in the test, in `tmp_path`, and are not committed.
  - with the `register_stages()` fixture, `land_bronze` is the first stage
  - `register_stages()` called two times gives `registry.stages.names() == ("land_bronze",)` and no error
  - G9a: `store.stages(run_id)` raises after the core `execute_run` call returns. The error propagates from
    `execute_run_handler`, and the fake session receives no `UPDATE` on `RUNS` after the core call.
  - G24: `EXECUTE_RUN` on a run that is not `queued` runs no stage and returns the stored `RunView`
  - a missing run raises `KeyError`
  - the returned JSON validates against `schemas.json`.
- `snowflake.yml` for both procedures: runtime 3.12, packages per the F3 evidence (no wheels bundled from the Mac),
  the build zip as import, the packing layout from the F8 evidence (G13).
- Live: deploy into a `TEST_<uuid8>` schema with `uv run --project ../.. snow snowpark build` and
  `snow snowpark deploy`; `CREATE_RUN` then `EXECUTE_RUN` on a staged fixture → `succeeded` with the exact
  `BRONZE_ROWS` count from `tests/oracle/` (P7 F1).
- Live rejections: `.xls` → 415, a generated zip bomb → 413, a generated 51 MB file → 413, and wrong bytes
  `PUT` as `@UPLOADS/<sha>.xlsx` → 400. Each rejection writes no `RUNS` row for the sha, and `LIST @UPLOADS`
  shows no file for the sha. The 415 output is the evidence for the `.xls` §2.4 signal (G12).
- (D11) After the close, `gates.py --only mutation` runs once; the kill rate goes to
  `.context/evidence/mutation_phase6_<date>.txt`.

Exit: one build and deploy command pair deploys to any schema; the local live run passes
(`.context/evidence/live_phase6_<date>.txt`); `uv run pytest -q tests/unit/hosts tests/integration/test_api.py`
passes in one process; Claude Code tags the close commit `deploy/6-<short-sha>`.

### Phase 7: Streamlit app

Allowed paths: `src/bob_killer_sis/` except `src/bob_killer_sis/pyproject.toml` and `src/bob_killer_sis/ruff.toml`, `hosts/snowflake/snowflake.yml`, `tests/unit/sis/`, `tests/live/`.
Both excluded files are on the control 6 list. The §1.9 step 3 check rejects a commit that touches either. CoCo
may not change the dependency list of the app (G21).

- `streamlit_app.py` does these things:
  - upload (`.xlsx`, `.xlsm`, many files; G12)
  - preview the first 5 rows per sheet with openpyxl
  - compute the SHA-256
  - `put_stream` with `auto_compress=False` and `overwrite=False`
  - call `CREATE_RUN`, then `EXECUTE_RUN` with `block=False`
  - poll every 2 s and show the run and its stages
  - show the `rejected` message
  - show "recent runs": the last 20 rows of `RUNS` by `_seq` descending, for all users (G9b). The label says
    "recent runs".
  - when the `AsyncJob` is done and the run state is not final, show an error with the run id (G9c).
- Every query names its columns (no `SELECT *`). `datetime` values go through `isoformat()` before the JSON Schema
  check. The check uses `jsonschema.Draft202012Validator` with no `FormatChecker` (G7).
- AppTest with an injected fake session: stage path, bound args, rejected message, a row that fails JSON Schema
  shows an error, a converted timestamp row passes, the recent-runs list, and the stuck-run message.
- Test: `src/bob_killer_sis/schemas.json` equals the core snapshot file byte for byte.
- `snowflake.yml` app entry: container runtime, compute pool, the PyPI integration (F7), `streamlit>=1.50`.
- Live: `snow streamlit deploy` into a `TEST_<uuid8>` schema. Then the G22 check: `snow streamlit get-url` returns a
  URL, and `DESCRIBE STREAMLIT` shows the object, the compute pool and the integration.

Exit: deploy works in a TEST_ schema. The 3.11 `compileall` and mypy steps pass. Coverage includes
`src/bob_killer_sis` and stays ≥ 90%. The local live run passes (`.context/evidence/live_phase7_<date>.txt`).
Claude Code tags the close commit `deploy/7-<short-sha>`. After the merge, you deploy to `APP`, open the app,
check the §2.4 signals and the F1 runtime (`sys.version`, role); the query outputs go to `.context/evidence/`.

### Phase 8: Docs

Allowed paths: `hosts/snowflake/README.md`, `README.md` (the bob_killer one).

- Setup, bootstrap, deploy, teardown, rollback (§11), the donor payload mapping: old `metadata.dtypes`
  held Python class names per cell (`int`, `float`, `str`, `bool`, `Timestamp`, `Timedelta`, `NoneType`); new
  `dtypes` hold openpyxl codes (`n`, `s`, `b`, `d`, `e`) per row (G18c). The old `data.id` (DataFrame index) is
  gone; use `(file_sha256, sheet, row_number)`.
- The `.xls` note (G12): the app accepts `.xlsx` and `.xlsm`. The procedure rejects `.xls` with 415. The README
  names the evidence for this §2.4 signal: the Phase 6 live test output for the 415, and one direct
  `CALL CREATE_RUN` in `APP` after the merge, with its output in `.context/evidence/xls_415_app_<date>.txt`.
- The ACCOUNTADMIN revoke line (§6.3).
- A section "Stuck runs":
  - A procedure that a statement timeout or a warehouse suspend kills cannot run the G9a `except` path in core
    `execute_run`, so the run stays `running`. G24 makes a second `EXECUTE_RUN` on that run do nothing.
  - If the app stops between `CREATE_RUN` and `EXECUTE_RUN`, the run stays `queued`. "Recent runs" shows it. No
    path starts it.
  - Recovery in both cases is manual: upload the file again. The new run gets a new `run_id`. `land_bronze`
    returns `already landed` only if the first landing committed. No code change.
- A section "Concurrent landings": each landing holds one `LANDED_FILES` transaction from `BEGIN` to `COMMIT`
  (§5.2 step 4). Snowflake can hold a table-level lock for the `MERGE` until `COMMIT`. A landing of a different
  file can wait for the full landing time of a large file. The Phase 5 evidence file gives the measured 30 000-row
  landing time.
- The Phase 2 hello app is not a deploy path and is not documented.
- A separate PR to the donor repo adds a README pointer. Claude Code opens it, not CoCo.

Exit: in the §1.9 step 4 checks, Claude Code follows the README in the clone to deploy into a new `TEST_<uuid8>`
schema, runs one upload by `CREATE_RUN` and `EXECUTE_RUN`, then runs `99_teardown.sql`. The output goes to
`.context/evidence/readme_deploy_<date>.txt`.

---

## 9. Gates and how CoCo works under them

- **CoCo runs the core's hooks.** With `-w labs/bob_killer`, CoCo loads `labs/bob_killer/.claude/settings.json`.
  The `Stop` hook refused CoCo's stop while a gate failed (seen 2026-10-16). Whether `PostToolUse` fires is not
  proven: its matcher is `Edit|Write|MultiEdit` and CoCo's tool names are lowercase. Phase 1 probes it with one
  real CoCo edit and records the result; `clone-check` tolerates the hook output either way. That is wanted. It needs a base: `tools/coco-clone` makes a local `main` in the clone. The hooks
  append to the clone's `.context/hooks.log`, which Claude Code archives (§1.9).
- For Claude Code, those hooks load only when it starts in `labs/bob_killer/`; this run starts at the repo
  root. Claude Code edits `src/` or `tests/` only in Phase 1 (gate tests). The controls are §1.2. Do not touch `.context/hooks.log`; only Claude Code hooks append to it.
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
4. No pandas and no password in any repo file. No file under `labs/bob_killer/src/`, `labs/bob_killer/tests/` or
   `tools/`, and no connection config, names an admin role. Only `hosts/snowflake/sql/00_admin_bootstrap.sql` and
   docs may name one, and the committed bootstrap does not grant ACCOUNTADMIN to `BOB_KILLER_SVC`.
5. One documented deploy path for procedures and app; one teardown script.

---

## 11. Risks and rollback

| Risk | Mitigation |
| --- | --- |
| pydantic 2.11 not on the Anaconda channel for 3.12 | F3 proves the artifact-repository path. If neither works, stop. |
| Procedure run time for later compiler stages | Record the limit in Phase 2 evidence for core planning. |
| Idle compute pool cost | Auto-suspend in the bootstrap. |
| No PK/UNIQUE/CHECK enforcement (F4) | Strict models on write and read; MERGE; live tests that write bad rows by raw SQL. |
| CoCo acts outside its phase | §1.2 controls; hard stop `security`. |
| `BOB_KILLER_SVC` holds ACCOUNTADMIN (checked 2026-10-16: grants `ACCOUNTADMIN`, `BOB_KILLER_OWNER`) and CoCo has a SQL tool | **Accepted risk until you revoke it.** Only the AGENTS.md rule stops `USE ROLE ACCOUNTADMIN`. The §1.2 controls guard the Mac, not the account. Revoke: `REVOKE ROLE ACCOUNTADMIN FROM USER BOB_KILLER_SVC;` |
| Generated apps (core Phase 7) must run on 3.11 | Out of scope. Phase 2 evidence feeds a core ticket. |
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
| GitHub remote | Public `github.com/jtouley/bob-killer-snowflake` (created 2026-10-16); evidence files redact the account id |
| Run branch | `snowflake-host` from `main`; Phase 1 is its first phase |
| `CORE` / `BRONZE` schemas from the first bootstrap | Done 2026-10-16: `APP` exists; `CORE` and `BRONZE` are dropped |

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
| NTH Phase 2 red impossible | Phase 2 tests red against `session.py` |
| NTH red records for live tests | AGENTS.md: `record_run.py --phase red -- -m live` |
| NTH `.context` paths ambiguous | AGENTS.md names `../../.context/` |
| NTH old Cadence files | Moved to `docs/history/sandbox-gh-5/` |
| NTH CoCo self-update | `tools/coco-phase` version check against evidence |
| NTH core hooks wording | §9 |
| NTH `entry_invariant --check` | §1.9 before-call step 1 |

| P3 r3 (on r5) | Cadence plan-review | READY WITH CHANGES (MF-1–4, NTH 8) | Applied in r6 |

| r3 ID | Fix in r6 |
| --- | --- |
| MF-1 CoCo code after verify; fsmonitor; orphan children | Clone config baseline + `core.fsmonitor=false` on every guard git call; merge the fetched sha; verify again after tests; `hooksPath=/dev/null` on merge and close; `finish` always kills the process group (tested) |
| MF-2 noise fix cannot work | Cadence mutable files excluded from raw hashes, run identity compared instead (tested from `/tmp`) |
| MF-3 Phase 5 bronze fixtures need Excel | Formula-free fixtures generated by a committed openpyxl script |
| MF-4 Phase 6 contract types | `RunRejected` in Phase 3; `CREATE_RUN` → `RunCreated`/`RunRejected`; `EXECUTE_RUN` → `RunView` |
| r1 MF-11 rollback tag | §1.9 step 6 tags deploy phases |
| NTH log truncated before lock | Lock first (tested) |
| NTH COCO_RESULT escaped in JSON | Read from `<log>.last.md` |
| NTH snow build output dirties clone | `.gitignore` `labs/bob_killer/hosts/snowflake/output/` |
| NTH stale settings allow list | `.claude/settings.json` updated |
| NTH guard cwd / Cadence symlink | Root from script path; Cadence path resolved with `pwd -P` |
| NTH Phase 1 ownership | Phase 1 is Claude Code's own phase |
| NTH AGENTS precedence, run-base-sha | AGENTS exception line; §1.9 defines `<run-base-sha>` |
| Step 0d human pre-merge | Replaced by Phase 1 inside the run, reviewed at the PR (user asked to start `/cadence` now) |

| A5 vibe-test (on r6) | Cadence vibe-test | NOT READY FOR P1 (G1–G6 blocking, G7–G24 non-blocking) | Blocking gaps applied in r7; non-blocking go to the P1 plan |

| Gap | Fix in r7 |
| --- | --- |
| G1 global stage registration vs frozen test | Phase 4: `Registry.snapshot()` + `tests/conftest.py` autouse fixture |
| G2 acceptance criterion 4 | §10.4 rewritten as a checkable path rule; issue #1 matches |
| G3 bootstrap source missing | Phase 2 reconstructs it from §6.3, marked, without the ACCOUNTADMIN grant |
| G4 Phase 2 exit | F2–F6, F8, F9 live; F1, F7 deploy-level; runtime check after merge; F10 in Phase 5 |
| G5 Stop hook vs blocked | §1.6 item 0: `BLOCKED` marker in `hook_stop.py`; §1.9 steps 8–9 map blocked and guard failures |
| G6 clone-check vs hook output | §1.2 control 3 tolerance + archive; Phase 1 probes `PostToolUse` |
| Security note | §11 accepted-risk row with the checked grants |
| G16 schemas | Done |
| G23 timeout code | Fixed |

| P7 test-benchmark (plan) | Cadence test-benchmark | FAIL (mean 7.0; F1–F3 must-fix) | F1–F3 written into §8 Phases 1, 2, 3, 5, 6 and D11 (r7.4). The P4 peer did not read the benchmark file and could not be pointed at it (lean-prompt rule), so the spec carries them. F1–F3 stay open in `.context/findings.jsonl` until R5. |

| User request 2026-10-16 | — | Add ODCS data contracts | D13; Phase 1 vendors the schema and adds PyYAML; Phase 3 generates and tests the contract |

| User scope change 2026-10-16 | — | Bob Killer extract/graph/lift/generate/verify/VBA + a dbt project in Snowflake; the run fails without them | §2 rewritten (goal 2.0), D14–D16, §8a phases to be planned by a fresh Cadence run |

| Round | Reviewer | Verdict | Result |
| --- | --- | --- | --- |
| r8 (2026-10-16) | Cadence plan-update (P4), plan `.context/plans/snowflake-host.plan.md` | Plan item 0b | Plan cycle 1 MF-1 to MF-6 folded: settled items G7 to G24 (as amended) in §5.2, §6.1, §6.4 and §8; control 6 as exact paths (MF-2); hello app path (MF-2); forced-overlap and two-writer landing tests (MF-4, cycle 2 MF-1); SHA mismatch 400 (MF-5); Phase 1 close commit (MF-6). §2 (goal 2.0) and D11–D16 unchanged. |
| Attested P3 on r7.1 | Cadence plan-review | READY WITH CHANGES (MF-1, MF-2) | MF-1: local live runs with `live_phase<n>_<date>.txt` evidence (§1.6, §6.4); G17 drops the branch-protection rule. MF-2: Phase 2 is the only owner of the TEST_ sweep; Phase 1 `conftest.py` has no sweep (§1.6 item 7, §8 Phases 1 and 2). NTH-1: core `execute_run` calls `claim_run` (§5.2 step 4, §8 Phase 4). |
| D12 r7.2 | User change `e504f06` | — | `live` CI job is automatic when the `SNOWFLAKE_*` secrets exist, skips with a notice that names `tools/setup-ci-secrets.sh`, fails on partial secrets, is never a required check; the local live run is the phase evidence (§1.2 control 8, §1.6 item 7, §1.6 exit). |
| P3 cycle 3 (attested, on r7.2) | Cadence plan-review | READY WITH CHANGES (MF-1) | `live` job triggers, `id: secrets` step, skip notice, partial-secrets failure, `concurrency:` group (§1.6 item 7); §1.6 exit uses the local live run and the first CI result (§1.6 exit). |
| P3 cycle 4 (attested, on r7.2) | Cadence plan-review | READY WITH CHANGES (MF-1) | Workflow-level triggers; job-level `if: github.event_name != 'schedule'`; PR-head checkout; `paths:` filters kept; `vars.*` warnings; pending-run note (§1.2 control 8, §1.6 item 7). |
| P6 plan-gate round 1 | de-adversarial-reviewer | REQUEST CHANGES (B-1, C-1 to C-4) | B-1: core `execute_run` keeps `-> RunState`; lost claim returns the stored state or raises `KeyError`; `EXECUTE_RUN` builds the `RunView` (§5.2 step 4, §8 Phases 4 and 6). C-1: `claim_run` live overlap test (§8 Phase 4). C-2: sweep scoped to the current database, prefix in Python (§6.4, §8 Phase 2). C-3: spec r8 trace file (§8 Phase 1). C-4: README "Stuck runs" (§8 Phase 8). |
| P6 plan-gate rounds 2 and 3 | de-adversarial-reviewer | REQUEST CHANGES (r2 B-1, C-1, C-2); APPROVE WITH CONDITIONS (r3 C-1) | r2 B-1: A claims, then the barrier; `claim_run` sends no transaction statements. r2 C-1: handler narrows `Run \| None`. r2 C-2: `SHOW SCHEMAS IN DATABASE "<db>"`, `NULL` database drops nothing. r3 C-1: `LOCK_TIMEOUT = 60`, `join(timeout=120)` (§6.4, §8 Phases 2, 4, 6). |
| P6 plan-gate round 4 (carry) | de-adversarial-reviewer | REQUEST CHANGES (B-1, B-2, C-1 to C-3) | B-1: `Registry.clear()`, autouse fixture snapshot + clear, collection-order test, idempotent `register_stages()` (D4, §8 Phases 4 and 6). B-2: G9a in core `execute_run` after a won claim; the handler writes no run state (§5.2 step 4, §8 Phases 4 and 6). C-1: trace file "Replaced text, must be absent" (§8 Phase 1). C-2: `datetime.now(UTC)`, doubled `"` in quoted names (§6.4, §8 Phase 2). C-3: landing time evidence, README "Stuck runs" queued case and "Concurrent landings" (§5.2 step 4, §8 Phases 5 and 8). |
