---
name: agent-memory-bootstrap-anchor
description: Restore Agent Memory workstation capability from a verified immutable public release and an optional private Global Owner when the user says “同步并部署本机 Agent Memory”. Use only for cold start or migration; do not use for ordinary project work.
---

# Agent Memory Bootstrap Anchor

This is a cold-start distribution anchor, not the Bootstrap implementation and not a behavior Owner.

When the user says `同步并部署本机 Agent Memory`:

1. Check whether `$agent-memory-workstation-bootstrap` is already callable. If yes, invoke it in `inspect` mode.
2. Otherwise run `python -B scripts/resolve_release.py --output <new-path-under-a-temporary-parent>`. Use `--version <vX.Y.Z>` only when
   the user selected an explicit version. The resolver must return `agent_memory_release_resolution_v1 / verified`; it validates
   one stable immutable GitHub Release, tag/commit identity, GitHub asset digests, `SHA256SUMS`, release/source manifests, and the
   portable bundle before writing its output. `release_resolution_blocked` ends the operation: do not guess an asset, ask for a
   checkout, or fall back to a branch or private repository. This resolver contract starts with the complete `v0.3.1` public
   operations release; earlier releases remain historical artifacts rather than valid cold-start inputs for this Anchor.
   GitHub API metadata may use an explicit `GITHUB_TOKEN`/`GH_TOKEN` or existing non-interactive `gh` authentication. Never render,
   persist, or pass that token to release asset URLs; rate limiting or invalid authentication remains a visible blocker.
3. Use the built-in `$skill-installer` only with the exact repository, immutable ref, and full commit in the verified
   `source-manifest.json` to install:
   - `.agents/skills/agent-memory-workstation-bootstrap`
   - `.agents/skills/global-owner-scout`
4. Explain that the next task is the reliable Skill discovery boundary. In that task, invoke
   `$agent-memory-workstation-bootstrap` in `inspect` mode; it owns source synchronization, Core/global Owner materialization,
   Doctor, local project discovery, and the Chinese deployment result.

Fixed boundaries:

- A repository checkout or Marketplace registration is a discovery surface, not public installation authority.
- Do not ask for a local path, Codex project ID, project list, model, reasoning, Speed, or Scheduled configuration.
- Do not create, resume, update, or delete Scheduled tasks and do not write a Host Profile.
- Do not copy Bootstrap or Scout logic into this Anchor. The canonical Sidecar release owns that logic.
- Do not claim task history, Host Profile, Scheduled state, unconfirmed Review Packs, or model adoption synchronized across hosts.
- `canonical_owner=null` is valid public Core mode; do not search for or synthesize another Owner. Authentication failure for an
  explicitly configured private Owner is a visible source-access blocker.
