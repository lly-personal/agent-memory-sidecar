# Source Authority Cutover v1

## Purpose

This contract owns the exceptional host operation that changes an existing managed Sidecar source identity after the public
engineering authority has moved. It does not weaken the normal `sync-sources` contract: identity drift, a dirty checkout, or a
commit mismatch still fails closed there.

## Plan and confirmation

The only production entry points are:

```text
managed_sources.py source-cutover --dry-run --codex-home <home> --source-manifest <manifest>
managed_sources.py source-cutover --apply --codex-home <home> --source-manifest <manifest> --plan-hash <hash>
```

The dry run performs no host mutation. It validates the release manifest, resolves every configured remote ref to the declared
full commit, reads clean existing managed sources, checks the current global-binding boundary, and emits
`agent_memory_source_cutover_plan_v1` with exact fields:

```text
contract_version, bootstrap_version, status, owner_action, current, desired, changes, plan_hash
```

`owner_action` is `keep_owner` when a commit-bound canonical Owner remains configured and `public_core` only when neither an Owner
checkout nor an existing global binding is present. Removing an existing Owner is not part of this contract and returns
`source_cutover_owner_detach_required`. Source identities expose only SHA-256 remote identities, refs, and commits; they never
expose raw remotes or local paths. `bootstrap_version` binds the executor contract; `plan_hash` is SHA-256 of canonical UTF-8 JSON
excluding itself.

Apply recomputes the complete plan and accepts only the exact current hash. There is no `force` option and no unbound approval
token. A stale plan, changed source, dirty checkout, unresolved ref, materialization failure, or Doctor failure aborts the operation.

## Transaction

Apply stages and verifies every desired source before replacing any target. It retains rollback snapshots for replaced sources and
the installed Bootstrap/Scout targets while Core setup runs. Core setup keeps ownership of its existing Store, Hook, runtime,
instruction, and Core Skill transaction. Before source mutation, apply validates the existing receipt target and proves that its
physical directory supports the staged-write plus atomic-replace commit primitive. Success requires Core's strict Doctor result;
only then may the operation atomically activate `agent_memory_source_cutover_receipt_v1` under the active Codex home and discard
rollback snapshots.

On failure, all replaced managed sources and Bootstrap/Scout targets are restored and no success receipt is written. Active project
checkouts, Scheduled state, Host Profile, project registration, and the frozen private engineering repository are never mutation
targets.

## Evidence boundary

A successful receipt proves one host's source synchronization and host materialization for the named commits. It does not prove
that the current task loaded newly installed Skills, that a project was activated, that another machine can cold-start, or that the
behavior changed in a later task. Those remain separate consumers.
