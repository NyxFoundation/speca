# Sherlock-RQ1 Phase 04 fixture set

Real `outputs/04_PARTIAL_*.json` files from the Sherlock "Ethereum Audit
Contest" RQ1 benchmark run, committed verbatim for the M4 acceptance tests
(issue #29).

- Source: the `bench-rq1-20260508-sherlock_ethereum_audit_contest` GitHub
  Release tarball of this repository (published from
  `benchmarks/results/rq1/sherlock_ethereum_audit_contest/`).
- One directory per audited client repo; `speca browse` operates on one
  project at a time, and property ids repeat across repos (the same property
  set was audited against every client), so tests load repos individually
  unless they are exercising cross-repo behaviour on purpose.
- Totals: 102 files, 550 reviewed items, 72 actionable findings
  (CONFIRMED_VULNERABILITY 39, CONFIRMED_POTENTIAL 24, DOWNGRADED 8,
  NEEDS_MANUAL_REVIEW 1).
- `nethermind_fusaka/` additionally carries the run's Phase 03
  `03_PARTIAL_*.json` slice so the 03↔04 merge and code-location paths are
  covered by real data.
- Contents are untouched: all references point at public Ethereum-client
  repositories and public specs, so nothing needed anonymising.

Consumed by `test/findings.rq1.acceptance.test.ts` and
`test/perf/rq1-filter-render.bench.ts` (`npm run perf:rq1`).
