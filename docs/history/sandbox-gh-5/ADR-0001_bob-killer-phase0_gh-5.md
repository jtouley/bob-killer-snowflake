---
decision_id: ADR-0001
status: proposed
question: How do we resolve the blocking spec gaps (G1-G4, G6, G7) so Phase 0 gates are enforceable, for gh-5?
choice: Exact parity everywhere; commit .context; oracle constants in tests/oracle JSON; TDD-Phase commit trailer; explicit import-linter layers; versioned contract snapshot dirs; incubate in sandbox labs/bob_killer
rationale: Each default makes a SPEC gate mechanically checkable without changing the spec's design; alternatives left gates unenforceable in CI (gitignored evidence, no phase marker) or contradicted Decision 1
---

# ADR-0001 — Phase 0 gate mechanics (gh-5)

Ticket: #5 · Source: `.context/vibetest/bob-killer-spec_gh-5_2026-10-01.md`

| Gap | Decision | Rejected alternative |
|---|---|---|
| G1 | Exact parity; "within tolerance" in the test-layer table is errata | A per-layer tolerance (contradicts Decision 1) |
| G2 | `.context/` committed; `*.db`, `tmp/` ignored | Upload `.context` as CI artifacts only (lost across sessions; user rejected) |
| G3 | `tests/oracle/*.json` with `source`, `verified_by`; literal-in-assert lint | Allowlisting each hand constant (allowlist growth = failing project) |
| G4 | `TDD-Phase: red\|green\|refactor\|scaffold` trailer | Infer phase from paths (can't distinguish refactor from green) |
| G6 | Layers: api/cli > stages(independent) > store > ir/registry/runtime > contracts | Per-pair forbidden lists (drift) |
| G7 | `contracts/snapshots/v{N}/`; update refuses existing N | Single snapshot + manual review (no mechanical bump check) |
| G11 | `sandbox/labs/bob_killer`, Apache-2.0 subtree, path-filtered CI | New repo now (out of session scope) |
