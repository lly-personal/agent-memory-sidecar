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
   directory. Run `managed_sources.py source-cutover --dry-run` with the resolved `source-manifest.json` for the active Codex home.
   This is the unified fresh/update/legacy inspection path:
   - a plan containing only `:install`, or `noop`, is already authorized by the user's deployment request; consume the exact plan
     hash immediately.
   - any `:replace` changes an existing source identity. Pipe the plan to `managed_sources.py render-cutover-plan`, ask for the one
     rendered confirmation, then rerun dry-run and apply only the fresh hash.
   - any Owner ambiguity, dirty source, unresolved ref, or stale plan stops the operation. Never ask the user to assemble a combined
     private/public manifest merely to preserve an already healthy Owner.
3. `source-cutover --apply` owns source synchronization, Core/global Owner materialization, Doctor, and atomic Bootstrap/Scout
   installation. Return one Chinese layered receipt. Explain that one Codex refresh or new task is required only for automatic
   discovery of newly installed Skills; do not defer host deployment to that task.

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
