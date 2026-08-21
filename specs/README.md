# Contract index

`agent-memory-core-v1.md` owns the active runtime contract.
`public-distribution-v1.md` owns the active public export and release contract. `public-authority-cutover-v1.md` owns the active
engineering-authority epochs, first-release cutover gate, and steady-state public development boundary.
`source-authority-cutover-v2.md` owns the lower-level transaction for explicit migration between managed Sidecar identities.
`workstation-reconcile-v2.md` owns the single user-facing operation that reconciles verified Release identity, Marketplace/Plugin,
managed sources, host materialization, and new-task consumer verification.
`global-owner-scout-delivery-v1.md` owns task-scoped Review Pack artifacts, compact receipts, and actual task-surface qualification.
`release-promotion-v1.md` owns the deterministic inspect/apply transition from a verified draft to an attested immutable Release.

All other Markdown contracts in this directory are retained historical contracts. `public-export-allowlist-v1.json` is the
machine-owned allowlist for the active public distribution contract. Historical files are
superseded for current implementation by Agent Memory Core v1 and ADR 0057,
including their former CLI, Store, rollout, release-hold, diagnostic and
migration requirements. A historical contract remains useful as decision
evidence, but cannot override Core v1.
