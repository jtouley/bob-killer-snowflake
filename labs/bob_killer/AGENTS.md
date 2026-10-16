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
