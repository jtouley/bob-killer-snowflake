# Name review queue: mt_dot_budget

Workbook sha256 `e835558d6df6a84ba0576804d02e8280821205d0b576ed232379a373afc93047`. 8 output-facing nodes need
review; each was pre-approved with the naming rule's own choice (reviews/mt_dot_budget.yaml). Revisit any row below with a better name.

| node | origin | rule | label | formula |
| --- | --- | --- | --- | --- |
| `revenue_c13` | 'REVENUE'!C13 | sheet_address | 'REVENUE'!C13 | `=IF(B13<>SUM(B17:B19),"Please complete Status","")` |
| `out_revenue_c13` | 'REVENUE'!C13 | sheet_address | 'REVENUE'!C13 | `` |
| `costs_f15` | 'COSTS'!F15 | sheet_address | 'COSTS'!F15 | `=TEXT(E15,)` |
| `out_costs_f15` | 'COSTS'!F15 | sheet_address | 'COSTS'!F15 | `` |
| `revenue_b16` | 'REVENUE'!B16 | sheet_address | 'REVENUE'!B16 | `=B15-B17` |
| `out_revenue_b16` | 'REVENUE'!B16 | sheet_address | 'REVENUE'!B16 | `` |
| `revenue_d16` | 'REVENUE'!D16 | sheet_address | 'REVENUE'!D16 | `=B15-SUM(B17:B19)` |
| `out_revenue_d16` | 'REVENUE'!D16 | sheet_address | 'REVENUE'!D16 | `` |
