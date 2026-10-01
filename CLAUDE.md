# Bob Killer — working agreement

Read SPEC.md before any task. The Workbook IR is the only contract between stages.
Phase 0 decisions that amend SPEC.md live in
`../../.context/proposals/ADR-0001_bob-killer-phase0_gh-5.md`; the
Phase 0 plan is `../../.context/plans/bob-killer-phase0_gh-5.plan.md` (ticket jtouley/sandbox#5).

## Loop (never skip a step)
1. Pick the lowest unbuilt node in dependency order (runtime fn → step → output).
2. RED: write the test. Expected values come from cached values, recorded oracle results,
   or `tests/oracle/*.json` (with `source` + `verified_by`) only.
   Run it via `scripts/record_run.py`. Confirm it fails for the stated reason. The run record is committed with the red commit.
3. GREEN: minimum code to pass. Never edit an existing assertion, test function, or `tests/oracle/**` in this phase.
4. REFACTOR: remove duplication; Excel semantics go in src/bob_killer/runtime/.
5. Recurse to parents. Commit test and implementation separately, test first.
   Every commit carries a trailer `TDD-Phase: red|green|refactor|scaffold|gate-change`.
6. Blocked? Add the node to `unsupported` with a reason, continue with independent nodes.

## Hard rules
- Parity is exact everywhere. No tolerances anywhere, including integration tests.
- No literal expected values in `assert` comparisons under `tests/unit` and `tests/integration`.
- No skip/xfail/approx/isclose without an entry in ALLOWLIST.md (named cell, root-cause class, linked issue).
- No branching on target or kind in core; use registry.py.
- LLM output may only fill `description`, or VBA translations behind tests. Names come from workbook.db. Never hand-edit IR YAML.
- Every type is defined once in contracts/ as a strict Pydantic model.
- Never execute VBA or macros outside the isolated oracle runner.
- `.context/` is committed evidence. If a gate fails, report it. Never delete, rewrite or hide logs in .context/.
- PRs merge with merge commits, not squash (the TDD-order gate reads commit order).

## Commands (from labs/bob_killer/)
- uv run pytest -q
- uv run python scripts/gates.py   # must pass before you stop
- uv run bob-killer all golden/sgec_tool.xlsm --out build/
- uv run fastapi dev src/bob_killer/api/main.py

## Start here
Phase 0 in SPEC.md, following the plan above. First task: scaffold the repo, then write the gate
scripts and prove each one rejects a deliberately bad commit.
