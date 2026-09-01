---
name: agent-memory-workstation-bootstrap
description: Synchronize and materialize portable Agent Memory capability from a commit-bound Sidecar source and an optional private Global Owner, install the explicit interactive Project Scout, discover local Codex Desktop projects, and optionally reconcile Scheduled enrollment only when the user explicitly asks. Use for “同步并部署本机 Agent Memory”, workstation migration, rescan, or enrollment reconciliation.
---

# Agent Memory Workstation Bootstrap

## Contract

- Skill version: `2.1.0`
- Modes: `inspect`, `verify_consumer`, `apply_enrollment`
- Deployment pack: `agent_memory_workstation_deployment_pack_v2`
- Enrollment pack: `global_owner_scout_enrollment_pack_v1`
- Host profile: `global_owner_scout_host_profile_v1`
- Read [references/contracts.md](references/contracts.md) completely before either mode.

This Skill separates five facts that must never be collapsed:

1. **desired bundle identity**: one verified Release binds Core, Plugin, Bootstrap, Scout, source commit, and content hashes;
2. **observed distribution**: Codex JSON state and physical readback identify the actual Marketplace and Plugin version/ref/hash/enabled state;
3. **source synchronization**: this host has clean managed snapshots of the Sidecar and canonical Global Owner sources;
4. **host materialization**: Core, global binding, Bootstrap, Scout, and Doctor are installed and verified on this host;
5. **consumer adoption**: a refreshed new task actually loaded the installed Bootstrap before the interactive entry is called ready.

A normal deployment request always enters `inspect`. It must not create, update, pause, resume, or delete Scheduled tasks and must
not change the Host Profile. Only an explicit request to retest or configure Scheduled capability enters `apply_enrollment`.

## Mode: `inspect`

1. Establish the cold-start source without assuming a pre-existing Sidecar checkout:
   - When invoked from the installed `agent-memory-sidecar` plugin, use its release source manifest as the first trusted Bootstrap source.
   - For the public lane, locate and validate the portable bundle's root `source-manifest.json`; a repository checkout or marketplace
     entry alone is not source authority. Execute this Skill's deterministic scripts from the Resolver's safely materialized portable
     root. Never default to a floating branch, ask for project IDs/model settings/project lists, or invent a source.
   - Authentication or source failure ends as `source_sync_blocked`; do not claim the capability is synchronized.
2. Run `python -B scripts/managed_sources.py workstation-reconcile --dry-run --codex-home <active-codex-home>
   --source-manifest <resolved-source-manifest> --release-manifest <resolved-release-manifest>` as the unified
   fresh/update/legacy inspection. It only targets Agent Memory Marketplace/Plugin and reconstructable managed
   sources under the active Codex home and never resets, cleans, pulls, or overwrites an active project checkout.
   - a plan containing fresh installs, same-source ref/version repairs, or `noop` is covered by the user's deployment request.
   - any Sidecar or Marketplace source identity replacement requires `render-reconcile-plan`, one confirmation, another dry-run,
     and only the fresh hash may apply.
   - an explicitly disabled Plugin is a blocker; never silently enable it or call another layer ready.
   - a public manifest with `canonical_owner=null` preserves a clean existing Owner only when its checkout and Core binding
     root/commit match exactly. One-sided, dirty, or mismatched Owner state fails closed.
3. Run exact-hash `workstation-reconcile --apply`. Marketplace/Plugin mutation participates in the source-cutover rollback
   transaction. The transaction then runs Core setup, binds the explicit or preserved canonical Owner, verifies Doctor, installs
   both versioned Skills, and performs exact readback before releasing rollback state. Validate Bootstrap `2.1.0`, Scout `5.7.0`,
   and every desired identity. The result is `reload_required`; it proves host materialization, not model adoption.
4. Ask for exactly one Codex Desktop refresh. In a new task that loaded this installed Skill, run the same command with
   `--verify-consumer` and no plan hash. Only an exact no-op host may become `ready`. Do not ask the user to repeat source choices,
   paths, versions, or deployment commands.
5. Use the Codex Desktop project API to enumerate the complete visible project inventory. Do not infer a fixed project list from
   repository names, paths, old automation names, another host's profile, or the repositories used as capability sources.
6. Enumerate recent tasks with the host-supported bound. Classify a task as natural only when native metadata proves it was
   user-created and belongs to the project. Scheduled, Scout, test, delegated, or automation tasks never establish activity. If
   origin or association is ambiguous, report `bounded`; do not default-enable it.
7. Inspect accessible projects read-only with `scripts/enrollment.py inspect-project`. Compute content identity from normalized Git
   remote identity plus the primary folder's repository-relative location. Never display or persist raw remotes or absolute paths.
   Non-Git and remote-less projects receive host-local identity only and are ineligible for periodic enrollment.
8. Read current Scheduled tasks only to report historical state. The interactive Scout remains the product path; Scheduled remains
   a separate paused/optional experiment unless the user explicitly asks to retest it.
9. Build and validate one `agent_memory_workstation_deployment_pack_v2` from the reconciler's exact readback, render it with
   `python -B scripts/managed_sources.py render-pack`, and return the Chinese Markdown. Separately render an Enrollment Pack only
   when project discovery is useful to the user's request. Do not make enrollment a prerequisite for interactive Scout use.

The final deployment result reports `desired release / Plugin distribution / source synchronization / host materialization /
consumer adoption` separately. A same-machine clean-profile simulation may prove deterministic cold start, but it must remain
distinct from a real second-device result.

## Mode: `verify_consumer`

Enter only from a refreshed new task that actually loaded Bootstrap 2.1.0 after an `inspect` result requested reload. Run
`workstation-reconcile --verify-consumer` against the same Resolver output. This mode is read-only: it requires an exact no-op plan,
re-observes current managed sources, Core runtime, Owner parity, Doctor, installed Bootstrap/Scout bytes, and distribution identities,
and then renders the only `ready` Pack. A historical cutover receipt is never accepted as current host evidence.
Any drift returns to `inspect`; never patch or infer readiness inside this mode.

## Mode: `apply_enrollment`

Enter this mode only when the user explicitly asks to retest/configure Scheduled and selects an action from the latest validated
Enrollment Pack: `按建议启用`, `启用：…`, `暂不启用：…`, `不再建议：…`, `保持现状`, or `重新扫描`.

1. Re-enumerate projects, tasks, and actual automation state. If identity, eligibility, or state changed, render a refreshed pack
   and ask again; do not apply a stale decision.
2. Resolve user-visible names to opaque project refs. `按建议启用` contains only proven `active + eligible` recommendations;
   bounded trials require explicit selection.
3. Build the complete next Host Profile in memory and snapshot every affected task. New or repaired tasks remain `PAUSED`.
4. Reconcile selected tasks through the native automation control plane, atomically write the Profile only after all changes
   succeed, then re-read both. Restore the task snapshots and prior Profile on any failure.
5. A temporary automation-source canary must prove a terminal native task-index result before one Scout may resume. Delete the
   canary after observation. Failure keeps Scouts paused and does not change the user's enrollment decision.

## Fixed boundaries

- The repository Anchor and plugin are distribution surfaces, not behavior Owners.
- Managed source snapshots are host-local, derived, clean, and replaceable; project worktrees remain user-owned reality.
- Project/global Owner and committed Skills can travel through Git. Local project IDs, paths, Host Profile, Scheduled Task IDs,
  run counts, task history, and unconfirmed Review Packs do not travel and must not be reported as synchronized.
- Same content identity may rebind when exactly one enrolled entry and one discovered project match; ambiguous matches require a
  refreshed user confirmation.
- Do not add a fixed project allowlist, database, candidate Inbox, transcript parser, cross-host lease, automatic Owner write,
  automatic Git publication, or second behavior Owner.
- A CLI-only host may synchronize sources, install Core/Owner/Skills, and pass Doctor, but cannot claim Desktop project activation.
- `canonical_owner=null` is the supported public Core profile: project rules and Doctor remain available, while global mutation and
  Owner parity stay explicitly unavailable until the user supplies a separate commit-bound Owner source.
