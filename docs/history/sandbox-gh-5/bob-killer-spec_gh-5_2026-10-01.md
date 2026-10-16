# Vibe test — Bob Killer Build Spec (gh-5)

RUN_BY_SKILL: vibe-test
Ticket: #5 (jtouley/sandbox#5) · task_id gh-5
Target: disk spec `labs/bob_killer/SPEC.md` (sha256 `b9d63b731dbd5e9e5ff3ea8b3e5a2df3387cc22a0c11c88ab388e8ae1057e42a`, dated 2026-09-25)
Pipeline run: 7e55bbdb-0641-4d47-a41c-c201248f632b
Date: 2026-10-01

## Classification

Disk spec, snapshotted verbatim into the branch. The spec is a design doc for a
multi-phase product. This Cadence run covers **Phase 0 (Skeleton)** only, as
named in the spec's own CLAUDE.md "Start here" section. Later phases are
evaluated only for gaps that would force Phase 0 to change.

## Overall read

The spec holds together well. The architecture is a five-stage compiler with
one IR, registries instead of branching, exact parity, and Excel as the only
oracle. The decisions section closes most of the questions a reviewer would
raise. What remains is a handful of internal contradictions and
under-specified mechanics in the anti-cheat gates. The gates are Phase 0's
whole deliverable, so they have to be pinned down before E1.

**Verdict for planning: PROCEED.** The blocking gaps below each have a default
resolution that P1 adopts and records as a decision. None needs the author to
redesign anything.

## Scenarios traced

| # | Scenario | Path through spec | Outcome |
|---|---|---|---|
| S1 | Agent writes the test and implementation in one commit | Gate "Red before green", `check_tdd_order.py` | Caught only if the gate can tell a test commit from an impl commit; the convention is unspecified (G4) |
| S2 | Agent edits an assertion during green | "Tests untouched in green", pre-commit diff | Pre-commit has to know the current phase. Nothing defines where phase lives (G4) |
| S3 | Agent hardcodes `assert sum_(...) == 6.0` | "No oracle literals" AST lint | Conflicts with loop step 2, which allows "a hand-verified constant" (G3) |
| S4 | Agent wraps a mismatch in `pytest.approx` | AST lint + ALLOWLIST.md | Handled. The integration-layer wording "within tolerance" contradicts it, though (G1) |
| S5 | CI checks red-before-green evidence in `.context/` | Layout says `.context/` is gitignored | CI can never see the evidence, so the gate is unenforceable (G2) |
| S6 | Contract field added without a `schema_version` bump | Decision 8 snapshot tests | Works if the snapshot-update command refuses to run without a version bump. The mechanism isn't stated (G7) |
| S7 | `stages may import contracts/ and runtime/` and generate reads the IR | Decision 7 vs "IR is the only contract" | `ir/`, `registry.py` and `store/` are missing from the allowed-import list (G6) |
| S8 | CI pins golden hashes in `golden.lock` | Golden set table | Montana row links a **.pdf**. iWARM, SGEC, JEDI and WARM links are landing pages, not files (G5). From this container every host returned no response (curl `000`) |
| S9 | Phase 0 "a deliberately cheating commit is rejected" | Roadmap | Needs a reproducible harness, not a one-off manual demo (G8) |
| S10 | PR merged with squash | Red-before-green relies on commit order | A squash erases the order. The gate must run on PR commits pre-merge, or merges must be non-squash (G9) |
| S11 | Mutation ≥80% on `runtime/` when `runtime/` is empty (Phase 0) | Gates table | Undefined. A zero-mutant run must count as a vacuous pass, not as 0% (G10) |
| S12 | Build hosted in `jtouley/sandbox` | Spec assumes a standalone `bob-killer/` repo, Apache-2.0, Python 3.12 | Sandbox is MIT and `requires-python >=3.14`, with no CI. Needs its own uv project + path-filtered workflow (G11) |

## Gaps and conflicts

| ID | Gap / conflict | Blocking? | Default resolution for P1 |
|---|---|---|---|
| G1 | Test-layers table: Integration oracle says "matches Excel **within tolerance**". Decision 1 and CLAUDE.md say exact, no tolerance | **Blocking** (it's the gate's semantics) | Exact wins. P1 amends SPEC wording through a dated errata note. The integration oracle is "exact equality" |
| G2 | `.context/` is gitignored per layout, yet the red-before-green CI gate and the append-only hook log both live there | **Blocking** | Commit `.context/` (user directive for this run). Ignore only `*.db` caches and scratch. `runs/` and the hook log are committed evidence |
| G3 | Loop step 2 allows a "hand-verified constant". The hard rules ban hardcoded expected numbers | **Blocking** | Hand-verified constants live in `tests/oracle/*.json` with `source`/`verified_by` provenance. Tests load them through one helper. The AST lint bans numeric literals in `assert` comparisons under `tests/` |
| G4 | No convention for marking red/green/refactor commits | **Blocking** | Commit trailer `TDD-Phase: red\|green\|refactor`. `red` may touch only `tests/`. `green` may not change existing `assert` nodes. `refactor` may not change assert nodes either. Checked by `scripts/check_tdd_order.py` over `base..HEAD` |
| G5 | Golden URLs are mostly landing pages, and one is a PDF | Non-blocking for Phase 0 (lock format + fetch script are in scope, real hashes are not) | `golden.lock` ships with `url`/`sha256` slots. Entries without a resolved direct URL are `status: unresolved`. CI fails on a hash *change*, not on unresolved entries. Fetching runs outside CI (nightly/manual) |
| G6 | import-linter allowed-imports list is incomplete | **Blocking** for the boundary gate | Shared layer = `contracts`, `ir`, `runtime`, `registry`. Stages (`extract`, `graph`, `lift`, `generate`, `verify`) are mutually independent. `store` is imported by stages and `api`. `api` and `cli` sit on top |
| G7 | "Contract change without version bump fails CI": mechanism unspecified | **Blocking** (Phase 0 done-when) | Snapshot files are stored under `contracts/snapshots/v{schema_version}/`. The test regenerates and compares. The update command writes only into a version directory that doesn't exist yet, so changing a contract means bumping |
| G8 | Cheat rejection evidence isn't defined | Non-blocking | `tests/gates/test_cheats.py` builds throwaway git repos, applies one cheat each, and asserts each gate exits non-zero. The output is saved to `.context/` as evidence |
| G9 | Squash merges defeat commit-order gates | Non-blocking | The TDD-order gate runs in PR CI over the PR's commit range. Documented in CLAUDE.md |
| G10 | Mutation and coverage thresholds on empty packages | Non-blocking | The gate script treats zero mutants or zero statements as a pass and says so in its output |
| G11 | Host repo mismatch (license, Python version, no CI) | Non-blocking | Self-contained uv project at `labs/bob_killer/` (Python 3.12, Apache-2.0 LICENSE inside the subtree). Workflow `.github/workflows/bob-killer.yml` is path-filtered. Extract to its own repo later |
| G12 | Spec says to use "Golden" both for snapshot tests and for the workbook sample set | Non-blocking | Snapshot tests live in `tests/snapshot/`. "Golden" means the workbook set only |
| G13 | Volatile functions (`NOW`, `RAND`, `TODAY`) vs exact parity are not addressed | Non-blocking (Phase 1/4) | Flag in Graph. Exclude from the parity denominator like macro-writable cells. Report separately |
| G14 | LLM description drafting appears in principles but in no roadmap phase | Non-blocking | Record as unscheduled. Not Phase 0 |
| G15 | "Export then re-import must produce an identical database": byte-identical SQLite isn't achievable | Non-blocking (Phase 2) | Define as a logical identity: sorted per-table row dumps are equal |
| G16 | Upload limits are named but have no values | Non-blocking | Config defaults: 50 MB compressed, 500 MB decompressed, 10k zip members, ratio ≤ 100. Values come from settings, not code |
| G17 | CLI lists `extract\|lift\|generate\|verify\|all`. There is no `graph` subcommand, though Graph is a stage | Non-blocking | CLI subcommands come from the stage registry, so `graph` exists automatically |
| G18 | Oracle needs licensed Excel or M365 Graph. This environment has neither, and real-Excel fixtures can't be authored here | Non-blocking for Phase 0, **blocking for Phase 1** | Phase 0 ships the oracle service interface plus a stub only. Raise as a risk in the plan |

## Risks for P1

1. **Gate scripts written by the agent they constrain.** Phase 0 gates are
   only as strong as their tests. Every gate needs a cheat fixture that it
   provably rejects (G8). Without one, the gates are decoration.
2. **Hooks scoped to a subtree of a larger repo.** Claude Code hooks in
   `labs/bob_killer/.claude/settings.json` fire only when the session is
   rooted there. Sessions rooted at sandbox need the CI gate as the backstop.
3. **No Excel anywhere yet.** Phase 1 can't start until the oracle runner exists
   (spec risk #1). Raise it now so it doesn't arrive as a surprise.
4. **Scope creep in Phase 0.** DDL generation from Pydantic, JSON Schema and
   OpenAPI snapshots, import-linter, FastAPI, registries, golden lock and
   gates add up to a lot. Keep each piece minimal and empty-pipeline-shaped.

## C.O.R.E.

- **SUMMARY:** Spec is coherent and buildable. 18 gaps found: 6 blocking
  (G1–G4, G6, G7), each with a default resolution. Proceed to P1 for Phase 0.
- **DECISIONS NEEDED:** (1) Accept the G2 directive that `.context/` is committed
  (user already said yes for this run). (2) Accept incubating in
  `sandbox/labs/bob_killer` under Apache-2.0 inside an MIT repo (G11).
  (3) Provide direct download URLs for the golden workbooks (G5).
- **ACTIONS REQUIRED:** P1 plan adopts the G1–G7 defaults as recorded decisions.
- **EVIDENCE:** this file; `labs/bob_killer/SPEC.md`; URL probe (all six hosts
  `000` from container).
