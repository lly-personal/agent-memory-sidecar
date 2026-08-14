# Governed Knowledge Index

- Status: active
- Owner layer: project_docs
- Last verified: 2026-07-24

## Current authority route

Read in this order:

1. [L1 Design Axioms](../specs/axioms.md) — product goal, evidence and forbidden
   complexity.
2. [L2 System Topology](../specs/topology.md) — one owner per component, data
   flow, Desktop and primary-folder boundaries.
3. [L3 Interaction Contract](../specs/interface.md) — proposal, CLI, state,
   failure and acceptance semantics.
4. [Agent Memory Core v1](../../specs/agent-memory-core-v1.md) — detailed
   executable contract.
5. [ADR 0057](../decisions/0057-agent-memory-core-v1.zh.md) — why the breaking
   Core cutover was selected.
6. [Public distribution v1](../../specs/public-distribution-v1.md) and
   [ADR 0072](../decisions/0072-allowlisted-public-distribution-lane.zh.md) — allowlisted public export, immutable sources, and the optional private Owner boundary.

Root [`domain.md`](../../domain.md) owns shared vocabulary. Root `specs/` owns detailed contracts.
`docs/decisions/` owns rationale. Tests own machine-verifiable acceptance.

## Current operational route

- [User guide](../user-guide.zh.md)
- [Operator reference](../operator-reference.zh.md)
- [Codex Desktop setup](../codex-desktop-setup.md)

Desktop installs exactly two Sidecar Hook entries: `UserPromptSubmit` and
`SessionStart` with matcher `^compact$`. Both execute a content-addressed
immutable zipapp; neither imports the editable checkout at runtime.

## Historical boundary

All root contracts other than `agent-memory-core-v1.md` and `public-distribution-v1.md` are retained historical
records and are superseded for the current implementation. They may explain
earlier decisions, but cannot restore legacy CLI, generic `MemoryStore`,
SQLite-active state, release harnesses, clean-store rotation, editable Hooks, or
Ambient release holds.

The immutable `v0.2.0` tag remains the executable rollback source. Historical
evidence never proves current Desktop adoption.

## Record rules

- Keep L1/L2/L3 small and route details rather than duplicating them.
- Keep stable Core and experimental Ambient evidence separate.
- Record unknown or unproven behavior explicitly.
- Never store raw chats, prompts, credentials, or unverified claims as governed
  knowledge.
