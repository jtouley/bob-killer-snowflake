# Phase 6 live: deployed procedures, real upload path (2026-10-16)

Deployed with `snow snowpark build` + `snow snowpark deploy --schema TEST_P6` (CREATE_RUN, EXECUTE_RUN, runtime 3.12).
Golden: mt_dot_budget, staged as @UPLOADS/<sha>.xlsx (auto_compress off).

- CALL CREATE_RUN -> {run_id: 31fb4fd3..., state: queued}
- CALL EXECUTE_RUN -> run succeeded; stage land_bronze succeeded, detail 'landed'
- Tables: BRONZE_ROWS 61 rows over 2 sheets, LANDED_FILES 1, RUNS state succeeded
- Defect found live and fixed (p6/red + p6/green): handler had a 5th parameter; Snowflake error 100357

```text
== CREATE_RUN with a sha256 that does not match the staged bytes
{"detail": "sha256 must be 64 lowercase hex digits and stage_file must be <sha256>.xlsx", "status": 400}
== second upload of the same bytes: new run, bronze already landed
run 5d333821cfd44a84a52d03d2472f202a
{"run": {"created_at": "2026-10-16T21:44:37.604364Z", "filename": "again.xlsx", "run_id": "5d333821cfd44a84a52d03d2472f202a", "schema_version": 5, "sha256": "e835558d6df6a84ba0576804d02e8280821205d0b576ed232379a373afc93047", "state": "succeeded"}, "stages": [{"detail": "already landed", "run_id": "5d333821cfd44a84a52d03d2472f202a", "stage": "land_bronze", "state": "succeeded"}]}
bronze_rows_after_second_run = 61
```
