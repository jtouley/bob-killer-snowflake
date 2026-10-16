# Plan — Bob Killer Phase 0: Skeleton + anti-cheat gates (gh-5)

RUN_BY_COMMAND: plan-create
Ticket: #5 (jtouley/sandbox#5) · task_id gh-5
Spec: `labs/bob_killer/SPEC.md` (sha256 b9d63b73…7e42a)
Vibe test: `.context/vibetest/bob-killer-spec_gh-5_2026-10-01.md`
Branch: `ccr-0d94cccb-c40ohp`

## Goal

Stand up `labs/bob_killer/` as a self-contained uv project that meets the
Phase 0 "done when" from SPEC.md:

1. CI runs green on an empty pipeline.
2. A deliberately cheating commit is rejected by the gates, with recorded evidence.
3. A contract change without a `schema_version` bump fails CI.

## Constraints

- Python 3.12, `uv`, `ruff`, `mypy --strict`, `pytest`, `hypothesis`, Polars (no pandas).
- Self-contained under `labs/bob_killer/`. Sandbox root `pyproject.toml` / `uv.lock` untouched.
- Apache-2.0 `LICENSE` inside the subtree (spec decision 4). The sandbox repo stays MIT.
- `.context/` is committed (user directive; vibe-test G2).
- Every type is defined once in `contracts/` as `ConfigDict(strict=True, extra="forbid", frozen=True)`.

## Non-goals (Phase 0)

- No Excel parsing, graph, lift, generate or verify logic. Packages exist with empty registries only.
- No Rust crate build. `crates/excel-kernel/` holds a README placeholder; the maturin build comes in Phase 4 (spec decision 5).
- No real oracle. `services/oracle/` holds an interface and stub (vibe-test G18).
- No golden downloads in CI (G5).

## Step 0 — restatement, decisions, blast radius

**Problem.** Agents under TDD pressure cheat. Phase 0 builds the cage before
the animal: gates that mechanically reject the known cheat patterns, proven by
fixtures, on an empty pipeline.

**Decisions adopted from the vibe-test (recorded in `.context/proposals/ADR-0001_bob-killer-phase0_gh-5.md`):**

| ID | Decision |
|---|---|
| D1 (G1) | Parity is exact everywhere. SPEC errata note replaces "within tolerance" |
| D2 (G2) | `.context/` is committed. Only `*.db` and `tmp/` are ignored |
| D3 (G3) | Hand-verified expected values live in `tests/oracle/*.json` with provenance and are loaded through `tests/oracle_values.py`. Numeric literals in assert comparisons under `tests/` are a lint error |
| D4 (G4) | Commit trailer `TDD-Phase: red\|green\|refactor`. Gate rules are in Phase B |
| D5 (G6) | import-linter contracts: stages independent; shared = contracts, ir, runtime, registry; store below stages; api/cli on top |
| D6 (G7) | Contract snapshots live under `contracts/snapshots/v{N}/`. The update command refuses an existing version directory |
| D7 (G11) | Incubate in sandbox with a path-filtered workflow; extract later |

**Blast radius.** New subtree `labs/bob_killer/` plus one new workflow
`.github/workflows/bob-killer.yml` (path filter `labs/bob_killer/**`) and
the committed `.context/`. Existing labs are unaffected. Rollback means
deleting the subtree and the workflow.

## Phases (TDD; each step = red commit then green commit)

Commit convention from D4: every commit under `labs/bob_killer/` carries a
`TDD-Phase:` trailer, or `TDD-Phase: scaffold` for non-code scaffolding
(config, docs, empty `__init__`). Red runs are saved to
`.context/runs/<run_id>/` by `scripts/record_run.py`.

### A. Scaffold (no behavior)
- `pyproject.toml` (Python 3.12, `bob-killer` script, deps: pydantic>=2, fastapi, polars, openpyxl, oletools, pyyaml, jinja2, streamlit; dev: pytest, hypothesis, mypy, ruff, import-linter, mutmut, pytest-cov, httpx).
- Package dirs from SPEC layout with `__init__.py`. `CLAUDE.md`, `ALLOWLIST.md` (empty table), `LICENSE` (Apache-2.0), `README.md`.
- **Exit:** `uv sync` succeeds; `uv run python -c "import bob_killer"` succeeds.

### B. Gate scripts (core of Phase 0), each test-first with a cheat fixture
Each gate is a function registered in one `scripts/gates.py` registry
(`@gate("name")`), never a cloned CLI shell (`core:dry-extension`).
`scripts/gates.py` runs all of them, or one via `--only`.

| Gate | Rule | Cheat fixture that must fail |
|---|---|---|
| `tdd_order` | Within base..HEAD, every `green` commit touching `src/X` is preceded by a `red` commit touching `tests/` and a run record in `.context/runs/` referencing that red commit's test ids. `red` commits touch only `tests/` + `.context/` | Impl and test in one commit; green with no prior red |
| `assertions_frozen` | A `green`/`refactor` commit may not modify or delete an existing `assert` node (AST diff per test function) | Green commit loosens `== x` to `>= 0` |
| `no_oracle_literals` | No numeric/str literal as a comparison operand in `assert` under `tests/unit` and `tests/integration` (D3) | `assert f() == 6.0` |
| `no_silent_skips` | `pytest.skip`, `pytest.mark.skip/xfail`, `pytest.approx`, `math.isclose` require an `ALLOWLIST.md` row referenced by `# allow: <id>` | Bare `@pytest.mark.xfail` |
| `exact_parity` | `verify/config.py` comparator has no parameter named like `tol`, `rtol`, `atol`, `eps`, `tolerance`, `approx` and no float default | Add `atol: float = 1e-9` |
| `append_only_log` | `.context/hooks.log` is a hash chain (each line has the sha256 of the previous line). Any rewrite or deletion breaks the chain | Edit a middle line |
| `contracts_versioned` | Regenerate DDL, JSON Schema and OpenAPI. They must equal `snapshots/v{schema_version}/` (D6) | Add a field without a bump |
| `types_lint` | `ruff check`, `ruff format --check`, `mypy --strict src scripts` | Untyped def |
| `boundaries` | `lint-imports` with D5 contracts | `graph` imports `lift` |
| `coverage` | ≥90% line coverage of `src/`; vacuous pass on 0 statements (G10) | n/a (threshold test) |
| `mutation` | Nightly only: mutmut on `runtime/` ≥80% killed; 0 mutants = vacuous pass | n/a in PR CI |

- **Exit:** `tests/gates/test_cheats.py` builds a temp git repo per cheat
  and asserts each gate exits non-zero with the expected rule id. Same
  for one clean history, which must pass. Output saved to
  `.context/evidence/cheat-rejections.txt`.

### C. Contracts + generation
- `contracts/base.py`: `StrictModel` with the mandated `ConfigDict`; `SCHEMA_VERSION = 1`.
- Minimal models: `RunCreate`, `Run`, `StageStatus`, `UploadLimits`.
- `contracts/ddl.py`: Pydantic → SQLite DDL (type map: str→TEXT, int→INTEGER, float→REAL, bool→INTEGER CHECK, datetime→TEXT ISO, Enum→TEXT CHECK IN). Unknown type → raise.
- `contracts/export.py`: writes DDL, JSON Schema and OpenAPI (from the FastAPI app) to a snapshot dir. CLI: `uv run python -m bob_killer.contracts.export --new-version`.
- Tests: strict config on every model (introspection test over all `StrictModel` subclasses); DDL type map; snapshot equality.
- **Exit:** `contracts_versioned` gate green; adding a field fails it.

### D. Registries + CLI + API skeleton
- `registry.py`: `Registry[T]` generic with `register(name)` decorator and duplicate-name error. Instances: `functions`, `step_kinds`, `generators`, `detectors`, `stages`. Generators also load from entry points group `bob_killer.generators`.
- `cli.py`: subcommands derived from `registry.stages` (G17); with an empty pipeline, `all` runs zero stages and exits 0.
- `api/main.py`: `POST /runs` (multipart upload) → 202 `{run_id}`; `GET /runs/{id}`. Upload checks from `UploadLimits` in settings (G16): compressed size, zip member count, total decompressed size and ratio read from the zip central directory **before** extraction. Run status in SQLite through `store/`.
- `store/`: applies generated DDL; typed repository for `runs`.
- Tests: registry duplicate/lookup; CLI `all` on empty pipeline; API 202 + status; zip-bomb fixture (generated in-test via `zipfile` with a high-ratio member) → 413; oversize → 413; non-zip → 415.
- **Exit:** `uv run pytest -q` green; coverage ≥90%.

### E. Golden lock + oracle stub
- `scripts/fetch_golden.py`: reads `golden.lock` (JSON: id, url, sha256, status). Downloads `resolved` entries to `golden/` (gitignored) and verifies sha256. `--update` rewrites the hash only with explicit `--accept <id>`.
- `golden.lock` with 5 entries + 2 bonus SGEC versions; `status: unresolved` where no direct URL exists (G5).
- `services/oracle/`: `Oracle` protocol (`recalculate(workbook, inputs) -> values`, `convert_xls(path) -> xlsx`) + `UnavailableOracle` that raises. README states the runner requirement.
- Tests: lock schema validation; hash-mismatch detection against a local file:// fixture (no network).
- **Exit:** `fetch_golden.py --verify-lock` green in CI without network.

### F. Hooks + CI
- `labs/bob_killer/.claude/settings.json`: `PostToolUse` (Edit|Write under `src/`) → `scripts/hook_post_edit.py` (runs affected tests, appends to the hash-chained `.context/hooks.log`, writes `.context/runs/<id>/`); `Stop` → `scripts/gates.py`, which blocks on failure.
- `.github/workflows/bob-killer.yml`: on PR + push, paths `labs/bob_killer/**`; `uv sync`; `uv run python scripts/gates.py --ci --base origin/${{ github.base_ref }}`; nightly job: mutation gate.
- `.pre-commit-config` entries are local to the subtree (assertions_frozen, types_lint).
- **Exit:** workflow green on the branch; cheat evidence file committed.

## Quality gates (real commands, all run from `labs/bob_killer/`)

```bash
uv sync
uv run pytest -q
uv run python scripts/gates.py            # all gates
uv run python scripts/gates.py --only tdd_order --base origin/main
uv run lint-imports
uv run mypy --strict src scripts
uv run ruff check . && uv run ruff format --check .
```

## TDD notes

- Each gate's test asserts the **rule id** and a non-zero exit, not just "fails".
- Clean-history control case in every cheat test, to catch over-eager gates.
- No `pytest.approx` anywhere. Expected values come from fixtures (gates) or are structural (API status codes are protocol constants, not oracle values; D3's literal ban applies to `tests/unit` + `tests/integration` oracle comparisons. HTTP codes compare against `http.HTTPStatus` members).

## Risks

| Risk | Mitigation |
|---|---|
| Gates are bypassed when sessions are rooted at the sandbox root (hooks don't fire) | CI is the backstop; Stop hook documented in root CLAUDE.md pointer |
| `tdd_order` is brittle on merge commits | Walk `--first-parent --no-merges` over base..HEAD; test with a merge fixture |
| No Excel oracle → Phase 1 blocked | Oracle stub plus explicit Phase 1 entry criterion; raised in issue #5 |
| Phase 0 scope creep | Each sub-phase has an exit; nothing beyond the "done when" |

## Next step

`/plan-review .context/plans/bob-killer-phase0_gh-5.plan.md`

---

## Update 2026-10-01 (round 1 review: `.context/reviews/plan_bob-killer-phase0_gh-5.md`)

RUN_BY_COMMAND: plan-update

Prior text above is kept unchanged. These amendments take precedence over it.

| Review ID | Change |
|---|---|
| PR-1 | `scripts/record_run.py` writes `.context/runs/<run_id>/run.json` = {node_ids, outcome per node, tests_tree_sha256, tdd_phase}. The red commit includes its own run record. `tdd_order` recomputes the red commit's `tests/` tree hash and requires a record in that commit whose hash matches and whose listed node ids all `failed` |
| PR-2 | Enforcement starts at the first commit in range carrying a `TDD-Phase:` trailer. `TDD-Phase: scaffold` is exempt but may not touch `src/**/*.py` beyond empty `__init__.py`/docstrings. New fixture: `bootstrap_history` (pre-trailer commits + scaffold + red/green) must pass |
| PR-3 | `assertions_frozen` compares assert nodes keyed by (file, qualified function, ordinal). In `green`/`refactor` the set of test functions may only grow. A delete or rename = violation `assertions_frozen/test-removed`. New cheat fixture: rename test in green |
| PR-4 | The Stop hook requires a green tree, which is intentional. A blocked Stop appends `{"event":"stop_blocked","failed_gates":[...]}` to `.context/hooks.log` (hash-chained) |
| PR-5 | Phase 0 runtime deps reduced to pydantic, fastapi, python-multipart. Dev: pytest, pytest-cov, hypothesis, mypy, ruff, import-linter, mutmut, httpx. Polars, openpyxl, oletools, jinja2 and streamlit are added by the phase that first imports them |
| PR-6 | CI base: `${{ github.event.pull_request.base.sha || github.event.before }}`. An all-zero SHA falls back to `origin/main` |
| PR-7 | Pin `fastapi~=` and `pydantic~=` minors. The snapshot-mismatch message names dependency drift as a possible cause |
| PR-8 | Before each E1 edit: `python3 $CADENCE_HOME/shared/skill_gate.py check --skill cadence --action strreplace --file <path>` (Pi protocol), because the Cadence gated prefixes don't cover `labs/bob_killer/src/` |
| PR-9 | The literal-lint scope (`tests/unit`, `tests/integration`) goes into `labs/bob_killer/CLAUDE.md` |
| PR-10 | Evidence path: `.context/evidence/<run_id>_cheat-rejections.txt` |

Next step: `/plan-review` (round 2).

---

## Update 2026-10-01 (b): adversarial conditions (`.context/adversarial/adversarial_bob-killer-phase0_gh-5.md`)

RUN_BY_COMMAND: plan-update

Conditions C1–C7 are in-scope E1 work. They're folded into Phase B (gates):
- C1: `record_run.py` is the only `run.json` writer and stores the junit XML + its sha256. `tdd_order` cross-checks the two.
- C2: import-linter forbids `bob_killer` → `tests`. Red commits limited to tests, conftest and fixture data.
- C3: `tests/oracle/**` and `tests/oracle_values.py` are frozen in green/refactor.
- C4: `Hooks-Log-Head:` commit trailer anchors the log chain. CI checks prefix-ancestry across commits.
- C5: `TDD-Phase: gate-change` for gate files. `labs/bob_killer/scripts/` added to CODEOWNERS (@jtouley).
- C6: `exact_parity` bans `*args`/`**kwargs`, float defaults, and tolerance-named module constants in `verify/`.
- C7: `tdd_order/empty-range` failure when src changed but no trailer commits are in range.
Each condition gets a cheat fixture in `tests/gates/test_cheats.py`.

---

## Update 2026-10-01 (c): test-benchmark plan (`.context/benchmarks/gh-5_plan.json`)

RUN_BY_COMMAND: plan-update

TB-1..TB-5 folded into Phase B/D: a shared `HistoryBuilder`; assert exit==1 + exact rule id; a clean control per gate; unit/integration split for upload limits; a hypothesis property test for the hash-chained log.
