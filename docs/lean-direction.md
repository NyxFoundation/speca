# Spec → Lean4: direction rationale (EF check-in)

Milestone 2-D was originally worded as SPECA → Lean: take the natural-language
security properties SPECA generates in `01e` and convert them into Lean
specifications. We implement the reverse direction, **Spec → Lean4**: the
protocol specification itself is modeled and machine-checked in Lean 4
(NyxFoundation/gasper-lean4), and each theorem is lowered into a `01e`
security property — with its proof outcome (`lean_status: proved | unknown`)
and its Kurtosis reproduction fixture attached — that the existing SPECA
pipeline then audits against client implementations. This is the stronger
design for our goals: the ground truth lives in the spec, not in generated
prose, so properties inherit a machine-checked provenance instead of asking
Lean to retroactively bless LLM output; it matches SPECA's existing
spec→property data flow, so the integration is a pluggable `01e` provider
(`--property-provider lean`) rather than a new pipeline; and a proved theorem
gives a precise, decidable statement that a devnet assertion can check, which
prose properties do not. Lean execution stays out of `speca` entirely — it
lives in the version-pinned external plugin
[NyxFoundation/speca-lean4-plugin](https://github.com/NyxFoundation/speca-lean4-plugin),
invoked across the plugin boundary defined in #87.

## Current status, honestly stated

- **Pilot scope is gasper only.** The provider covers the gasper-lean4 Core
  theorem set (Casper FFG safety/liveness family), not the originally
  discussed EIP-7951 or any broader EIP coverage (#90).
- **Kurtosis fixtures are scaffolds.** Each checker-linked property gets a
  fixture under `outputs/kurtosis/<label>/<property_id>/` referencing a real
  proved decidable checker from gasper-lean4's Executable layer, but devnet
  bring-up and execution are #92 territory; the fixture's `verdict` is null
  and its `scaffold` flag is true. Properties whose theorem has no Executable
  checker keep `kurtosis_test` null.
- **The CI smoke proves plumbing, not theorems.** The `properties-lean`
  workflow uses the plugin's committed sample proof-health fixture by
  default; `lean_status` values in that run certify nothing. Real
  certification requires the `run_lean` path (`lake exe speca-export` over an
  actual gasper-lean4 build).
- **Proof outcomes are recorded as-is.** `unknown` is never relabeled;
  `lean_status` / `lean_artifact` / `kurtosis_test` are additive fields and
  core `01e` fields are unchanged.

## Pointers

- Provider wiring: `scripts/orchestrator/providers.py`
  (`LeanPropertyProvider`), CI: `.github/workflows/01e-properties-lean.yml`.
- Integrated pipeline spec: plugin `docs/pipeline.md`; Kurtosis bridge
  design: plugin `docs/kurtosis-bridge.md`; toolchain pinning: plugin
  `docs/lean-toolchain.md`.
- Tracking: #86 (M2), #88 (this provider), #90 (full-EIP generation), #92
  (Kurtosis reproduction at scale).
