---
name: agent-memory-bootstrap-anchor
description: Restore Agent Memory workstation capability from a verified immutable public release and an optional private Global Owner when the user says “同步并部署本机 Agent Memory”. Use only for cold start or migration; do not use for ordinary project work.
---

# Agent Memory Bootstrap Anchor

This is a cold-start distribution anchor, not the Bootstrap implementation and not a behavior Owner.

When the user says `同步并部署本机 Agent Memory`:

1. Run `python -B scripts/resolve_release.py --output <new-path-under-a-temporary-parent>`. Use `--version <vX.Y.Z>` only when
   the user selected an explicit version. The resolver must return `agent_memory_release_resolution_v1 / verified`; it validates
   one stable immutable GitHub Release, tag/commit identity, GitHub asset digests, `SHA256SUMS`, release/source manifests, and the
   portable bundle before writing its output. `release_resolution_blocked` ends the operation: do not guess an asset, ask for a
   checkout, or fall back to a branch or private repository. This resolver contract starts with the complete `v0.3.1` public
   operations release; earlier releases remain historical artifacts rather than valid cold-start inputs for this Anchor.
   GitHub API metadata may use an explicit `GITHUB_TOKEN`/`GH_TOKEN` or existing non-interactive `gh` authentication. Never render,
   persist, or pass that token to release asset URLs; rate limiting or invalid authentication remains a visible blocker.
2. Read `portable_root` from the verified result and execute the formal Bootstrap script only from that safely materialized portable
   directory. Run `managed_sources.py workstation-reconcile --dry-run` with the resolved `source-manifest.json` and
   `release-manifest.json` for the active Codex home. This one plan compares desired Release identity with actual Marketplace,
   Plugin, managed source, runtime, and Skill state:
   - fresh installs and same-source ref/version repairs are authorized by the user's deployment request;
   - a Sidecar or Marketplace source identity replacement requires `render-reconcile-plan`, one rendered confirmation, another
     dry-run, and only the fresh hash may apply;
   - an explicitly disabled Plugin, Owner ambiguity, unreadable state, dirty tracked source, unresolved ref, or stale plan stops.
3. `workstation-reconcile --apply` owns Plugin/Marketplace compensation, source synchronization, Core/global Owner materialization,
   Doctor, atomic Bootstrap/Scout installation, and exact readback. Return its Chinese Deployment Pack v2. A successful mutation
   ends at `reload_required`; ask for exactly one Codex Desktop refresh, not another source choice or command sequence.
4. In the refreshed new task, resolve the same current Release and rerun dry-run. When the plan is exact `noop`, run
   `workstation-reconcile --verify-consumer` instead of apply. Only that read-only new-task check may return `ready`.

Compatibility: published Anchor 1.x calls `source-cutover` after resolving a Release. Bootstrap 2.0 recognizes only that complete
Resolver directory shape and routes the legacy command and renderer through this same Workstation Reconcile v2 plan/transaction.
Do not ask the user to run an intermediate migration or perform a second refresh.

Fixed boundaries:

- A repository checkout or Marketplace registration is a discovery surface, not public installation authority.
- Do not delegate to an already installed Bootstrap before resolving the selected Release; it may be an older implementation and
  is not authority for the requested update.
- Do not ask for a local path, Codex project ID, project list, model, reasoning, Speed, or Scheduled configuration.
- Do not create, resume, update, or delete Scheduled tasks and do not write a Host Profile.
- Do not copy Bootstrap or Scout logic into this Anchor. The verified portable Sidecar release owns that logic.
- Do not claim task history, Host Profile, Scheduled state, unconfirmed Review Packs, or model adoption synchronized across hosts.
- `canonical_owner=null` means the public release does not distribute an Owner. Bootstrap may preserve an existing clean Owner only
  when its managed checkout and Core binding root/commit match exactly; otherwise it fails closed. It must not search for,
  synthesize, or silently detach another Owner. Authentication failure for an explicitly configured private Owner is a visible
  source-access blocker.
