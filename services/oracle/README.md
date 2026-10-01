# Excel oracle service

The one separate service from day one (SPEC decision 7). It recalculates a workbook
with given inputs and converts legacy `.xls` to `.xlsx` **in real Excel**, so its
results are Excel's results. LibreOffice is never an oracle.

Client protocol: `bob_killer.verify.oracle.Oracle`. Phase 0 ships only
`UnavailableOracle`, which raises.

Runner options (Phase 1 entry criterion):
- Desktop Excel driven by `xlwings` on a Windows or Mac runner, or
- Microsoft Graph workbook API (needs a Microsoft 365 account; rate-limited).

The runner executes third-party macros (JEDI), so it runs in an isolated,
disposable environment with no credentials beyond its own.
