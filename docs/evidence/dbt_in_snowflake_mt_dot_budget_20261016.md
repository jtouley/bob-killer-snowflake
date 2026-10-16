# Golden workbook → dbt project → run and queried in Snowflake (2026-10-16)

First end-to-end run of the goal path on a real government workbook: the Montana DOT MWTP Project Budget
Worksheet (`golden.lock` id `mt_dot_budget`, sha256 `e835558d…`).

## What ran

| Step | How | Result |
| --- | --- | --- |
| Extract → Graph → Lift | merged `snowflake-host` code, `labs/bob_killer/build/gen_dbt.py mt_dot_budget` | IR: 48 inputs, 30 steps, 3 outputs, 1 unsupported |
| dbt project | the merged dbt generator (`generate/dbt`) | 84 files |
| Runtime in Snowflake | Python 3.12 UDFs `BK_FN_SUM/MIN/IF/SUMIF` (1–4 args), `BK_OP_ADD/SUB/MUL/EQ/NE`, code zip on `@BOB_KILLER.TEST_DBTDEMO.BK_CODE` | `BK_FN_SUM([3,1])` = `0x1.0000000000000p+2` (4) exactly; `BK_OP_MUL(3,2)` = 6 |
| Inputs | 48 input cells with Excel's cached values as wire JSON into `TEST_DBTDEMO.WB_INPUT_CELLS` | 48 rows |
| Deploy | `snow dbt deploy BK_MT_DEMO --dbt-version 1.12.3` (dbt Project on Snowflake) | created |
| Run | `snow dbt execute BK_MT_DEMO build` (runs inside Snowflake) | PASS 82, ERROR 4, SKIP 3, TOTAL 89; 66 tables in `TEST_DBTDEMO__R_000…01` incl. `FCT_FORMULA_CELLS`, `BK_ORACLE` |
| Parity (SQL in Snowflake) | `FCT_FORMULA_CELLS.value` = `BK_ORACLE` wire value of Excel's cached result, per cell | **24 / 30 exact**, 6 mismatch |

## The 6 mismatches (all trace to SUMIF)

| Cell | Snowflake dbt | Excel cached | Cause |
| --- | --- | --- | --- |
| REVENUE!B16–B19, D16 | `#N/A` | 0 | `SUMIF` is not in the runtime yet; its UDF returns `#N/A` on purpose; dependents inherit it |
| REVENUE!C13 | "Please complete Status" | "" | `=IF(B13<>SUM(B17:B19),...)` reads the SUMIF cells; the demo comparison shim also does not propagate errors like Excel |

Every formula cell that does not depend on SUMIF equals Excel's cached value exactly (IEEE-754 bits, via the
`float.hex()` wire format).

## Honest limits of this run

- **Operators are a demo shim** in `build/bk_udf.py` (`ADD/SUB/MUL/EQ/NE`), not the core runtime: the runtime has
  no operator layer yet. `SUM`, `MIN` and `IF` are the merged runtime functions.
- **The 4 dbt test errors**: the generated `bk_exact_parity` tests call `BK_VALUES_EQUAL`, which was not deployed in
  this run; the parity check above was run as SQL instead.
- **The workbook is a budget template**: 45 of its 48 inputs are blank, so most outputs are 0. The larger goldens
  (iWARM, SGEC) are next.
- The UDFs, inputs and project live in schema `BOB_KILLER.TEST_DBTDEMO` (drop with `99_teardown.sql`).

## Next to make it fully pass

1. `SUMIF` (and the other gap functions) in `runtime/` with Microsoft-doc oracle cases.
2. A runtime operator layer (`+ - * / ^ & = <> < > <= >=`, unary) replacing the shim, with Excel error propagation.
3. Deploy `BK_VALUES_EQUAL` (wraps `verify/config.values_equal`) so the generated dbt parity tests run.
4. Make the UDF + input loading part of the pipeline (`RUN_PIPELINE`, D18) instead of the demo scripts.
