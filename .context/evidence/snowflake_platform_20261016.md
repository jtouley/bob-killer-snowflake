# Snowflake platform facts, host Phase 2 (2026-10-16)

Account checks for docs/SPEC.md §4, run as role BOB_KILLER_OWNER (connection `bob_killer`) by
`labs/bob_killer/tests/live/test_platform.py`. Every command and output is appended below, one section
per step, for every live run of the day (the early runs include the failures that were fixed in the
tests; the last run is the passing one, see `live_phase2_20261016.txt`).

| Fact | Result | How |
| --- | --- | --- |
| F1 | TRUE (deploy level) | `snow streamlit deploy` of `HELLO_EAI` and `HELLO_NO_EAI`; `DESCRIBE STREAMLIT` shows `runtime_name = SYSTEM$ST_CONTAINER_RUNTIME_PY3_11`, `compute_pool = BOB_KILLER_POOL`, `main_file = hello_app/streamlit_app.py`. The app is not opened (runtime check after merge). |
| F2 | TRUE | `PLATFORM_PROBE` (runtime 3.12) imports `bob_killer.contracts`, builds a `Run`, returns `sys_version` 3.12.13. |
| F3 | TRUE | Every package of the import set is on the Anaconda channel for 3.12 (`information_schema.packages`; pydantic 2.11.7 and 2.11.9; et-xmlfile is listed as `et_xmlfile`). The path that `snow` 3.29 actually used: the **artifact repository** `snowflake.snowpark.pypi_shared_repository` (`DESCRIBE PROCEDURE`: `packages = []`, `artifact_repository_packages = ['snowflake-snowpark-python','pydantic<2.12,>=2.11']`, installed `pydantic==2.11.10`). `snow snowpark build` reported "No external dependencies": no wheel was bundled from the Mac. Both paths work; deploys use the artifact repository. |
| F4 | TRUE | In a TEST_ schema: two inserts of the same PRIMARY KEY both succeed (COUNT = 2); a NULL into a NOT NULL column fails (100072, raised as connector `IntegrityError`). |
| F5 | TRUE | Inside the owner's-rights procedure `CURRENT_SCHEMA()` is the procedure's TEST_ schema; `DESCRIBE PROCEDURE` shows `execute as = OWNER`. |
| F6 | TRUE | `put_stream(auto_compress=False, overwrite=False)` to `@UPLOADS/<sha256>.xlsx`: `LIST` shows the `.xlsx` name with the original size; `get_stream` inside the procedure returns bytes with the same SHA-256. |
| F7 | TRUE (deploy level) | Both copies deploy: with `BOB_KILLER_PYPI_EAI` (`external_access_integrations = ["BOB_KILLER_PYPI_EAI"]`) and without (`[]`). Which one can install from PyPI shows only when a person opens the app (post-merge step). |
| F8 | TRUE | `snow snowpark build` then `snow snowpark deploy --schema TEST_…`. The working `hosts/snowflake/snowflake.yml` is recorded below: artifact `src: ../../src`, `dest: src.zip` (zip root holds `bob_killer/`). `DESCRIBE PROCEDURE` imports: `…/DEPLOYMENTS/src.zip/src.zip`, `…/platform_probe.py/platform_probe.py`. Layout notes: `src: ../../src/bob_killer` zips without the package prefix; glob artifacts need `enable_snowpark_glob_support` and then reject sources outside the project root. The build writes `labs/bob_killer/src.zip`; the test removes it. |
| F9 | TRUE | `session.call(..., block=False)` returns an `AsyncJob`; `is_done()` is true after `result()`. |
| F10 | Phase 5 | — |

Compute pool: `BOB_KILLER_POOL` `auto_suspend_secs = 300` and state `SUSPENDED` after `ALTER COMPUTE POOL … SUSPEND`.
Teardown: `hosts/snowflake/sql/99_teardown.sql` with the hello schema dropped it (`SHOW SCHEMAS` no longer lists it).
`BOB_KILLER_OWNER` exists and is the session role (`tests/live/test_connection.py`).

# Raw command log

## hosts/snowflake/snowflake.yml

_2026-10-16T19:51:40.750404+00:00_

```text
definition_version: 2
# Snowflake CLI project for the Bob Killer host (docs/SPEC.md §4 F8, G13).
# `snow snowpark build` zips the artifacts; `snow snowpark deploy` uploads the zip and creates
# the procedures. The core ships from ../../src/bob_killer through an artifact src/dest mapping.
mixins:
  snowpark_shared:
    stage: deployments
    artifacts:
      - src: ../../src
        dest: src.zip
      - src: probe/platform_probe.py
        dest: platform_probe.py
entities:
  platform_probe:
    type: procedure
    identifier:
      name: PLATFORM_PROBE
    handler: platform_probe.platform_probe
    runtime: "3.12"
    signature:
      - name: stage_path
        type: string
    returns: variant
    execute_as_caller: false
    meta:
      use_mixins:
        - snowpark_shared
```

## hosts/snowflake/requirements.txt

_2026-10-16T19:51:40.751396+00:00_

```text
snowflake-snowpark-python
pydantic>=2.11,<2.12
```

## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-16T19:52:02.976146+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark deploy --schema TEST_BE2C19CF -c bob_killer --project hosts/snowflake

_2026-10-16T19:52:40.936537+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading platform_probe.py to @BOB_KILLER.TEST_BE2C19CF.deployments/platform_probe.py/
  Uploading src.zip to @BOB_KILLER.TEST_BE2C19CF.deployments/src.zip/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
+----------------------------------------------------------------------------------+
| object                                                     | type      | status  |
|------------------------------------------------------------+-----------+---------|
| BOB_KILLER.TEST_BE2C19CF.PLATFORM_PROBE(stage_path string) | procedure | created |
+----------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## CALL PLATFORM_PROBE(<staged file>)

_2026-10-16T19:52:48.378250+00:00_

```text
{
  "current_schema": "TEST_BE2C19CF",
  "run_state": "queued",
  "sha256": "1e4bfb53b95a0b7ba9a5056d24c911432467697bdde5c63bc79623381dfbf6e3",
  "sys_version": "3.12.13 | packaged by conda-forge | (main, Mar  5 2026, 16:41:49) [GCC 14.3.0]"
}
```

## F3 pydantic (3.12, Anaconda channel)

_2026-10-16T19:52:49.787272+00:00_

```text
1.10.12, 1.10.19, 2.10.3, 2.11.7, 2.11.9, 2.12.2, 2.12.3, 2.12.4, 2.12.5, 2.13.2, 2.13.4, 2.13.5, 2.5.3, 2.8.2
```

## F3 pydantic-core (3.12, Anaconda channel)

_2026-10-16T19:52:51.190275+00:00_

```text
2.14.6, 2.20.1, 2.21.0, 2.27.1, 2.33.2, 2.39.0, 2.41.4, 2.41.5, 2.42.0, 2.46.2, 2.46.4, 2.46.5
```

## F3 annotated-types (3.12, Anaconda channel)

_2026-10-16T19:52:52.449961+00:00_

```text
0.6.0, 0.7.0
```

## F3 typing-extensions (3.12, Anaconda channel)

_2026-10-16T19:52:53.715468+00:00_

```text
3.10.0.0, 3.10.0.2, 3.7.4.2, 3.7.4.3, 4.1.1, 4.11.0, 4.12.2, 4.15.0, 4.16.0, 4.7.1, 4.9.0
```

## F3 typing-inspection (3.12, Anaconda channel)

_2026-10-16T19:52:54.918836+00:00_

```text
0.4.0, 0.4.2, 0.4.3
```

## F3 openpyxl (3.12, Anaconda channel)

_2026-10-16T19:52:56.673825+00:00_

```text
2.5.14, 2.6.1, 2.6.2, 2.6.3, 3.0.0, 3.0.1, 3.0.10, 3.0.2, 3.0.3, 3.0.4, 3.0.5, 3.0.6, 3.0.7, 3.0.9, 3.1.2, 3.1.5
```

## F3 et-xmlfile (3.12, Anaconda channel)

_2026-10-16T19:52:57.928284+00:00_

```text
MISSING
```

## F3 snowflake-snowpark-python (3.12, Anaconda channel)

_2026-10-16T19:52:59.776063+00:00_

```text
0.4.0, 0.5.0, 0.5.1, 1.12.1a1, 1.13.0a1, 1.14.0a1, 1.14.0a2, 1.27.0, 1.27.0, 1.27.0, 1.27.0, 1.27.0, 1.28.0, 1.28.0, 1.28.0, 1.28.0, 1.28.0, 1.29.0, 1.29.0, 1.29.0, 1.29.0, 1.29.0, 1.29.1, 1.29.1, 1.29.1, 1.29.1, 1.29.1, 1.30.0, 1.30.0, 1.30.0, 1.30.0, 1.30.0, 1.31.1, 1.31.1, 1.31.1, 1.31.1, 1.31.1, 1.32.0, 1.32.0, 1.32.0, 1.32.0, 1.32.0, 1.33.0, 1.33.0, 1.33.0, 1.33.0, 1.33.0, 1.34.0, 1.34.0, 1.34.0, 1.34.0, 1.34.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.37.0, 1.37.0, 1.37.0, 1.37.0, 1.37.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.1, 1.53.1, 1.53.1, 1.53.1, 1.53.1, 1.54.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.1, 1.55.1, 1.55.1, 1.55.1, 1.55.1
```

## F6 LIST @UPLOADS

_2026-10-16T19:53:08.268045+00:00_

```text
[
  {
    "name": "uploads/1e4bfb53b95a0b7ba9a5056d24c911432467697bdde5c63bc79623381dfbf6e3.xlsx",
    "size": 265,
    "md5": "2f46d9e002142f1b05ef94ae94fb7939",
    "last_modified": "Fri, 16 Oct 2026 19:52:43 GMT"
  }
]
```

## F8 DESCRIBE PROCEDURE PLATFORM_PROBE(VARCHAR)

_2026-10-16T19:53:08.474723+00:00_

```text
[
  {
    "property": "signature",
    "value": "(STAGE_PATH VARCHAR)"
  },
  {
    "property": "returns",
    "value": "VARIANT"
  },
  {
    "property": "language",
    "value": "PYTHON"
  },
  {
    "property": "null handling",
    "value": "CALLED ON NULL INPUT"
  },
  {
    "property": "volatility",
    "value": "VOLATILE"
  },
  {
    "property": "execute as",
    "value": "OWNER"
  },
  {
    "property": "body",
    "value": null
  },
  {
    "property": "imports",
    "value": "[@BOB_KILLER.TEST_BE2C19CF.DEPLOYMENTS/src.zip/src.zip, @BOB_KILLER.TEST_BE2C19CF.DEPLOYMENTS/platform_probe.py/platform_probe.py]"
  },
  {
    "property": "handler",
    "value": "platform_probe.platform_probe"
  },
  {
    "property": "runtime_version",
    "value": "3.12"
  },
  {
    "property": "packages",
    "value": "[]"
  },
  {
    "property": "artifact_repository",
    "value": "snowflake.snowpark.pypi_shared_repository"
  },
  {
    "property": "artifact_repository_packages",
    "value": "['snowflake-snowpark-python','pydantic<2.12,>=2.11']"
  },
  {
    "property": "installed_packages",
    "value": "['wheel==0.47.0','readline==8.3','ld_impl_linux-64==2.45.1','libuuid==2.42','liblzma==5.8.3','libxcrypt==4.4.36','icu==78.3','ncurses==6.6','libzlib==1.3.2','libstdcxx==15.2.0','ca-certificates==2026.4.22','libsqlite==3.53.0','libffi==3.5.2','pip==26.0.1','libgcc==15.2.0','bzip2==1.0.8','openssl==3.6.2','setuptools==82.0.1','packaging==26.2','python==3.12.13','_openmp_mutex==4.5','tzdata==2025c','libgomp==15.2.0','libnsl==2.0.1','libgcc-ng==15.2.0','zstd==1.5.7','libexpat==2.7.5','tk==8.6.13','typing_extensions==4.15.0','opentelemetry-api==1.38.0','opentelemetry-sdk==1.38.0','wrapt==2.1.2','python_abi==3.12','typing-extensions==4.15.0','importlib-metadata==8.7.0','opentelemetry-semantic-conventions==0.59b0','zipp==3.23.1','deprecated==1.3.1','snowflake-telemetry-python==0.8.0','ld_impl_linux-aarch64==2.45.1']"
  },
  {
    "property": "artifact_repository_installed_packages",
    "value": "['annotated-types==0.8.0','asn1crypto==1.5.1','boto3==1.43.114','botocore==1.43.114','certifi==2026.7.22','cffi==2.1.1','charset-normalizer==3.5.2','cloudpickle==3.1.2','cryptography==50.0.2','filelock==3.32.7','idna==3.20','jmespath==1.1.0','packaging==26.3','platformdirs==4.13.3','protobuf==6.33.6','pycparser==3.11','pydantic-core==2.33.2','pydantic==2.11.10','pyjwt==2.15.1','pyopenssl==26.4.0','python-dateutil==2.9.0.post0','pytz==2026.5','pyyaml==6.0.3','requests==2.34.2','s3transfer==0.19.2','setuptools==84.0.0','six==1.17.0','snowflake-connector-python==4.8.0','snowflake-snowpark-python==1.55.2','sortedcontainers==2.4.0','tomlkit==0.15.2','typing-extensions==4.16.0','typing-inspection==0.4.4','tzlocal==5.4.4','urllib3==2.8.0','wheel==0.48.0']"
  }
]
```

## F9 session.call(..., block=False)

_2026-10-16T19:53:15.615421+00:00_

```text
AsyncJob is_done=True
{
  "current_schema": "TEST_BE2C19CF",
  "run_state": "queued",
  "sha256": "1e4bfb53b95a0b7ba9a5056d24c911432467697bdde5c63bc79623381dfbf6e3",
  "sys_version": "3.12.13 | packaged by conda-forge | (main, Mar  5 2026, 16:41:49) [GCC 14.3.0]"
}
```

## hosts/snowflake/hello_app/snowflake.yml

_2026-10-16T19:53:15.731523+00:00_

```text
definition_version: 2
# Hello probe (docs/SPEC.md §4 F1, F7). Two copies of one app: with and without the PyPI
# integration. Deployed only into a TEST_<uuid8> schema by tests/live/test_platform.py.
mixins:
  hello_shared:
    query_warehouse: BOB_KILLER_WH
    compute_pool: BOB_KILLER_POOL
    runtime_name: SYSTEM$ST_CONTAINER_RUNTIME_PY3_11
    main_file: streamlit_app.py
    artifacts:
      - streamlit_app.py
      - pyproject.toml
entities:
  hello_eai:
    type: streamlit
    identifier:
      name: HELLO_EAI
    external_access_integrations:
      - BOB_KILLER_PYPI_EAI
    meta:
      use_mixins:
        - hello_shared
  hello_no_eai:
    type: streamlit
    identifier:
      name: HELLO_NO_EAI
    meta:
      use_mixins:
        - hello_shared
```

## $ snow streamlit deploy hello_eai --schema TEST_764DF364 -c bob_killer --project hosts/snowflake/hello_app

_2026-10-16T19:53:39.867129+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_764DF364.HELLO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/hello_app/output/bundle/streamlit/hello_eai.
The following files exist only on the stage:
.streamlit/config.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  modified: pyproject.toml -> pyproject.toml
  modified: streamlit_app.py -> streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/hello_app/output/bundle/streamlit/hello_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_764DF364.HELLO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_EAI

_2026-10-16T19:53:39.972127+00:00_

```text
[
  {
    "title": null,
    "main_file": "streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "sllptd7rxlgiee7beqnf",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[\"BOB_KILLER_PYPI_EAI\"]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_764DF364.HELLO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_764DF364.HELLO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_764DF364.HELLO_EAI/versions/live/"
  }
]
```

## $ snow streamlit deploy hello_no_eai --schema TEST_764DF364 -c bob_killer --project hosts/snowflake/hello_app

_2026-10-16T19:53:55.860997+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_764DF364.HELLO_NO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/hello_app/output/bundle/streamlit/hello_no_eai.
The following files exist only on the stage:
.streamlit/config.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  modified: pyproject.toml -> pyproject.toml
  modified: streamlit_app.py -> streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/hello_app/output/bundle/streamlit/hello_no_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_764DF364.HELLO_NO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_NO_EAI

_2026-10-16T19:53:55.987969+00:00_

```text
[
  {
    "title": null,
    "main_file": "streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "xigsqewqefidc6k5t2pi",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_NO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_764DF364.HELLO_NO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_764DF364.HELLO_NO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_764DF364.HELLO_NO_EAI/versions/live/"
  }
]
```

## Compute pool BOB_KILLER_POOL before and after ALTER ... SUSPEND

_2026-10-16T19:53:56.279818+00:00_

```text
[
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 10:43:57.863000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  },
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 12:53:56.240000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  }
]
```

## 99_teardown.sql

_2026-10-16T19:53:56.465702+00:00_

```text
DROP SCHEMA IF EXISTS IDENTIFIER('BOB_KILLER.TEST_764DF364')
[
  {
    "status": "TEST_764DF364 successfully dropped."
  }
]
```

## hosts/snowflake/snowflake.yml

_2026-10-16T19:56:52.471145+00:00_

```text
definition_version: 2
# Snowflake CLI project for the Bob Killer host (docs/SPEC.md §4 F8, G13).
# `snow snowpark build` zips the artifacts; `snow snowpark deploy` uploads the zip and creates
# the procedures. The core ships from ../../src/bob_killer through an artifact src/dest mapping.
mixins:
  snowpark_shared:
    stage: deployments
    artifacts:
      - src: ../../src
        dest: src.zip
      - src: probe/platform_probe.py
        dest: platform_probe.py
  # Hello probe (spec §4 F1, F7): one app, with and without the PyPI integration. Deployed only
  # into a TEST_<uuid8> schema by tests/live/test_platform.py. Throwaway; not a deploy path.
  hello_shared:
    query_warehouse: BOB_KILLER_WH
    compute_pool: BOB_KILLER_POOL
    runtime_name: SYSTEM$ST_CONTAINER_RUNTIME_PY3_11
    main_file: streamlit_app.py
    artifacts:
      - src: hello_app/streamlit_app.py
        dest: streamlit_app.py
      - src: hello_app/pyproject.toml
        dest: pyproject.toml
entities:
  platform_probe:
    type: procedure
    identifier:
      name: PLATFORM_PROBE
    handler: platform_probe.platform_probe
    runtime: "3.12"
    signature:
      - name: stage_path
        type: string
    returns: variant
    execute_as_caller: false
    meta:
      use_mixins:
        - snowpark_shared
  hello_eai:
    type: streamlit
    identifier:
      name: HELLO_EAI
    external_access_integrations:
      - BOB_KILLER_PYPI_EAI
    meta:
      use_mixins:
        - hello_shared
  hello_no_eai:
    type: streamlit
    identifier:
      name: HELLO_NO_EAI
    meta:
      use_mixins:
        - hello_shared
```

## hosts/snowflake/requirements.txt

_2026-10-16T19:56:52.471705+00:00_

```text
snowflake-snowpark-python
pydantic>=2.11,<2.12
```

## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-16T19:57:13.141199+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark deploy --schema TEST_DD770494 -c bob_killer --project hosts/snowflake

_2026-10-16T19:57:31.166777+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading platform_probe.py to @BOB_KILLER.TEST_DD770494.deployments/platform_probe.py/
  Uploading src.zip to @BOB_KILLER.TEST_DD770494.deployments/src.zip/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
+----------------------------------------------------------------------------------+
| object                                                     | type      | status  |
|------------------------------------------------------------+-----------+---------|
| BOB_KILLER.TEST_DD770494.PLATFORM_PROBE(stage_path string) | procedure | created |
+----------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## CALL PLATFORM_PROBE(<staged file>)

_2026-10-16T19:57:39.377891+00:00_

```text
{
  "current_schema": "TEST_DD770494",
  "run_state": "queued",
  "sha256": "87422e5b4d34053da5254660312cfd88d02b88614072596ee0206398a11e23a3",
  "sys_version": "3.12.13 | packaged by conda-forge | (main, Mar  5 2026, 16:41:49) [GCC 14.3.0]"
}
```

## F3 pydantic (3.12, Anaconda channel)

_2026-10-16T19:57:40.709464+00:00_

```text
1.10.12, 1.10.19, 2.10.3, 2.11.7, 2.11.9, 2.12.2, 2.12.3, 2.12.4, 2.12.5, 2.13.2, 2.13.4, 2.13.5, 2.5.3, 2.8.2
```

## F3 pydantic-core (3.12, Anaconda channel)

_2026-10-16T19:57:41.960586+00:00_

```text
2.14.6, 2.20.1, 2.21.0, 2.27.1, 2.33.2, 2.39.0, 2.41.4, 2.41.5, 2.42.0, 2.46.2, 2.46.4, 2.46.5
```

## F3 annotated-types (3.12, Anaconda channel)

_2026-10-16T19:57:43.898250+00:00_

```text
0.6.0, 0.7.0
```

## F3 typing-extensions (3.12, Anaconda channel)

_2026-10-16T19:57:45.177947+00:00_

```text
3.10.0.0, 3.10.0.2, 3.7.4.2, 3.7.4.3, 4.1.1, 4.11.0, 4.12.2, 4.15.0, 4.16.0, 4.7.1, 4.9.0
```

## F3 typing-inspection (3.12, Anaconda channel)

_2026-10-16T19:57:46.363980+00:00_

```text
0.4.0, 0.4.2, 0.4.3
```

## F3 openpyxl (3.12, Anaconda channel)

_2026-10-16T19:57:47.717495+00:00_

```text
2.5.14, 2.6.1, 2.6.2, 2.6.3, 3.0.0, 3.0.1, 3.0.10, 3.0.2, 3.0.3, 3.0.4, 3.0.5, 3.0.6, 3.0.7, 3.0.9, 3.1.2, 3.1.5
```

## F3 et_xmlfile (3.12, Anaconda channel)

_2026-10-16T19:57:48.998858+00:00_

```text
1.0.1, 1.1.0, 2.0.0
```

## F3 snowflake-snowpark-python (3.12, Anaconda channel)

_2026-10-16T19:57:50.154695+00:00_

```text
0.4.0, 0.5.0, 0.5.1, 1.12.1a1, 1.13.0a1, 1.14.0a1, 1.14.0a2, 1.27.0, 1.27.0, 1.27.0, 1.27.0, 1.27.0, 1.28.0, 1.28.0, 1.28.0, 1.28.0, 1.28.0, 1.29.0, 1.29.0, 1.29.0, 1.29.0, 1.29.0, 1.29.1, 1.29.1, 1.29.1, 1.29.1, 1.29.1, 1.30.0, 1.30.0, 1.30.0, 1.30.0, 1.30.0, 1.31.1, 1.31.1, 1.31.1, 1.31.1, 1.31.1, 1.32.0, 1.32.0, 1.32.0, 1.32.0, 1.32.0, 1.33.0, 1.33.0, 1.33.0, 1.33.0, 1.33.0, 1.34.0, 1.34.0, 1.34.0, 1.34.0, 1.34.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.37.0, 1.37.0, 1.37.0, 1.37.0, 1.37.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.1, 1.53.1, 1.53.1, 1.53.1, 1.53.1, 1.54.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.1, 1.55.1, 1.55.1, 1.55.1, 1.55.1
```

## F4 duplicate PK + NULL into NOT NULL

_2026-10-16T19:57:54.174669+00:00_

```text
rows after 2 duplicate inserts: 2
100072 (22000): DML operation to table TEST_DD770494.F4_PROBE failed on column V with error: NULL result in a non-nullable column
```

## F6 LIST @UPLOADS

_2026-10-16T19:57:54.348821+00:00_

```text
[
  {
    "name": "uploads/87422e5b4d34053da5254660312cfd88d02b88614072596ee0206398a11e23a3.xlsx",
    "size": 265,
    "md5": "57b4243ca9ccb96d8195aa51970cebf6",
    "last_modified": "Fri, 16 Oct 2026 19:57:33 GMT"
  }
]
```

## F8 DESCRIBE PROCEDURE PLATFORM_PROBE(VARCHAR)

_2026-10-16T19:57:54.448570+00:00_

```text
[
  {
    "property": "signature",
    "value": "(STAGE_PATH VARCHAR)"
  },
  {
    "property": "returns",
    "value": "VARIANT"
  },
  {
    "property": "language",
    "value": "PYTHON"
  },
  {
    "property": "null handling",
    "value": "CALLED ON NULL INPUT"
  },
  {
    "property": "volatility",
    "value": "VOLATILE"
  },
  {
    "property": "execute as",
    "value": "OWNER"
  },
  {
    "property": "body",
    "value": null
  },
  {
    "property": "imports",
    "value": "[@BOB_KILLER.TEST_DD770494.DEPLOYMENTS/platform_probe.py/platform_probe.py, @BOB_KILLER.TEST_DD770494.DEPLOYMENTS/src.zip/src.zip]"
  },
  {
    "property": "handler",
    "value": "platform_probe.platform_probe"
  },
  {
    "property": "runtime_version",
    "value": "3.12"
  },
  {
    "property": "packages",
    "value": "[]"
  },
  {
    "property": "artifact_repository",
    "value": "snowflake.snowpark.pypi_shared_repository"
  },
  {
    "property": "artifact_repository_packages",
    "value": "['snowflake-snowpark-python','pydantic<2.12,>=2.11']"
  },
  {
    "property": "installed_packages",
    "value": "['wheel==0.47.0','readline==8.3','ld_impl_linux-64==2.45.1','libuuid==2.42','liblzma==5.8.3','libxcrypt==4.4.36','icu==78.3','ncurses==6.6','libzlib==1.3.2','libstdcxx==15.2.0','ca-certificates==2026.4.22','libsqlite==3.53.0','libffi==3.5.2','pip==26.0.1','libgcc==15.2.0','bzip2==1.0.8','openssl==3.6.2','setuptools==82.0.1','packaging==26.2','python==3.12.13','_openmp_mutex==4.5','tzdata==2025c','libgomp==15.2.0','libnsl==2.0.1','libgcc-ng==15.2.0','zstd==1.5.7','libexpat==2.7.5','tk==8.6.13','typing_extensions==4.15.0','opentelemetry-api==1.38.0','opentelemetry-sdk==1.38.0','wrapt==2.1.2','python_abi==3.12','typing-extensions==4.15.0','importlib-metadata==8.7.0','opentelemetry-semantic-conventions==0.59b0','zipp==3.23.1','deprecated==1.3.1','snowflake-telemetry-python==0.8.0','ld_impl_linux-aarch64==2.45.1']"
  },
  {
    "property": "artifact_repository_installed_packages",
    "value": "['annotated-types==0.8.0','asn1crypto==1.5.1','boto3==1.43.114','botocore==1.43.114','certifi==2026.7.22','cffi==2.1.1','charset-normalizer==3.5.2','cloudpickle==3.1.2','cryptography==50.0.2','filelock==3.32.7','idna==3.20','jmespath==1.1.0','packaging==26.3','platformdirs==4.13.3','protobuf==6.33.6','pycparser==3.11','pydantic-core==2.33.2','pydantic==2.11.10','pyjwt==2.15.1','pyopenssl==26.4.0','python-dateutil==2.9.0.post0','pytz==2026.5','pyyaml==6.0.3','requests==2.34.2','s3transfer==0.19.2','setuptools==84.0.0','six==1.17.0','snowflake-connector-python==4.8.0','snowflake-snowpark-python==1.55.2','sortedcontainers==2.4.0','tomlkit==0.15.2','typing-extensions==4.16.0','typing-inspection==0.4.4','tzlocal==5.4.4','urllib3==2.8.0','wheel==0.48.0']"
  }
]
```

## F9 session.call(..., block=False)

_2026-10-16T19:57:58.734655+00:00_

```text
AsyncJob is_done=True
{
  "current_schema": "TEST_DD770494",
  "run_state": "queued",
  "sha256": "87422e5b4d34053da5254660312cfd88d02b88614072596ee0206398a11e23a3",
  "sys_version": "3.12.13 | packaged by conda-forge | (main, Mar  5 2026, 16:41:49) [GCC 14.3.0]"
}
```

## $ snow streamlit deploy hello_eai --schema TEST_C40F8577 -c bob_killer --project hosts/snowflake

_2026-10-16T19:58:19.304846+00:00_

```text
exit 1
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ No match was found for the specified source in the project directory         │
│ : streamlit_app.py                                                           │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## $ snow streamlit deploy hello_eai --schema TEST_45FE154A -c bob_killer --project hosts/snowflake

_2026-10-16T19:59:33.433871+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_45FE154A.HELLO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_eai.
The following files exist only on the stage:
hello_app/.streamlit/config.toml
hello_app/pyproject.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  added:    hello_app/pyproject.toml -> pyproject.toml
  modified: hello_app/streamlit_app.py -> hello_app/streamlit_app.py
  added:    hello_app/streamlit_app.py -> streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_45FE154A.HELLO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_EAI

_2026-10-16T19:59:33.556769+00:00_

```text
[
  {
    "title": null,
    "main_file": "hello_app/streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "o2hcapihnjpdoz2ldb2p",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[\"BOB_KILLER_PYPI_EAI\"]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_45FE154A.HELLO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_45FE154A.HELLO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_45FE154A.HELLO_EAI/versions/live/"
  }
]
```

## $ snow streamlit deploy hello_no_eai --schema TEST_45FE154A -c bob_killer --project hosts/snowflake

_2026-10-16T19:59:55.360403+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_45FE154A.HELLO_NO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_no_eai.
The following files exist only on the stage:
hello_app/.streamlit/config.toml
hello_app/pyproject.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  added:    hello_app/pyproject.toml -> pyproject.toml
  modified: hello_app/streamlit_app.py -> hello_app/streamlit_app.py
  added:    hello_app/streamlit_app.py -> streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_no_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_45FE154A.HELLO_NO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_NO_EAI

_2026-10-16T19:59:55.459935+00:00_

```text
[
  {
    "title": null,
    "main_file": "hello_app/streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "c4g64yeezirnszligp4z",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_NO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_45FE154A.HELLO_NO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_45FE154A.HELLO_NO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_45FE154A.HELLO_NO_EAI/versions/live/"
  }
]
```

## Compute pool BOB_KILLER_POOL before and after ALTER ... SUSPEND

_2026-10-16T19:59:55.745057+00:00_

```text
[
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 12:53:56.240000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  },
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 12:59:55.689000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  }
]
```

## 99_teardown.sql

_2026-10-16T19:59:55.904356+00:00_

```text
DROP SCHEMA IF EXISTS IDENTIFIER('BOB_KILLER.TEST_45FE154A')
[
  {
    "status": "TEST_45FE154A successfully dropped."
  }
]
```

## $ snow streamlit deploy hello_eai --schema TEST_CBED1A6C -c bob_killer --project hosts/snowflake

_2026-10-16T20:01:13.344842+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_CBED1A6C.HELLO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_eai.
The following files exist only on the stage:
hello_app/.streamlit/config.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  modified: hello_app/pyproject.toml -> hello_app/pyproject.toml
  modified: hello_app/streamlit_app.py -> hello_app/streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_CBED1A6C.HELLO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_EAI

_2026-10-16T20:01:13.588087+00:00_

```text
[
  {
    "title": null,
    "main_file": "hello_app/streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "hjn2lol57eow54nmorye",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[\"BOB_KILLER_PYPI_EAI\"]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_CBED1A6C.HELLO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_CBED1A6C.HELLO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_CBED1A6C.HELLO_EAI/versions/live/"
  }
]
```

## $ snow streamlit deploy hello_no_eai --schema TEST_CBED1A6C -c bob_killer --project hosts/snowflake

_2026-10-16T20:01:28.185656+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_CBED1A6C.HELLO_NO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_no_eai.
The following files exist only on the stage:
hello_app/.streamlit/config.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  modified: hello_app/pyproject.toml -> hello_app/pyproject.toml
  modified: hello_app/streamlit_app.py -> hello_app/streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_no_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_CBED1A6C.HELLO_NO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_NO_EAI

_2026-10-16T20:01:28.330476+00:00_

```text
[
  {
    "title": null,
    "main_file": "hello_app/streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "ikqzu6a4uimldx2qxfbl",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_NO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_CBED1A6C.HELLO_NO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_CBED1A6C.HELLO_NO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_CBED1A6C.HELLO_NO_EAI/versions/live/"
  }
]
```

## Compute pool BOB_KILLER_POOL before and after ALTER ... SUSPEND

_2026-10-16T20:01:28.697586+00:00_

```text
[
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 12:59:55.689000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  },
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 13:01:28.559000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  }
]
```

## 99_teardown.sql

_2026-10-16T20:01:28.834796+00:00_

```text
DROP SCHEMA IF EXISTS IDENTIFIER('BOB_KILLER.TEST_CBED1A6C')
[
  {
    "status": "TEST_CBED1A6C successfully dropped."
  }
]
```

## hosts/snowflake/snowflake.yml

_2026-10-16T20:09:15.332080+00:00_

```text
definition_version: 2
# Snowflake CLI project for the Bob Killer host (docs/SPEC.md §4 F8, G13).
# `snow snowpark build` zips the artifacts; `snow snowpark deploy` uploads the zip and creates
# the procedures. The core ships from ../../src/bob_killer through an artifact src/dest mapping.
mixins:
  snowpark_shared:
    stage: deployments
    artifacts:
      - src: ../../src
        dest: src.zip
      - src: probe/platform_probe.py
        dest: platform_probe.py
  # Hello probe (spec §4 F1, F7): one app, with and without the PyPI integration. Deployed only
  # into a TEST_<uuid8> schema by tests/live/test_platform.py. Throwaway; not a deploy path.
  hello_shared:
    query_warehouse: BOB_KILLER_WH
    compute_pool: BOB_KILLER_POOL
    runtime_name: SYSTEM$ST_CONTAINER_RUNTIME_PY3_11
    main_file: hello_app/streamlit_app.py
    artifacts:
      - hello_app/streamlit_app.py
      - hello_app/pyproject.toml
entities:
  platform_probe:
    type: procedure
    identifier:
      name: PLATFORM_PROBE
    handler: platform_probe.platform_probe
    runtime: "3.12"
    signature:
      - name: stage_path
        type: string
    returns: variant
    execute_as_caller: false
    meta:
      use_mixins:
        - snowpark_shared
  hello_eai:
    type: streamlit
    identifier:
      name: HELLO_EAI
    external_access_integrations:
      - BOB_KILLER_PYPI_EAI
    meta:
      use_mixins:
        - hello_shared
  hello_no_eai:
    type: streamlit
    identifier:
      name: HELLO_NO_EAI
    meta:
      use_mixins:
        - hello_shared
```

## hosts/snowflake/requirements.txt

_2026-10-16T20:09:15.334156+00:00_

```text
snowflake-snowpark-python
pydantic>=2.11,<2.12
```

## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-16T20:09:25.435941+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark deploy --schema TEST_46F0D24A -c bob_killer --project hosts/snowflake

_2026-10-16T20:09:36.515152+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading platform_probe.py to @BOB_KILLER.TEST_46F0D24A.deployments/platform_probe.py/
  Uploading src.zip to @BOB_KILLER.TEST_46F0D24A.deployments/src.zip/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
+----------------------------------------------------------------------------------+
| object                                                     | type      | status  |
|------------------------------------------------------------+-----------+---------|
| BOB_KILLER.TEST_46F0D24A.PLATFORM_PROBE(stage_path string) | procedure | created |
+----------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## CALL PLATFORM_PROBE(<staged file>)

_2026-10-16T20:09:43.895372+00:00_

```text
{
  "current_schema": "TEST_46F0D24A",
  "run_state": "queued",
  "sha256": "d6d6c707a80ace496ad20040243b87a900736fea3e5b3a389cd3f46b6411a9bc",
  "sys_version": "3.12.13 | packaged by conda-forge | (main, Mar  5 2026, 16:41:49) [GCC 14.3.0]"
}
```

## F3 pydantic (3.12, Anaconda channel)

_2026-10-16T20:09:45.138024+00:00_

```text
1.10.12, 1.10.19, 2.10.3, 2.11.7, 2.11.9, 2.12.2, 2.12.3, 2.12.4, 2.12.5, 2.13.2, 2.13.4, 2.13.5, 2.5.3, 2.8.2
```

## F3 pydantic-core (3.12, Anaconda channel)

_2026-10-16T20:09:46.921498+00:00_

```text
2.14.6, 2.20.1, 2.21.0, 2.27.1, 2.33.2, 2.39.0, 2.41.4, 2.41.5, 2.42.0, 2.46.2, 2.46.4, 2.46.5
```

## F3 annotated-types (3.12, Anaconda channel)

_2026-10-16T20:09:48.199169+00:00_

```text
0.6.0, 0.7.0
```

## F3 typing-extensions (3.12, Anaconda channel)

_2026-10-16T20:09:49.463432+00:00_

```text
3.10.0.0, 3.10.0.2, 3.7.4.2, 3.7.4.3, 4.1.1, 4.11.0, 4.12.2, 4.15.0, 4.16.0, 4.7.1, 4.9.0
```

## F3 typing-inspection (3.12, Anaconda channel)

_2026-10-16T20:09:50.795838+00:00_

```text
0.4.0, 0.4.2, 0.4.3
```

## F3 openpyxl (3.12, Anaconda channel)

_2026-10-16T20:09:52.222123+00:00_

```text
2.5.14, 2.6.1, 2.6.2, 2.6.3, 3.0.0, 3.0.1, 3.0.10, 3.0.2, 3.0.3, 3.0.4, 3.0.5, 3.0.6, 3.0.7, 3.0.9, 3.1.2, 3.1.5
```

## F3 et_xmlfile (3.12, Anaconda channel)

_2026-10-16T20:09:53.515079+00:00_

```text
1.0.1, 1.1.0, 2.0.0
```

## F3 snowflake-snowpark-python (3.12, Anaconda channel)

_2026-10-16T20:09:54.670457+00:00_

```text
0.4.0, 0.5.0, 0.5.1, 1.12.1a1, 1.13.0a1, 1.14.0a1, 1.14.0a2, 1.27.0, 1.27.0, 1.27.0, 1.27.0, 1.27.0, 1.28.0, 1.28.0, 1.28.0, 1.28.0, 1.28.0, 1.29.0, 1.29.0, 1.29.0, 1.29.0, 1.29.0, 1.29.1, 1.29.1, 1.29.1, 1.29.1, 1.29.1, 1.30.0, 1.30.0, 1.30.0, 1.30.0, 1.30.0, 1.31.1, 1.31.1, 1.31.1, 1.31.1, 1.31.1, 1.32.0, 1.32.0, 1.32.0, 1.32.0, 1.32.0, 1.33.0, 1.33.0, 1.33.0, 1.33.0, 1.33.0, 1.34.0, 1.34.0, 1.34.0, 1.34.0, 1.34.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.37.0, 1.37.0, 1.37.0, 1.37.0, 1.37.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.1, 1.53.1, 1.53.1, 1.53.1, 1.53.1, 1.54.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.1, 1.55.1, 1.55.1, 1.55.1, 1.55.1
```

## F4 duplicate PK + NULL into NOT NULL

_2026-10-16T20:09:58.412678+00:00_

```text
rows after 2 duplicate inserts: 2
100072 (22000): DML operation to table TEST_46F0D24A.F4_PROBE failed on column V with error: NULL result in a non-nullable column
```

## F6 LIST @UPLOADS

_2026-10-16T20:09:58.521802+00:00_

```text
[
  {
    "name": "uploads/d6d6c707a80ace496ad20040243b87a900736fea3e5b3a389cd3f46b6411a9bc.xlsx",
    "size": 265,
    "md5": "ad9da2b1ce0a43d3178f672698469134",
    "last_modified": "Fri, 16 Oct 2026 20:09:38 GMT"
  }
]
```

## F8 DESCRIBE PROCEDURE PLATFORM_PROBE(VARCHAR)

_2026-10-16T20:09:58.585030+00:00_

```text
[
  {
    "property": "signature",
    "value": "(STAGE_PATH VARCHAR)"
  },
  {
    "property": "returns",
    "value": "VARIANT"
  },
  {
    "property": "language",
    "value": "PYTHON"
  },
  {
    "property": "null handling",
    "value": "CALLED ON NULL INPUT"
  },
  {
    "property": "volatility",
    "value": "VOLATILE"
  },
  {
    "property": "execute as",
    "value": "OWNER"
  },
  {
    "property": "body",
    "value": null
  },
  {
    "property": "imports",
    "value": "[@BOB_KILLER.TEST_46F0D24A.DEPLOYMENTS/platform_probe.py/platform_probe.py, @BOB_KILLER.TEST_46F0D24A.DEPLOYMENTS/src.zip/src.zip]"
  },
  {
    "property": "handler",
    "value": "platform_probe.platform_probe"
  },
  {
    "property": "runtime_version",
    "value": "3.12"
  },
  {
    "property": "packages",
    "value": "[]"
  },
  {
    "property": "artifact_repository",
    "value": "snowflake.snowpark.pypi_shared_repository"
  },
  {
    "property": "artifact_repository_packages",
    "value": "['snowflake-snowpark-python','pydantic<2.12,>=2.11']"
  },
  {
    "property": "installed_packages",
    "value": "['wheel==0.47.0','readline==8.3','ld_impl_linux-64==2.45.1','libuuid==2.42','liblzma==5.8.3','libxcrypt==4.4.36','icu==78.3','ncurses==6.6','libzlib==1.3.2','libstdcxx==15.2.0','ca-certificates==2026.4.22','libsqlite==3.53.0','libffi==3.5.2','pip==26.0.1','libgcc==15.2.0','bzip2==1.0.8','openssl==3.6.2','setuptools==82.0.1','packaging==26.2','python==3.12.13','_openmp_mutex==4.5','tzdata==2025c','libgomp==15.2.0','libnsl==2.0.1','libgcc-ng==15.2.0','zstd==1.5.7','libexpat==2.7.5','tk==8.6.13','typing_extensions==4.15.0','opentelemetry-api==1.38.0','opentelemetry-sdk==1.38.0','wrapt==2.1.2','python_abi==3.12','typing-extensions==4.15.0','importlib-metadata==8.7.0','opentelemetry-semantic-conventions==0.59b0','zipp==3.23.1','deprecated==1.3.1','snowflake-telemetry-python==0.8.0','ld_impl_linux-aarch64==2.45.1']"
  },
  {
    "property": "artifact_repository_installed_packages",
    "value": "['annotated-types==0.8.0','asn1crypto==1.5.1','boto3==1.43.114','botocore==1.43.114','certifi==2026.7.22','cffi==2.1.1','charset-normalizer==3.5.2','cloudpickle==3.1.2','cryptography==50.0.2','filelock==3.32.7','idna==3.20','jmespath==1.1.0','packaging==26.3','platformdirs==4.13.3','protobuf==6.33.6','pycparser==3.11','pydantic-core==2.33.2','pydantic==2.11.10','pyjwt==2.15.1','pyopenssl==26.4.0','python-dateutil==2.9.0.post0','pytz==2026.5','pyyaml==6.0.3','requests==2.34.2','s3transfer==0.19.2','setuptools==84.0.0','six==1.17.0','snowflake-connector-python==4.8.0','snowflake-snowpark-python==1.55.2','sortedcontainers==2.4.0','tomlkit==0.15.2','typing-extensions==4.16.0','typing-inspection==0.4.4','tzlocal==5.4.4','urllib3==2.8.0','wheel==0.48.0']"
  }
]
```

## F9 session.call(..., block=False)

_2026-10-16T20:10:01.209032+00:00_

```text
AsyncJob is_done=True
{
  "current_schema": "TEST_46F0D24A",
  "run_state": "queued",
  "sha256": "d6d6c707a80ace496ad20040243b87a900736fea3e5b3a389cd3f46b6411a9bc",
  "sys_version": "3.12.13 | packaged by conda-forge | (main, Mar  5 2026, 16:41:49) [GCC 14.3.0]"
}
```

## $ snow streamlit deploy hello_eai --schema TEST_2EC42066 -c bob_killer --project hosts/snowflake

_2026-10-16T20:10:12.183727+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_2EC42066.HELLO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_eai.
The following files exist only on the stage:
hello_app/.streamlit/config.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  modified: hello_app/pyproject.toml -> hello_app/pyproject.toml
  modified: hello_app/streamlit_app.py -> hello_app/streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_2EC42066.HELLO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_EAI

_2026-10-16T20:10:12.296156+00:00_

```text
[
  {
    "title": null,
    "main_file": "hello_app/streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "wjooxv436dwvvrnovsdq",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[\"BOB_KILLER_PYPI_EAI\"]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_2EC42066.HELLO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_2EC42066.HELLO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_2EC42066.HELLO_EAI/versions/live/"
  }
]
```

## $ snow streamlit deploy hello_no_eai --schema TEST_2EC42066 -c bob_killer --project hosts/snowflake

_2026-10-16T20:10:23.848585+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_2EC42066.HELLO_NO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_no_eai.
The following files exist only on the stage:
hello_app/.streamlit/config.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  modified: hello_app/pyproject.toml -> hello_app/pyproject.toml
  modified: hello_app/streamlit_app.py -> hello_app/streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_no_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_2EC42066.HELLO_NO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake-coco-p2/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_NO_EAI

_2026-10-16T20:10:24.168244+00:00_

```text
[
  {
    "title": null,
    "main_file": "hello_app/streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "okmt25e3e6zcmh7byhtc",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_NO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_2EC42066.HELLO_NO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_2EC42066.HELLO_NO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_2EC42066.HELLO_NO_EAI/versions/live/"
  }
]
```

## Compute pool BOB_KILLER_POOL before and after ALTER ... SUSPEND

_2026-10-16T20:10:24.750154+00:00_

```text
[
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 13:01:28.559000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  },
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 13:10:24.573000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  }
]
```

## 99_teardown.sql

_2026-10-16T20:10:24.914860+00:00_

```text
DROP SCHEMA IF EXISTS IDENTIFIER('BOB_KILLER.TEST_2EC42066')
[
  {
    "status": "TEST_2EC42066 successfully dropped."
  }
]
```

## hosts/snowflake/snowflake.yml

_2026-10-16T20:36:31.200003+00:00_

```text
definition_version: 2
# Snowflake CLI project for the Bob Killer host (docs/SPEC.md §4 F8, G13).
# `snow snowpark build` zips the artifacts; `snow snowpark deploy` uploads the zip and creates
# the procedures. The core ships from ../../src/bob_killer through an artifact src/dest mapping.
mixins:
  snowpark_shared:
    stage: deployments
    artifacts:
      - src: ../../src
        dest: src.zip
      - src: probe/platform_probe.py
        dest: platform_probe.py
  # Hello probe (spec §4 F1, F7): one app, with and without the PyPI integration. Deployed only
  # into a TEST_<uuid8> schema by tests/live/test_platform.py. Throwaway; not a deploy path.
  hello_shared:
    query_warehouse: BOB_KILLER_WH
    compute_pool: BOB_KILLER_POOL
    runtime_name: SYSTEM$ST_CONTAINER_RUNTIME_PY3_11
    main_file: hello_app/streamlit_app.py
    artifacts:
      - hello_app/streamlit_app.py
      - hello_app/pyproject.toml
entities:
  platform_probe:
    type: procedure
    identifier:
      name: PLATFORM_PROBE
    handler: platform_probe.platform_probe
    runtime: "3.12"
    signature:
      - name: stage_path
        type: string
    returns: variant
    execute_as_caller: false
    meta:
      use_mixins:
        - snowpark_shared
  hello_eai:
    type: streamlit
    identifier:
      name: HELLO_EAI
    external_access_integrations:
      - BOB_KILLER_PYPI_EAI
    meta:
      use_mixins:
        - hello_shared
  hello_no_eai:
    type: streamlit
    identifier:
      name: HELLO_NO_EAI
    meta:
      use_mixins:
        - hello_shared
```

## hosts/snowflake/requirements.txt

_2026-10-16T20:36:31.200586+00:00_

```text
snowflake-snowpark-python
pydantic>=2.11,<2.12
```

## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-16T20:36:55.062230+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark deploy --schema TEST_72B273C6 -c bob_killer --project hosts/snowflake

_2026-10-16T20:37:13.909946+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading src.zip to @BOB_KILLER.TEST_72B273C6.deployments/src.zip/
  Uploading platform_probe.py to @BOB_KILLER.TEST_72B273C6.deployments/platform_probe.py/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
+----------------------------------------------------------------------------------+
| object                                                     | type      | status  |
|------------------------------------------------------------+-----------+---------|
| BOB_KILLER.TEST_72B273C6.PLATFORM_PROBE(stage_path string) | procedure | created |
+----------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## CALL PLATFORM_PROBE(<staged file>)

_2026-10-16T20:37:23.175515+00:00_

```text
{
  "current_schema": "TEST_72B273C6",
  "run_state": "queued",
  "sha256": "29a799a6dc41231dd0b2caed863236283b01021b972fd56c338edec15e057cdd",
  "sys_version": "3.12.13 | packaged by conda-forge | (main, Mar  5 2026, 16:41:49) [GCC 14.3.0]"
}
```

## F3 pydantic (3.12, Anaconda channel)

_2026-10-16T20:37:24.798248+00:00_

```text
1.10.12, 1.10.19, 2.10.3, 2.11.7, 2.11.9, 2.12.2, 2.12.3, 2.12.4, 2.12.5, 2.13.2, 2.13.4, 2.13.5, 2.5.3, 2.8.2
```

## F3 pydantic-core (3.12, Anaconda channel)

_2026-10-16T20:37:26.419706+00:00_

```text
2.14.6, 2.20.1, 2.21.0, 2.27.1, 2.33.2, 2.39.0, 2.41.4, 2.41.5, 2.42.0, 2.46.2, 2.46.4, 2.46.5
```

## F3 annotated-types (3.12, Anaconda channel)

_2026-10-16T20:37:28.550243+00:00_

```text
0.6.0, 0.7.0
```

## F3 typing-extensions (3.12, Anaconda channel)

_2026-10-16T20:37:29.925376+00:00_

```text
3.10.0.0, 3.10.0.2, 3.7.4.2, 3.7.4.3, 4.1.1, 4.11.0, 4.12.2, 4.15.0, 4.16.0, 4.7.1, 4.9.0
```

## F3 typing-inspection (3.12, Anaconda channel)

_2026-10-16T20:37:31.353191+00:00_

```text
0.4.0, 0.4.2, 0.4.3
```

## F3 openpyxl (3.12, Anaconda channel)

_2026-10-16T20:37:33.463998+00:00_

```text
2.5.14, 2.6.1, 2.6.2, 2.6.3, 3.0.0, 3.0.1, 3.0.10, 3.0.2, 3.0.3, 3.0.4, 3.0.5, 3.0.6, 3.0.7, 3.0.9, 3.1.2, 3.1.5
```

## F3 et_xmlfile (3.12, Anaconda channel)

_2026-10-16T20:37:34.795911+00:00_

```text
1.0.1, 1.1.0, 2.0.0
```

## F3 snowflake-snowpark-python (3.12, Anaconda channel)

_2026-10-16T20:37:36.053095+00:00_

```text
0.4.0, 0.5.0, 0.5.1, 1.12.1a1, 1.13.0a1, 1.14.0a1, 1.14.0a2, 1.27.0, 1.27.0, 1.27.0, 1.27.0, 1.27.0, 1.28.0, 1.28.0, 1.28.0, 1.28.0, 1.28.0, 1.29.0, 1.29.0, 1.29.0, 1.29.0, 1.29.0, 1.29.1, 1.29.1, 1.29.1, 1.29.1, 1.29.1, 1.30.0, 1.30.0, 1.30.0, 1.30.0, 1.30.0, 1.31.1, 1.31.1, 1.31.1, 1.31.1, 1.31.1, 1.32.0, 1.32.0, 1.32.0, 1.32.0, 1.32.0, 1.33.0, 1.33.0, 1.33.0, 1.33.0, 1.33.0, 1.34.0, 1.34.0, 1.34.0, 1.34.0, 1.34.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.37.0, 1.37.0, 1.37.0, 1.37.0, 1.37.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.1, 1.53.1, 1.53.1, 1.53.1, 1.53.1, 1.54.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.1, 1.55.1, 1.55.1, 1.55.1, 1.55.1
```

## F4 duplicate PK + NULL into NOT NULL

_2026-10-16T20:37:41.389586+00:00_

```text
rows after 2 duplicate inserts: 2
100072 (22000): DML operation to table TEST_72B273C6.F4_PROBE failed on column V with error: NULL result in a non-nullable column
```

## F6 LIST @UPLOADS

_2026-10-16T20:37:41.693884+00:00_

```text
[
  {
    "name": "uploads/29a799a6dc41231dd0b2caed863236283b01021b972fd56c338edec15e057cdd.xlsx",
    "size": 265,
    "md5": "12df8685b07bca5bb177620f19cf18a0",
    "last_modified": "Fri, 16 Oct 2026 20:37:16 GMT"
  }
]
```

## F8 DESCRIBE PROCEDURE PLATFORM_PROBE(VARCHAR)

_2026-10-16T20:37:41.790522+00:00_

```text
[
  {
    "property": "signature",
    "value": "(STAGE_PATH VARCHAR)"
  },
  {
    "property": "returns",
    "value": "VARIANT"
  },
  {
    "property": "language",
    "value": "PYTHON"
  },
  {
    "property": "null handling",
    "value": "CALLED ON NULL INPUT"
  },
  {
    "property": "volatility",
    "value": "VOLATILE"
  },
  {
    "property": "execute as",
    "value": "OWNER"
  },
  {
    "property": "body",
    "value": null
  },
  {
    "property": "imports",
    "value": "[@BOB_KILLER.TEST_72B273C6.DEPLOYMENTS/platform_probe.py/platform_probe.py, @BOB_KILLER.TEST_72B273C6.DEPLOYMENTS/src.zip/src.zip]"
  },
  {
    "property": "handler",
    "value": "platform_probe.platform_probe"
  },
  {
    "property": "runtime_version",
    "value": "3.12"
  },
  {
    "property": "packages",
    "value": "[]"
  },
  {
    "property": "artifact_repository",
    "value": "snowflake.snowpark.pypi_shared_repository"
  },
  {
    "property": "artifact_repository_packages",
    "value": "['snowflake-snowpark-python','pydantic<2.12,>=2.11']"
  },
  {
    "property": "installed_packages",
    "value": "['wheel==0.47.0','readline==8.3','ld_impl_linux-64==2.45.1','libuuid==2.42','liblzma==5.8.3','libxcrypt==4.4.36','icu==78.3','ncurses==6.6','libzlib==1.3.2','libstdcxx==15.2.0','ca-certificates==2026.4.22','libsqlite==3.53.0','libffi==3.5.2','pip==26.0.1','libgcc==15.2.0','bzip2==1.0.8','openssl==3.6.2','setuptools==82.0.1','packaging==26.2','python==3.12.13','_openmp_mutex==4.5','tzdata==2025c','libgomp==15.2.0','libnsl==2.0.1','libgcc-ng==15.2.0','zstd==1.5.7','libexpat==2.7.5','tk==8.6.13','typing_extensions==4.15.0','opentelemetry-api==1.38.0','opentelemetry-sdk==1.38.0','wrapt==2.1.2','python_abi==3.12','typing-extensions==4.15.0','importlib-metadata==8.7.0','opentelemetry-semantic-conventions==0.59b0','zipp==3.23.1','deprecated==1.3.1','snowflake-telemetry-python==0.8.0','ld_impl_linux-aarch64==2.45.1']"
  },
  {
    "property": "artifact_repository_installed_packages",
    "value": "['annotated-types==0.8.0','asn1crypto==1.5.1','boto3==1.43.114','botocore==1.43.114','certifi==2026.7.22','cffi==2.1.1','charset-normalizer==3.5.2','cloudpickle==3.1.2','cryptography==50.0.2','filelock==3.32.7','idna==3.20','jmespath==1.1.0','packaging==26.3','platformdirs==4.13.3','protobuf==6.33.6','pycparser==3.11','pydantic-core==2.33.2','pydantic==2.11.10','pyjwt==2.15.1','pyopenssl==26.4.0','python-dateutil==2.9.0.post0','pytz==2026.5','pyyaml==6.0.3','requests==2.34.2','s3transfer==0.19.2','setuptools==84.0.0','six==1.17.0','snowflake-connector-python==4.8.0','snowflake-snowpark-python==1.55.2','sortedcontainers==2.4.0','tomlkit==0.15.2','typing-extensions==4.16.0','typing-inspection==0.4.4','tzlocal==5.4.4','urllib3==2.8.0','wheel==0.48.0']"
  }
]
```

## F9 session.call(..., block=False)

_2026-10-16T20:37:46.393548+00:00_

```text
AsyncJob is_done=True
{
  "current_schema": "TEST_72B273C6",
  "run_state": "queued",
  "sha256": "29a799a6dc41231dd0b2caed863236283b01021b972fd56c338edec15e057cdd",
  "sys_version": "3.12.13 | packaged by conda-forge | (main, Mar  5 2026, 16:41:49) [GCC 14.3.0]"
}
```

## $ snow streamlit deploy hello_eai --schema TEST_D03E2610 -c bob_killer --project hosts/snowflake

_2026-10-16T20:38:13.023492+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_D03E2610.HELLO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_eai.
The following files exist only on the stage:
hello_app/.streamlit/config.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  modified: hello_app/pyproject.toml -> hello_app/pyproject.toml
  modified: hello_app/streamlit_app.py -> hello_app/streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_D03E2610.HELLO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_EAI

_2026-10-16T20:38:13.324945+00:00_

```text
[
  {
    "title": null,
    "main_file": "hello_app/streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "ekjf6y7qz5ekplh22edk",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[\"BOB_KILLER_PYPI_EAI\"]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_D03E2610.HELLO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_D03E2610.HELLO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_D03E2610.HELLO_EAI/versions/live/"
  }
]
```

## $ snow streamlit deploy hello_no_eai --schema TEST_D03E2610 -c bob_killer --project hosts/snowflake

_2026-10-16T20:38:48.876711+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_D03E2610.HELLO_NO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_no_eai.
The following files exist only on the stage:
hello_app/.streamlit/config.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  modified: hello_app/pyproject.toml -> hello_app/pyproject.toml
  modified: hello_app/streamlit_app.py -> hello_app/streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_no_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_D03E2610.HELLO_NO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_NO_EAI

_2026-10-16T20:38:49.275203+00:00_

```text
[
  {
    "title": null,
    "main_file": "hello_app/streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "xgnxrpp4aadsz6xyazck",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_NO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_D03E2610.HELLO_NO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_D03E2610.HELLO_NO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_D03E2610.HELLO_NO_EAI/versions/live/"
  }
]
```

## Compute pool BOB_KILLER_POOL before and after ALTER ... SUSPEND

_2026-10-16T20:38:49.872325+00:00_

```text
[
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 13:10:24.573000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  },
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 13:38:49.572000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  }
]
```

## 99_teardown.sql

_2026-10-16T20:38:50.101407+00:00_

```text
DROP SCHEMA IF EXISTS IDENTIFIER('BOB_KILLER.TEST_D03E2610')
[
  {
    "status": "TEST_D03E2610 successfully dropped."
  }
]
```

## hosts/snowflake/snowflake.yml

_2026-10-16T21:09:30.516400+00:00_

```text
definition_version: 2
# Snowflake CLI project for the Bob Killer host (docs/SPEC.md §4 F8, G13).
# `snow snowpark build` zips the artifacts; `snow snowpark deploy` uploads the zip and creates
# the procedures. The core ships from ../../src/bob_killer through an artifact src/dest mapping.
mixins:
  snowpark_shared:
    stage: deployments
    artifacts:
      - src: ../../src
        dest: src.zip
      - src: probe/platform_probe.py
        dest: platform_probe.py
  # Hello probe (spec §4 F1, F7): one app, with and without the PyPI integration. Deployed only
  # into a TEST_<uuid8> schema by tests/live/test_platform.py. Throwaway; not a deploy path.
  hello_shared:
    query_warehouse: BOB_KILLER_WH
    compute_pool: BOB_KILLER_POOL
    runtime_name: SYSTEM$ST_CONTAINER_RUNTIME_PY3_11
    main_file: hello_app/streamlit_app.py
    artifacts:
      - hello_app/streamlit_app.py
      - hello_app/pyproject.toml
entities:
  platform_probe:
    type: procedure
    identifier:
      name: PLATFORM_PROBE
    handler: platform_probe.platform_probe
    runtime: "3.12"
    signature:
      - name: stage_path
        type: string
    returns: variant
    execute_as_caller: false
    meta:
      use_mixins:
        - snowpark_shared
  hello_eai:
    type: streamlit
    identifier:
      name: HELLO_EAI
    external_access_integrations:
      - BOB_KILLER_PYPI_EAI
    meta:
      use_mixins:
        - hello_shared
  hello_no_eai:
    type: streamlit
    identifier:
      name: HELLO_NO_EAI
    meta:
      use_mixins:
        - hello_shared
```

## hosts/snowflake/requirements.txt

_2026-10-16T21:09:30.518588+00:00_

```text
snowflake-snowpark-python
pydantic>=2.11,<2.12
```

## $ snow snowpark build -c bob_killer --project hosts/snowflake

_2026-10-16T21:09:38.987209+00:00_

```text
exit 0
Resolving dependencies from requirements.txt
  No external dependencies.
Preparing artifacts for source code
  Creating: src.zip
Build done.
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## $ snow snowpark deploy --schema TEST_96AC49EB -c bob_killer --project hosts/snowflake

_2026-10-16T21:09:48.403030+00:00_

```text
exit 0
Performing initial validation
Checking remote state
Preparing required stages and artifacts
  Creating (if not exists) stage: deployments
  Uploading src.zip to @BOB_KILLER.TEST_96AC49EB.deployments/src.zip/
  Uploading platform_probe.py to @BOB_KILLER.TEST_96AC49EB.deployments/platform_probe.py/
Creating Snowpark entities
  Creating procedure PLATFORM_PROBE
+----------------------------------------------------------------------------------+
| object                                                     | type      | status  |
|------------------------------------------------------------+-----------+---------|
| BOB_KILLER.TEST_96AC49EB.PLATFORM_PROBE(stage_path string) | procedure | created |
+----------------------------------------------------------------------------------+
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## CALL PLATFORM_PROBE(<staged file>)

_2026-10-16T21:09:55.261616+00:00_

```text
{
  "current_schema": "TEST_96AC49EB",
  "run_state": "queued",
  "sha256": "6b5f09602cbba3fee7ae3b1a5624ff9e1446929cc85d098fd4371e06f2eb909b",
  "sys_version": "3.12.13 | packaged by conda-forge | (main, Mar  5 2026, 16:41:49) [GCC 14.3.0]"
}
```

## F3 pydantic (3.12, Anaconda channel)

_2026-10-16T21:09:56.488575+00:00_

```text
1.10.12, 1.10.19, 2.10.3, 2.11.7, 2.11.9, 2.12.2, 2.12.3, 2.12.4, 2.12.5, 2.13.2, 2.13.4, 2.13.5, 2.5.3, 2.8.2
```

## F3 pydantic-core (3.12, Anaconda channel)

_2026-10-16T21:09:57.868978+00:00_

```text
2.14.6, 2.20.1, 2.21.0, 2.27.1, 2.33.2, 2.39.0, 2.41.4, 2.41.5, 2.42.0, 2.46.2, 2.46.4, 2.46.5
```

## F3 annotated-types (3.12, Anaconda channel)

_2026-10-16T21:09:59.072841+00:00_

```text
0.6.0, 0.7.0
```

## F3 typing-extensions (3.12, Anaconda channel)

_2026-10-16T21:10:00.243038+00:00_

```text
3.10.0.0, 3.10.0.2, 3.7.4.2, 3.7.4.3, 4.1.1, 4.11.0, 4.12.2, 4.15.0, 4.16.0, 4.7.1, 4.9.0
```

## F3 typing-inspection (3.12, Anaconda channel)

_2026-10-16T21:10:01.711605+00:00_

```text
0.4.0, 0.4.2, 0.4.3
```

## F3 openpyxl (3.12, Anaconda channel)

_2026-10-16T21:10:02.903522+00:00_

```text
2.5.14, 2.6.1, 2.6.2, 2.6.3, 3.0.0, 3.0.1, 3.0.10, 3.0.2, 3.0.3, 3.0.4, 3.0.5, 3.0.6, 3.0.7, 3.0.9, 3.1.2, 3.1.5
```

## F3 et_xmlfile (3.12, Anaconda channel)

_2026-10-16T21:10:04.055610+00:00_

```text
1.0.1, 1.1.0, 2.0.0
```

## F3 snowflake-snowpark-python (3.12, Anaconda channel)

_2026-10-16T21:10:05.439261+00:00_

```text
0.4.0, 0.5.0, 0.5.1, 1.12.1a1, 1.13.0a1, 1.14.0a1, 1.14.0a2, 1.27.0, 1.27.0, 1.27.0, 1.27.0, 1.27.0, 1.28.0, 1.28.0, 1.28.0, 1.28.0, 1.28.0, 1.29.0, 1.29.0, 1.29.0, 1.29.0, 1.29.0, 1.29.1, 1.29.1, 1.29.1, 1.29.1, 1.29.1, 1.30.0, 1.30.0, 1.30.0, 1.30.0, 1.30.0, 1.31.1, 1.31.1, 1.31.1, 1.31.1, 1.31.1, 1.32.0, 1.32.0, 1.32.0, 1.32.0, 1.32.0, 1.33.0, 1.33.0, 1.33.0, 1.33.0, 1.33.0, 1.34.0, 1.34.0, 1.34.0, 1.34.0, 1.34.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.35.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.36.0, 1.37.0, 1.37.0, 1.37.0, 1.37.0, 1.37.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.38.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.0, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.39.1, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.41.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.42.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.43.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.44.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.47.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.0, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.48.1, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.49.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.0, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.50.1, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.0, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.51.1, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.52.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.0, 1.53.1, 1.53.1, 1.53.1, 1.53.1, 1.53.1, 1.54.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.0, 1.55.1, 1.55.1, 1.55.1, 1.55.1, 1.55.1
```

## F4 duplicate PK + NULL into NOT NULL

_2026-10-16T21:10:09.202438+00:00_

```text
rows after 2 duplicate inserts: 2
100072 (22000): DML operation to table TEST_96AC49EB.F4_PROBE failed on column V with error: NULL result in a non-nullable column
```

## F6 LIST @UPLOADS

_2026-10-16T21:10:09.290786+00:00_

```text
[
  {
    "name": "uploads/6b5f09602cbba3fee7ae3b1a5624ff9e1446929cc85d098fd4371e06f2eb909b.xlsx",
    "size": 265,
    "md5": "f05e1aa6e7b6d0cd2d0d120853808e7d",
    "last_modified": "Fri, 16 Oct 2026 21:09:50 GMT"
  }
]
```

## F8 DESCRIBE PROCEDURE PLATFORM_PROBE(VARCHAR)

_2026-10-16T21:10:09.594334+00:00_

```text
[
  {
    "property": "signature",
    "value": "(STAGE_PATH VARCHAR)"
  },
  {
    "property": "returns",
    "value": "VARIANT"
  },
  {
    "property": "language",
    "value": "PYTHON"
  },
  {
    "property": "null handling",
    "value": "CALLED ON NULL INPUT"
  },
  {
    "property": "volatility",
    "value": "VOLATILE"
  },
  {
    "property": "execute as",
    "value": "OWNER"
  },
  {
    "property": "body",
    "value": null
  },
  {
    "property": "imports",
    "value": "[@BOB_KILLER.TEST_96AC49EB.DEPLOYMENTS/src.zip/src.zip, @BOB_KILLER.TEST_96AC49EB.DEPLOYMENTS/platform_probe.py/platform_probe.py]"
  },
  {
    "property": "handler",
    "value": "platform_probe.platform_probe"
  },
  {
    "property": "runtime_version",
    "value": "3.12"
  },
  {
    "property": "packages",
    "value": "[]"
  },
  {
    "property": "artifact_repository",
    "value": "snowflake.snowpark.pypi_shared_repository"
  },
  {
    "property": "artifact_repository_packages",
    "value": "['snowflake-snowpark-python','pydantic<2.12,>=2.11']"
  },
  {
    "property": "installed_packages",
    "value": "['wheel==0.47.0','readline==8.3','ld_impl_linux-64==2.45.1','libuuid==2.42','liblzma==5.8.3','libxcrypt==4.4.36','icu==78.3','ncurses==6.6','libzlib==1.3.2','libstdcxx==15.2.0','ca-certificates==2026.4.22','libsqlite==3.53.0','libffi==3.5.2','pip==26.0.1','libgcc==15.2.0','bzip2==1.0.8','openssl==3.6.2','setuptools==82.0.1','packaging==26.2','python==3.12.13','_openmp_mutex==4.5','tzdata==2025c','libgomp==15.2.0','libnsl==2.0.1','libgcc-ng==15.2.0','zstd==1.5.7','libexpat==2.7.5','tk==8.6.13','typing_extensions==4.15.0','opentelemetry-api==1.38.0','opentelemetry-sdk==1.38.0','wrapt==2.1.2','python_abi==3.12','typing-extensions==4.15.0','importlib-metadata==8.7.0','opentelemetry-semantic-conventions==0.59b0','zipp==3.23.1','deprecated==1.3.1','snowflake-telemetry-python==0.8.0','ld_impl_linux-aarch64==2.45.1']"
  },
  {
    "property": "artifact_repository_installed_packages",
    "value": "['annotated-types==0.8.0','asn1crypto==1.5.1','boto3==1.43.114','botocore==1.43.114','certifi==2026.7.22','cffi==2.1.1','charset-normalizer==3.5.2','cloudpickle==3.1.2','cryptography==50.0.2','filelock==3.32.7','idna==3.20','jmespath==1.1.0','packaging==26.3','platformdirs==4.13.3','protobuf==6.33.6','pycparser==3.11','pydantic-core==2.33.2','pydantic==2.11.10','pyjwt==2.15.1','pyopenssl==26.4.0','python-dateutil==2.9.0.post0','pytz==2026.5','pyyaml==6.0.3','requests==2.34.2','s3transfer==0.19.2','setuptools==84.0.0','six==1.17.0','snowflake-connector-python==4.8.0','snowflake-snowpark-python==1.55.2','sortedcontainers==2.4.0','tomlkit==0.15.2','typing-extensions==4.16.0','typing-inspection==0.4.4','tzlocal==5.4.4','urllib3==2.8.0','wheel==0.48.0']"
  }
]
```

## F9 session.call(..., block=False)

_2026-10-16T21:10:13.819770+00:00_

```text
AsyncJob is_done=True
{
  "current_schema": "TEST_96AC49EB",
  "run_state": "queued",
  "sha256": "6b5f09602cbba3fee7ae3b1a5624ff9e1446929cc85d098fd4371e06f2eb909b",
  "sys_version": "3.12.13 | packaged by conda-forge | (main, Mar  5 2026, 16:41:49) [GCC 14.3.0]"
}
```

## $ snow streamlit deploy hello_eai --schema TEST_4B806A3F -c bob_killer --project hosts/snowflake

_2026-10-16T21:10:22.523036+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_4B806A3F.HELLO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_eai.
The following files exist only on the stage:
hello_app/.streamlit/config.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  modified: hello_app/pyproject.toml -> hello_app/pyproject.toml
  modified: hello_app/streamlit_app.py -> hello_app/streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_4B806A3F.HELLO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_EAI

_2026-10-16T21:10:22.637697+00:00_

```text
[
  {
    "title": null,
    "main_file": "hello_app/streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "hntbtdh5qb766eolcjes",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[\"BOB_KILLER_PYPI_EAI\"]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_4B806A3F.HELLO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_4B806A3F.HELLO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_4B806A3F.HELLO_EAI/versions/live/"
  }
]
```

## $ snow streamlit deploy hello_no_eai --schema TEST_4B806A3F -c bob_killer --project hosts/snowflake

_2026-10-16T21:10:32.759915+00:00_

```text
exit 0
Checking if object exists
Performing a diff between the Snowflake stage: snow://streamlit/BOB_KILLER.TEST_4B806A3F.HELLO_NO_EAI/versions/live and your local deploy_root: /Users/jasontouleyrou/Projects/bob-killer-snowflake/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_no_eai.
The following files exist only on the stage:
hello_app/.streamlit/config.toml

Use the --prune flag to delete them from the stage.
Local changes to be deployed:
  modified: hello_app/pyproject.toml -> hello_app/pyproject.toml
  modified: hello_app/streamlit_app.py -> hello_app/streamlit_app.py
Uploading files from local /Users/jasontouleyrou/Projects/bob-killer-snowflake/labs/bob_killer/hosts/snowflake/output/bundle/streamlit/hello_no_eai directory to stage.
Streamlit successfully deployed and available under https://app.snowflake.com/<ORG>/<ACCOUNT>/#/streamlit-apps/BOB_KILLER.TEST_4B806A3F.HELLO_NO_EAI
warning: `VIRTUAL_ENV=.venv` does not match the project environment path `/Users/jasontouleyrou/Projects/bob-killer-snowflake/.venv` and will be ignored; use `--active` to target the active environment instead
```

## F1/F7 DESCRIBE STREAMLIT HELLO_NO_EAI

_2026-10-16T21:10:33.009950+00:00_

```text
[
  {
    "title": null,
    "main_file": "hello_app/streamlit_app.py",
    "query_warehouse": "BOB_KILLER_WH",
    "url_id": "sn7eiogwnlepeswqbo23",
    "default_packages": "python==3.11.*,snowflake-snowpark-python,streamlit",
    "user_packages": "",
    "import_urls": "[]",
    "external_access_integrations": "[]",
    "external_access_secrets": "{}",
    "compute_pool": "BOB_KILLER_POOL",
    "runtime_name": "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11",
    "name": "HELLO_NO_EAI",
    "comment": null,
    "default_version": "LAST",
    "default_version_name": "VERSION$1",
    "default_version_alias": null,
    "default_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_4B806A3F.HELLO_NO_EAI/versions/version$1/",
    "default_version_source_location_uri": null,
    "default_version_git_commit_hash": null,
    "last_version_name": "VERSION$1",
    "last_version_alias": null,
    "last_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_4B806A3F.HELLO_NO_EAI/versions/version$1/",
    "last_version_source_location_uri": null,
    "last_version_git_commit_hash": null,
    "live_version_location_uri": "snow://streamlit/BOB_KILLER.TEST_4B806A3F.HELLO_NO_EAI/versions/live/"
  }
]
```

## Compute pool BOB_KILLER_POOL before and after ALTER ... SUSPEND

_2026-10-16T21:10:33.354962+00:00_

```text
[
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 14:01:38.040000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  },
  {
    "name": "BOB_KILLER_POOL",
    "state": "SUSPENDED",
    "min_nodes": 1,
    "max_nodes": 1,
    "instance_family": "CPU_X64_XS",
    "num_services": 0,
    "num_jobs": 0,
    "auto_suspend_secs": 300,
    "auto_resume": "true",
    "active_nodes": 0,
    "idle_nodes": 0,
    "target_nodes": 0,
    "created_on": "2026-10-16 10:43:57.829000-07:00",
    "resumed_on": "1969-12-31 16:00:00-08:00",
    "updated_on": "2026-10-16 14:10:33.171000-07:00",
    "owner": "ACCOUNTADMIN",
    "comment": null,
    "is_exclusive": "false",
    "application": null,
    "placement_group": null,
    "backup_instance_families": ""
  }
]
```

## 99_teardown.sql

_2026-10-16T21:10:33.561085+00:00_

```text
DROP SCHEMA IF EXISTS IDENTIFIER('BOB_KILLER.TEST_4B806A3F')
[
  {
    "status": "TEST_4B806A3F successfully dropped."
  }
]
```
