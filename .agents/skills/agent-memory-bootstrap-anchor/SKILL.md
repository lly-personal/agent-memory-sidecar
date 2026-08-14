---
name: agent-memory-bootstrap-anchor
description: Restore Agent Memory workstation capability from a commit-bound public Sidecar release and an optional private Global Owner when the user says “同步并部署本机 Agent Memory” in a continuity-enabled repository. Use only for cold start or migration; do not use for ordinary project work.
---

# Agent Memory Bootstrap Anchor

This is a cold-start distribution anchor, not the Bootstrap implementation and not a behavior Owner.

When the user says `同步并部署本机 Agent Memory`:

1. Check whether `$agent-memory-workstation-bootstrap` is already callable. If yes, invoke it in `inspect` mode.
2. Otherwise require the signed/checksummed portable release bundle and its root `source-manifest.json`; a repository checkout or
   floating marketplace entry alone is not a public installation authority. If a plugin or Skill was newly installed, explain that
   the next task is the reliable discovery boundary and do not claim host materialization in this task.
3. Use the built-in `$skill-installer` only with the exact repository, immutable ref, and full commit named by that manifest to install:
   - `.agents/skills/agent-memory-workstation-bootstrap`
   - `.agents/skills/global-owner-scout`
4. On the next task, invoke `$agent-memory-workstation-bootstrap` in `inspect` mode. It owns source synchronization, Core/global
   Owner materialization, Doctor, local project discovery, and the Chinese deployment result.

Fixed boundaries:

- Do not ask for a local path, Codex project ID, project list, model, reasoning, Speed, or Scheduled configuration.
- Do not create, resume, update, or delete Scheduled tasks and do not write a Host Profile.
- Do not copy Bootstrap or Scout logic into this Anchor. The canonical Sidecar source owns that logic.
- Do not claim task history, Host Profile, Scheduled state, unconfirmed Review Packs, or model adoption synchronized across hosts.
- `canonical_owner=null` is valid public Core mode; do not search for or synthesize another Owner. Authentication failure for an
  explicitly configured private Owner is a visible source-access blocker.
