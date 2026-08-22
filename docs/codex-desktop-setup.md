# Codex Desktop Setup — Agent Memory Core v1

- Status: active
- Owner layer: project_docs
- Last verified: 2026-08-22
- Evidence: [Core v1 contract](../specs/agent-memory-core-v1.md)、[Public distribution v1](../specs/public-distribution-v1.md)、[Workstation Reconcile v2](../specs/workstation-reconcile-v2.md)

## Released consumer path

Codex Desktop users register the tagged public Marketplace and install the plugin:

```powershell
codex plugin marketplace add lly-personal/agent-memory-sidecar --ref v0.3.9
codex plugin add agent-memory-sidecar@agent-memory
```

Restart Desktop and start one new task, then send `同步并部署本机 Agent Memory`.
The Anchor resolves the latest stable immutable Release (or an explicitly
selected version), verifies asset digests, checksums, tag/commit and manifests,
safely materializes its portable bundle, and runs the commit-bound Bootstrap in
the same task. Fresh/same-source deployment completes directly. A legacy
Sidecar or Marketplace source identity replacement displays one path-free plan and asks for one
confirmation before a fresh-hash atomic apply. The following task is needed
only for reliable automatic discovery and consumer verification of newly installed Plugin/Skills.
A checkout or Marketplace alone does not authorize source materialization or prove model adoption.

Core-only consumers install the Release wheel and run:

```powershell
python -m pip install .\agent_memory_sidecar-0.3.9-py3-none-any.whl
agent-memory setup
agent-memory setup --apply
agent-memory doctor
```

Preview performs no writes. Apply builds a deterministic content-addressed
zipapp, installs the canonical Skill, updates the two Hook entries, binds the
runtime installation, and verifies exact hashes and Store integrity.

The commands above are the public Core profile. They do not require a private
Owner and do not create a global binding. Project-scope Core, immutable Runtime,
Store integrity, and Doctor remain available.

If a complete global instruction source is available as a separately selected,
clean, commit-bound private checkout:

```powershell
python -m agent_memory_sidecar setup --apply --global-rules-source <owner-checkout>
```

The source must be a clean checkout with a resolvable commit and a canonical
`global/AGENTS.md`. Setup preserves complete-file parity between that source and
the local `~/.codex/AGENTS.md`. SQLite, events, tokens, credentials and Hook
trust are never copied between devices.

Workstation Bootstrap uses `workstation-reconcile --dry-run` and exact-hash apply as
the unified Marketplace/Plugin/source/host transaction. Public Core sets
`canonical_owner` to `null`; a release source must bind the Sidecar ref and
full commit SHA. On a legacy host, null preserves a clean existing Owner only
when Core's bound source root and commit match it exactly.

If an existing host has a clean managed Sidecar with a different repository
identity, normal `sync-sources` intentionally fails closed. The unified flow reads actual Codex JSON and physical component
identities, renders only safe desired/observed changes, then passes the exact fresh `plan_hash` to apply after one confirmation.
Apply returns `reload_required`; a refreshed task runs read-only `--verify-consumer` before reporting `ready`.
Existing global Owner removal is not implicit and requires a separate decision.

## Contributor path

Contributors clone this public repository, work on a topic branch, and may use
an editable install only for development:

```powershell
python -m pip install -e .
python -m agent_memory_sidecar setup
```

Editable setup is not the released consumer acceptance path. Before a pull
request, run the full checks in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Installed Hooks

- `UserPromptSubmit`: captures a bounded envelope and prompt hash, then
  transports a fixed capability plus opaque current event ref.
- `SessionStart` with matcher `^compact$`: read-only retransports the capability
  for the same current session, scope and prompt event.

Other `SessionStart` sources and `PostCompact` are no-op. Hooks do not inspect
prompt semantics, persist proposal bodies, approve rules, query native Memories,
or render UI. Both invoke the installed `.pyz`; editing the checkout cannot
change the live Hook runtime.

## Existing legacy Store

Setup returns `migration_required` and performs no migration. First produce a
read-only plan:

```powershell
python -m agent_memory_sidecar maintenance core-cutover --dry-run
```

Review its table counts, copy/drop policy, artifact hash, backup destination and
`plan_hash`. Apply is a separate authorized operation:

```powershell
python -m agent_memory_sidecar maintenance core-cutover --apply --plan-hash <hash> --approval-ref <current-ref>
```

The operation preserves a permanent checksum-protected backup and restores the
legacy Store and Hook configuration if verification fails.

## What doctor proves

Doctor verifies:

- exactly seven Core tables, schema fingerprint, FK and SQLite integrity;
- artifact content hash and immutable path;
- exact Hook commands and compact matcher;
- installed Skill checksum;
- global source/target complete-file parity when configured.

It does not prove that Desktop invoked a Hook, that a model followed a rule, or
that continuity survived a new task. Those require real Desktop acceptance.
