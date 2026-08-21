# Workstation Reconcile v2

- Status: active
- Owner layer: cross_component_contract
- Applies when: a verified public Release must be reconciled with one Codex workstation.
- Avoid when: only Core rules, Scheduled enrollment, or Release publication is being changed.

## Product contract

The user has one operation: synchronize and deploy Agent Memory on this workstation. The implementation owns five distinct facts:

```text
DesiredBundleIdentity
-> ObservedHostState
-> exact reconcile plan
-> transactional execution and readback
-> new-task consumer verification
```

No earlier fact can substitute for a later one. In particular, a verified Release, clean managed source, installed Skill, passing
Doctor, and model adoption are separate evidence layers.

## Desired bundle identity

`DesiredBundleIdentity` is constructed only from the Resolver-verified `resolution.json`, byte-matching release assets,
`release-manifest.json`, its matching `source-manifest.json`, and the safely materialized portable tree. The public repository,
tag/commit, Core/tag relation, Plugin/Skill embedded versions, archive digest, and physical component hashes must agree before a
plan exists. It has exact fields:

```text
release_ref, source_commit, core_version, plugin_version, plugin_sha256,
bootstrap_version, bootstrap_sha256, scout_version, scout_sha256
```

The source identity is additionally bound as the SHA-256 of the normalized credential-free Sidecar remote. Component hashes are
computed from physical regular files while excluding bytecode caches, Git metadata, and the portable-only generated Plugin
`source-manifest.json`.

## Observed host state

`ObservedHostState.distribution` has exact `marketplace` and `plugin` objects:

```text
marketplace: status, source_sha256, ref, commit
plugin: status, source_sha256, ref, version, content_sha256, enabled
```

The observer uses `codex plugin ... --json`, the Codex-owned marketplace install metadata, the clean tracked marketplace checkout,
and the physical installed Plugin cache. It never parses UI text and never exposes roots, URLs, credentials, or host IDs. Missing,
unavailable, disabled, and drifted are distinct states.

When managed source identity is already exact, the same dry-run invokes the exact managed Core's read-only Doctor and physically
reads installed Bootstrap and Scout versions/hashes. Only live Core runtime identity, expected Owner parity state, Doctor, and both
Skills can produce a no-op host result. Historical cutover receipts are transaction records, not current-state observations.

## Plan and authorization

`agent_memory_workstation_reconcile_plan_v2` has exact fields:

```text
contract_version, bootstrap_version, status, desired_bundle, observed_distribution,
source_plan_hash, changes, blockers, confirmation_required, requires_reload, plan_hash
```

- Fresh install and same-source ref/version repair are covered by the user's deployment request.
- A Sidecar or Marketplace source identity change requires one visible confirmation and a fresh exact `plan_hash`.
- An explicitly disabled Plugin is `distribution_reconcile_blocked`; the reconciler does not silently reverse the user's setting.
- Apply always recomputes desired identity, observed state, source plan, and the complete plan hash.

## Transaction

Plugin/Marketplace mutation is a participant in Source Authority Cutover v2, not a shell pre-step. The transaction:

1. stages and validates all managed source replacements;
2. snapshots installed Bootstrap and Scout targets;
3. removes/re-adds only the Agent Memory Plugin and Marketplace when the plan requires it;
4. materializes Core, optional exact Owner binding, Bootstrap, Scout, and Doctor;
5. reads Plugin/Marketplace, source receipts, runtime identity, and Skill content hashes back exactly;
6. constructs and validates Deployment Pack v2 before committing the source receipt;
7. only then discards source, Skill, and distribution rollback state.

Any failure before commit restores all touched managed sources, Skill targets, and Agent Memory distribution surfaces. It never
resets or cleans a user project checkout.
The atomic source receipt replacement is the commit point. A later rollback-snapshot cleanup failure is reported as
`source_cutover_postcommit_cleanup_failed` and never attempts a second rollback after any recovery copy may already have been
discarded; the next run must re-observe the committed state.

## Published-anchor compatibility

Plugin 1.3/Bootstrap Anchor 1.x is already public and invokes `source-cutover` after resolving a Release. When that legacy command
receives the exact Resolver directory shape (`source-manifest.json`, `release-manifest.json`, `resolution.json`, and `portable/`),
Bootstrap 2.0 routes its dry-run/apply and renderer to Workstation Reconcile v2. This prevents the first v0.3.8 upgrade from leaving
new Core/Skills behind an old Plugin or requiring a second migration cycle. A standalone source manifest without that Resolver
shape retains the lower-level Source Authority Cutover v2 behavior.

## Deployment Pack v2

`agent_memory_workstation_deployment_pack_v2` has exact fields:

```text
contract_version, status, display_locale, generated_at, desired_bundle, distribution,
source_sync, host_materialization, consumer_activation, limitations, pack_hash
```

Statuses are `ready`, `reload_required`, `distribution_reconcile_blocked`, `source_sync_blocked`, or
`host_materialization_blocked`. `ready` requires exact distribution, exact managed Sidecar commit, verified runtime/Doctor,
exact Bootstrap and Scout hashes, and a new task that loaded the installed Bootstrap. An apply task therefore ends at
`reload_required`; after one Desktop refresh, `--verify-consumer` in the newly loaded Bootstrap task may produce `ready`.
Any blocked Pack sets the interactive entry to `blocked` and does not ask for Desktop refresh or Project Scout; it routes only to
the first invalid layer.

`ready` never proves Scheduled activation, another workstation, continuity, or product effect.

## Acceptance criteria

- Fresh host: install Marketplace, Plugin, managed source, Core, Skills, and Doctor; return `reload_required`.
- Exact live host: plan is `noop`; read-only new-task verification re-observes it and may return `ready`.
- Missing or drifted Core/Doctor/Bootstrap/Scout: plan contains `host:materialize`; a prior green receipt cannot suppress repair.
- Old Marketplace/Plugin plus new sources/Skills: plan replaces both distribution surfaces; v1-style `ready` is impossible.
- New Plugin plus old source/Skills: source/materialization changes remain visible and block `ready` until exact.
- Wrong source identity: one confirmation and exact-hash apply; no force path.
- Missing cache, unreadable CLI state, or dirty tracked marketplace: fail closed.
- Explicitly disabled Plugin: preserve the setting and return a visible blocker.
- Any execution or readback failure: restore every touched managed surface and return no completion claim.
- The current host cannot qualify a real second host; the Deployment Pack always retains that limitation until separately proven.
