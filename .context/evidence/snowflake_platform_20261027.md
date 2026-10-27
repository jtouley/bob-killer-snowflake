
## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-27T16:45:28.062594+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
New version of Snowflake CLI available. Newest: 3.31.0, current: 3.29.0
```

## $ snow snowpark deploy --schema TEST_099579CD -c bob_killer --project hosts/snowflake

_2026-10-27T16:45:43.469897+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading platform_probe.py to @BOB_KILLER.TEST_099579CD.deployments/platform_probe.py/
  Uploading src.zip to @BOB_KILLER.TEST_099579CD.deployments/src.zip/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
  Creating procedure CREATE_RUN
  Creating procedure EXECUTE_RUN
+-----------------------------------------------------------------------------------------------------------------+
| object                                                                                    | type      | status  |
|-------------------------------------------------------------------------------------------+-----------+---------|
| BOB_KILLER.TEST_099579CD.PLATFORM_PROBE(stage_path string)                                | procedure | created |
| BOB_KILLER.TEST_099579CD.CREATE_RUN(stage_file varchar, filename varchar, sha256 varchar) | procedure | created |
| BOB_KILLER.TEST_099579CD.EXECUTE_RUN(run_id varchar)                                      | procedure | created |
+-----------------------------------------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-27T16:46:11.855300+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark deploy --schema TEST_612B65B5 -c bob_killer --project hosts/snowflake

_2026-10-27T16:46:17.605824+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading platform_probe.py to @BOB_KILLER.TEST_612B65B5.deployments/platform_probe.py/
  Uploading src.zip to @BOB_KILLER.TEST_612B65B5.deployments/src.zip/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
  Creating procedure CREATE_RUN
  Creating procedure EXECUTE_RUN
+-----------------------------------------------------------------------------------------------------------------+
| object                                                                                    | type      | status  |
|-------------------------------------------------------------------------------------------+-----------+---------|
| BOB_KILLER.TEST_612B65B5.PLATFORM_PROBE(stage_path string)                                | procedure | created |
| BOB_KILLER.TEST_612B65B5.CREATE_RUN(stage_file varchar, filename varchar, sha256 varchar) | procedure | created |
| BOB_KILLER.TEST_612B65B5.EXECUTE_RUN(run_id varchar)                                      | procedure | created |
+-----------------------------------------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-27T18:02:51.181200+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark deploy --schema TEST_738C3145 -c bob_killer --project hosts/snowflake

_2026-10-27T18:02:56.834980+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading platform_probe.py to @BOB_KILLER.TEST_738C3145.deployments/platform_probe.py/
  Uploading src.zip to @BOB_KILLER.TEST_738C3145.deployments/src.zip/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
  Creating procedure CREATE_RUN
  Creating procedure EXECUTE_RUN
+-----------------------------------------------------------------------------------------------------------------+
| object                                                                                    | type      | status  |
|-------------------------------------------------------------------------------------------+-----------+---------|
| BOB_KILLER.TEST_738C3145.PLATFORM_PROBE(stage_path string)                                | procedure | created |
| BOB_KILLER.TEST_738C3145.CREATE_RUN(stage_file varchar, filename varchar, sha256 varchar) | procedure | created |
| BOB_KILLER.TEST_738C3145.EXECUTE_RUN(run_id varchar)                                      | procedure | created |
+-----------------------------------------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-27T19:42:51.688614+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark deploy --replace --schema TEST_738C3145 -c bob_killer --project hosts/snowflake

_2026-10-27T19:43:03.735031+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading platform_probe.py to @BOB_KILLER.TEST_738C3145.deployments/platform_probe.py/
  Uploading src.zip to @BOB_KILLER.TEST_738C3145.deployments/src.zip/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
  Creating procedure CREATE_RUN
  Creating procedure EXECUTE_RUN
+----------------------------------------------------------------------------------------------------------------------------+
| object                                                                                    | type      | status             |
|-------------------------------------------------------------------------------------------+-----------+--------------------|
| BOB_KILLER.TEST_738C3145.PLATFORM_PROBE(stage_path string)                                | procedure | definition updated |
| BOB_KILLER.TEST_738C3145.CREATE_RUN(stage_file varchar, filename varchar, sha256 varchar) | procedure | definition updated |
| BOB_KILLER.TEST_738C3145.EXECUTE_RUN(run_id varchar)                                      | procedure | definition updated |
+----------------------------------------------------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-27T19:59:44.240483+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark deploy --schema TEST_48CCD142 -c bob_killer --project hosts/snowflake

_2026-10-27T19:59:49.676749+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading src.zip to @BOB_KILLER.TEST_48CCD142.deployments/src.zip/
  Uploading platform_probe.py to @BOB_KILLER.TEST_48CCD142.deployments/platform_probe.py/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
  Creating procedure CREATE_RUN
  Creating procedure EXECUTE_RUN
+-----------------------------------------------------------------------------------------------------------------+
| object                                                                                    | type      | status  |
|-------------------------------------------------------------------------------------------+-----------+---------|
| BOB_KILLER.TEST_48CCD142.PLATFORM_PROBE(stage_path string)                                | procedure | created |
| BOB_KILLER.TEST_48CCD142.CREATE_RUN(stage_file varchar, filename varchar, sha256 varchar) | procedure | created |
| BOB_KILLER.TEST_48CCD142.EXECUTE_RUN(run_id varchar)                                      | procedure | created |
+-----------------------------------------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-27T21:28:45.498294+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark deploy --schema TEST_3B1D5C04 -c bob_killer --project hosts/snowflake

_2026-10-27T21:28:51.321994+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading platform_probe.py to @BOB_KILLER.TEST_3B1D5C04.deployments/platform_probe.py/
  Uploading src.zip to @BOB_KILLER.TEST_3B1D5C04.deployments/src.zip/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
  Creating procedure CREATE_RUN
  Creating procedure EXECUTE_RUN
+-----------------------------------------------------------------------------------------------------------------+
| object                                                                                    | type      | status  |
|-------------------------------------------------------------------------------------------+-----------+---------|
| BOB_KILLER.TEST_3B1D5C04.PLATFORM_PROBE(stage_path string)                                | procedure | created |
| BOB_KILLER.TEST_3B1D5C04.CREATE_RUN(stage_file varchar, filename varchar, sha256 varchar) | procedure | created |
| BOB_KILLER.TEST_3B1D5C04.EXECUTE_RUN(run_id varchar)                                      | procedure | created |
+-----------------------------------------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```
