# Golden probe on merged snowflake-host (Extract -> Graph -> runtime vs Excel cached values)

Command: `uv run python build/golden_probe.py` (each formula evaluated on Excel's own cached inputs; compared with `verify/config.values_equal`, exact).

| golden | cells | formulas | parsed | evaluated | exact | mismatch |
|---|---|---|---|---|---|---|
| mt_dot_budget | 615 | 31 | 31 | 24 | 24 | 0 |
| iwarm | 2537 | 287 | 287 | 264 | 264 | 0 |
| sgec_current | 197704 | 2796 | 2796 | 269 | 269 | 0 |
| sgec_v4_1 | 194654 | 2687 | 2687 | 136 | 136 | 0 |
| sgec_v5_1 | 207376 | 2880 | 2880 | 228 | 228 | 0 |

Not yet evaluable (coverage gaps, top reasons across all goldens):

- node binary:=: 5316
- function VLOOKUP: 673
- function SUMIF: 488
- function ISNA: 429
- function ISBLANK: 351
- function SUMPRODUCT: 259
- function XLOOKUP: 84
- node name: 84
- function SUMIFS: 50
- node binary:^: 2
- function TEXT: 1
- node binary:<>: 1
