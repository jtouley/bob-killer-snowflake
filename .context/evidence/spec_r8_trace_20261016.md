# Spec r8 trace (plan item 0b, P6 r1 C-3, P6 r4 C-1)

- Spec: `docs/SPEC.md`, status line 3: "r8 (plan settled decisions folded; goal §2.0; D11–D16)". 1253 lines. Not committed.
- Plan: `.context/plans/snowflake-host.plan.md` (later sections win; current-effective-state tables for Phases 1, 2, 4, 6).
- Section start lines in r8: §1.2 = 43, §1.6 = 181, §2.4 = 478, §5.2 = 589 (to 649), §6.1 = 663, §6.4 = 735, §7 = 757, §8 = 780 (to 1091; Phase 1 786, Phase 2 813, Phase 3 856, Phase 4 881, Phase 5 945, Phase 6 988, Phase 7 1029, Phase 8 1060), §13 = 1156.
- §2 (goal 2.0) and D11–D16 are unchanged from the input file. D4 is the only §7 row that changed.

## Settled items

| # | Item | Settlement (short) | r8 section | r8 line(s) |
| --- | --- | --- | --- | --- |
| 1 | G1 (amended, P6 r4 B-1) | `snapshot()` + `clear()`; autouse fixture snapshot, clear, yield; collection-order test | §8 Phase 4; D4; §8 Phase 6 | 895, 899, 902; 764; 992 |
| 2 | G7 | Named columns, no `SELECT *`; `isoformat()`; `Draft202012Validator` with no `FormatChecker`; store names columns | §5.2 step 5; §8 Phase 4; §8 Phase 7 | 645–648; 924; 1046–1047 |
| 3 | G8 | SQLite upsert `ON CONFLICT … DO UPDATE`; failed-stage order case | §8 Phase 4 | 887, 890 |
| 4 | G9a (amended, P6 r4 B-2) | Core `execute_run`: `try` after a won claim, `set_state(FAILED)`, re-raise; handler writes no run state | §5.2 step 4; §8 Phase 4; §8 Phase 6 | 617–623; 905–913, 917–922; 997, 1009 |
| 5 | G9b (amended, NTH-3) | "recent runs", last 20 by `_seq` desc, all users | §5.2 step 3; §8 Phase 7 | 608–609; 1043–1044 |
| 6 | G9c | Job done, state not final: error with run id | §5.2 step 3; §8 Phase 7 | 607; 1045 |
| 7 | G10 (amended, MF-5) | Regex + `stage_file` check gives 400; SHA mismatch 400, `REMOVE`, no `RUNS` row | §5.2 step 2; §8 Phase 6 | 595–600; 1002–1004 |
| 8 | G11 | `UploadRejected` removes the staged file; large inputs in `tmp_path` | §5.2 step 2; §8 Phase 6 | 601; 1005–1006 |
| 9 | G12 | App accepts `.xlsx`, `.xlsm`; 415 live proof; README note | §8 Phase 7; §8 Phase 6; §8 Phase 8 | 1036; 1021; 1068–1070 |
| 10 | G13 | Real packing layout, exact `snowflake.yml` in evidence, no Mac wheels | §8 Phase 2; §8 Phase 6 | 841–843; 1015 |
| 11 | G14 (amended, NTH-5) | Default 10 000; 30 000-row live test; halving to floor 500; 500 fails stops blocked | §8 Phase 5 | 979–982 |
| 12 | G15 (amended, cycle 3) | Case 1 bronze `MERGE` fallback fix prompt; case 2 hard stop `retries`; other failure normal fix | §5.2 step 4; §8 Phase 5 | 630–639; 974–976 |
| 13 | G16 | No phase drops a schema outside TEST_; `APP` exists, `CORE`/`BRONZE` dropped | §6.3; §6.4; §12 | 733; 753; 1152 |
| 14 | G17 (amended, r7.1) | Gate test: `--base 0000…` uses merge-base; no branch-protection rule | §1.6 item 8 | 245–249 |
| 15 | G18 (amended) | Rules (a)–(d), blank-row definition; §2.4 "non-blank" | §6.1; §2.4; §8 Phase 5 | 694–703; 482; 951, 956 |
| 16 | G19 (amended, NTH-1) | Coverage `source` adds `src/bob_killer_sis`; gate already runs `--cov=src` | §1.6 item 6 | 208, 213–214 |
| 17 | G20 | App `ruff.toml` `extend` + `py311`; CI 3.11 mypy step | §1.6 item 6; §8 Phase 7 exit | 208–209, 215–216; 1055 |
| 18 | G21 (amended) | App `pyproject.toml` in Phase 1 only; on control 6 list | §1.6 item 6; §1.2 control 6; §8 Phase 1; §8 Phase 7 | 210–212; 75–76; 791–794; 1031–1033 |
| 19 | G22 | `snow streamlit get-url` returns URL; `DESCRIBE STREAMLIT` shows object, pool, integration | §8 Phase 7 | 1052–1053 |
| 20 | G24 (amended, P6 r1 B-1) | `claim_run`; core keeps `-> RunState`; lost claim returns stored state or `KeyError` | §5.2 step 4; §8 Phase 4; §8 Phase 6 | 611–616; 885–886, 891–892, 905–916; 1011 |
| 21 | Cycle 1 MF-1 | Spec r8 folds the settled decisions; status line; §13 row | Status; §8 Phase 1; §13 | 3; 804; 1246 |
| 22 | Cycle 1 MF-2 | Control 6 exact full-path list; hello app path; Phase 7 drops `ruff.toml`/`pyproject.toml` | §1.2 control 6; §8 Phase 2; §8 Phase 7 | 71–79; 815, 844; 1031–1033 |
| 23 | Cycle 1 MF-3 (replaced by D12) | CI secrets/variables names, key and connection file step, root `uv sync --locked`; no hard stop on missing secrets | §1.6 items 7 and 9 | 229–240, 250–252 |
| 24 | Cycle 1 MF-4 (replaced by cycle 2 MF-1) | Forced overlap of parallel landings | §8 Phase 5 two-writer test | 969–976 |
| 25 | Cycle 1 MF-5 | SHA mismatch 400, `REMOVE`, no `RUNS` row; unit and live tests | §5.2 step 2; §8 Phase 6 | 597–600; 1003–1004, 1019–1020 |
| 26 | Cycle 1 MF-6 | Empty close commit `phase 1: Gate and dependency prep verified`; `p1/gate-change:` prefix | §1.6 exit | 267–270 |
| 27 | Cycle 2 MF-1 | `BronzeWriter.land` with `after_claim`; call-order and 0-rows unit tests; two-writer live test | §5.2 step 4; §8 Phase 5 | 624–629; 959–964, 969–976 |
| 28 | Cycle 3 MF-1 (G15 cases) | Two failure cases; case 2 no fix prompt | §5.2 step 4; §8 Phase 5 | 634–639; 974–976 |
| 29 | Attested cycle 3 MF-1 (r7.2 live job) | Push, PR, dispatch; `id: secrets`; skip notice; partial failure; `concurrency:`; exit uses local run + first CI result | §1.6 item 7; §1.6 exit; §13 | 217–240; 264–266; 1249 |
| 30 | Attested r7.1 MF-1 | Local live runs with `live_phase<n>_<date>.txt`; no phase exit depends on CI `live`; secrets record is information only | §1.6 local runs; §1.6 item 9; §6.4; §13 | 254–258; 250–252; 741–742; 1247 |
| 31 | Attested r7.1 MF-2 | Phase 2 is the only sweep owner; Phase 1 `conftest.py` has no sweep | §1.6 item 7; §8 Phase 1; §8 Phase 2; §6.4 | 241–243; 798; 827–828; 743 |
| 32 | D12 r7.2 | `live` job automatic only with secrets; skip notice names `tools/setup-ci-secrets.sh`; never required; local run is evidence | §1.2 control 8; §1.6 item 7; §1.6 exit; D12 (unchanged); §13 | 85–89; 230–231, 239; 264; 771; 1248 |
| 33 | Cycle 4 MF-1 | Workflow-level `on:`; `push.branches: ["**"]`; `paths:` kept; `if: github.event_name != 'schedule'`; PR-head checkout; `vars.*` warnings; pending-run note | §1.2 control 8; §1.6 item 7; §13 | 85–88; 218–228, 233–235; 1250 |
| 34 | P6 r1 B-1 | Core `execute_run -> RunState`; `EXECUTE_RUN` builds `RunView`; `test_cli.py`/`test_api.py` unchanged; type-hint-only change in `cli.py`/`api/main.py` | §5.2 step 4; §8 Phase 4; §8 Phase 6 | 610–623; 885–886, 905–916, 939; 997–999 |
| 35 | P6 r1 C-1 | `claim_run` live overlap test and hard stop | §8 Phase 4 | 928–938 |
| 36 | P6 r1 C-2 | Sweep scoped to current database; prefix in Python; quoted qualified `DROP`; `TESTX_OLD`, no `IN ACCOUNT` tests | §6.4; §8 Phase 2 | 745–752; 829–836 |
| 37 | P6 r1 C-3 | Trace file before Phase 2; missing row stops E1 | §8 Phase 1 | 806–811 |
| 38 | P6 r1 C-4 | README "Stuck runs" | §8 Phase 8 | 1072–1078 |
| 39 | P6 r2 B-1 | A claims, then barrier; `claim_run` sends no transaction statements | §8 Phase 4 | 926–933 |
| 40 | P6 r2 C-1 | Handler narrows `Run \| None`: `KeyError` on `None`, then `RunView` | §5.2 step 4; §8 Phase 6 | 620–622; 997–999 |
| 41 | P6 r2 C-2 | `SELECT CURRENT_DATABASE()`; `NULL` drops nothing; `SHOW SCHEMAS IN DATABASE "<db>"`; `created_on` | §6.4; §8 Phase 2 | 745–748; 829–830, 836 |
| 42 | P6 r3 C-1 | `LOCK_TIMEOUT = 60`; `join(timeout=120)`; lock error fails test | §8 Phase 4 | 931, 934–935 |
| 43 | P6 r4 B-1 | `Registry.clear()`; fixture; collection-order test; `register_stages()` at import and handler entry; two-call test; one-process exit commands | D4; §8 Phase 4; §8 Phase 6 | 764; 895–903, 942; 990–995, 1008, 1026 |
| 44 | P6 r4 B-2 | G9a in core after a won claim; tests (a)–(c); handler has no G9a code; no `UPDATE` on `RUNS` after core call | §5.2 step 4; §8 Phase 4; §8 Phase 6 | 617–622; 912–913, 917–922; 997–999, 1009–1010 |
| 45 | P6 r4 C-1 | Trace file "Replaced text, must be absent" section | §8 Phase 1 | 807–811 |
| 46 | P6 r4 C-2 | `datetime.now(UTC)`; naive `created_on` raises `ValueError`; doubled `"`; two-time-zone and `TEST_A"B` tests | §6.4; §8 Phase 2 | 749–751; 831–833, 837–839 |
| 47 | P6 r4 C-3 | 30 000-row landing time in evidence; README "Stuck runs" queued case; "Concurrent landings" | §5.2 step 4; §8 Phase 5; §8 Phase 8 | 640–642; 981–982; 1073–1083 |

Rows: 47. Rows with no r8 location: 0. Rows where r8 text conflicts with the plan's winning section: 0 found.

## Replaced text, must be absent

Scope: r8 §5.2 (lines 589–649) and §8 (lines 780–1091). Each command runs from the repo root. The count is
`grep -n` matches piped to `wc -l`. A whole-file count is also shown.

| # | Replaced text (plan) | Command | Count §5.2+§8 | Count whole file |
| --- | --- | --- | --- | --- |
| 1 | "returns the current `RunView`" in core `execute_run` text (P6 r1 B-1) | ``sed -n '589,649p;780,1091p' docs/SPEC.md \| grep -nF -- 'returns the current `RunView`' \| wc -l`` | 0 | 0 |
| 2 | `IDENTIFIER(CURRENT_DATABASE())` (P6 r2 C-2) | ``sed -n '589,649p;780,1091p' docs/SPEC.md \| grep -nF -- 'IDENTIFIER(CURRENT_DATABASE())' \| wc -l`` | 0 | 0 |
| 3 | Barrier before both claims (P6 r2 B-1) | ``sed -n '589,649p;780,1091p' docs/SPEC.md \| grep -nF -- 'wait on one `threading.Barrier(2)` and then call `SnowflakeRunStore.claim_run`' \| wc -l`` | 0 | 0 |
| 4a | "`workflow_dispatch` only" for the `live` job (cycle 3 r7.2 MF-1) | ``sed -n '589,649p;780,1091p' docs/SPEC.md \| grep -nF -- '`workflow_dispatch` only' \| wc -l`` | 0 | 0 |
| 4b | "manual-only" for the `live` job (cycle 3 r7.2 MF-1) | ``sed -n '589,649p;780,1091p' docs/SPEC.md \| grep -nF -- 'manual-only' \| wc -l`` | 0 | 0 |
| 5a | G9a in the handler (P6 r4 B-2) | ``sed -n '589,649p;780,1091p' docs/SPEC.md \| grep -nF -- 'G9a stays in the procedure' \| wc -l`` | 0 | 0 |
| 5b | G9a in the handler (P6 r4 B-2) | ``sed -n '589,649p;780,1091p' docs/SPEC.md \| grep -nF -- '`EXECUTE_RUN` catches an error outside a stage' \| wc -l`` | 0 | 0 |
| 6 | Snapshot-only fixture claim (P6 r4 B-1) | ``sed -n '589,649p;780,1091p' docs/SPEC.md \| grep -nF -- 'cannot change `tests/integration/test_api.py:38`' \| wc -l`` | 0 | 0 |
| 7 | Naive `datetime.now()` in the sweep text (P6 r4 C-2) | ``sed -n '589,649p;780,1091p' docs/SPEC.md \| grep -nF -- 'datetime.now()' \| wc -l`` | 0 | 0 |

All counts are 0. E1 may continue to Phase 2 on this check.
