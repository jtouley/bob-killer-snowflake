# Compiler local facts L-F1 and L-F2 (docs/SPEC-compiler-dbt.md §2)

Recorded 2026-10-16 by Claude Code on branch `compiler/phase9-prep`, from `labs/bob_killer/`.
Machine: macOS (Darwin 23.6.0, arm64), uv 0.12.18, Python 3.12.12.

## L-F1: `dbt parse` with dbt-core 1.12.3 and dbt-snowflake runs with no warehouse connection

Command:

```
uv tool run --from 'dbt-core==1.12.3' --with 'dbt-snowflake' dbt parse \
  --project-dir tests/fixtures/dbt_hello --profiles-dir tests/fixtures/dbt_hello
```

Resolved tool versions: dbt-core 1.12.3, dbt-snowflake 1.12.3 (outside the project's `uv.lock`, D29).
Fixture: `tests/fixtures/dbt_hello/` (one seed, one model, one `not_null` test, `profiles.yml` with
`account: ""` and `user: ""` per F14). No Snowflake connection was opened (parse does not connect).

Result: **exit 0**. Output:

```
Running with dbt=1.12.3
 adapter: Invalid profile: 'user' is a required property.
Registered adapter: snowflake=1.12.3
Unable to do partial parsing because saved manifest not found. Starting full parse.
Performance info: tests/fixtures/dbt_hello/target/perf_info.json
```

Note: with `user: ""` the local adapter logs `Invalid profile: 'user' is a required property.` and
still exits 0. The same parse with `account: "bk"` and `user: "bk"` (scratch copy, not committed) logs no
such line. F14 (an empty `account` and `user` deploy and build in Snowflake) is a Phase 10 live check;
this note is input for it, not a result.

Verdict: L-F1 holds.

## L-F2: oletools runs on 3.12 with the project's pinned set

After `uv lock` and `uv sync` with the core dependencies `openpyxl>=3.1`, `jinja2~=3.1`, `pyyaml>=6`,
`oletools>=0.60`:

```
uv run python -c "import oletools.olevba"   # exit 0
```

Locked versions: openpyxl 3.1.5, jinja2 3.1.6, pyyaml 6.0.3, oletools 0.60.2, olefile 0.47,
pcodedmp 1.2.6 (oletools dependency), pyparsing 3.3.3.

`mypy --strict` on `import oletools.olevba`: oletools has no `py.typed` and no typeshed stubs, so
`pyproject.toml` sets `ignore_missing_imports` for `oletools` and `oletools.*` only. olefile is typed
through `types-olefile` in the dev group.

Verdict: L-F2 holds.
