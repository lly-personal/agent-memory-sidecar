---
name: agent-memory-bootstrap-anchor
description: Restore Agent Memory workstation capability from a commit-bound public Sidecar release and an optional private Global Owner when the user says “同步并部署本机 Agent Memory”. Use only for cold start or migration; do not use for ordinary project work.
---

# Agent Memory Bootstrap Anchor

This plugin Skill is a cold-start distribution anchor, not the Bootstrap implementation and not a behavior Owner.

1. If `$agent-memory-workstation-bootstrap` is already callable, invoke it in `inspect` mode.
2. Otherwise require the `source-manifest.json` packaged at the plugin root by the portable release bundle. Validate it with the
   bundled Workstation Bootstrap, then use the built-in `$skill-installer` only with its exact repository, immutable ref, and full
   commit to install:
   - `.agents/skills/agent-memory-workstation-bootstrap`
   - `.agents/skills/global-owner-scout`
3. Tell the user that the next task is the reliable Skill discovery boundary. In that task, invoke
   `$agent-memory-workstation-bootstrap` in `inspect` mode.

Do not guess a source manifest or fall back to a branch when the packaged file is absent; report the portable distribution as
incomplete. Do not ask for local paths, project IDs, a project list, model settings, or Scheduled configuration. Do not modify Scheduled tasks
or Host Profile. Do not claim host materialization before the installed Bootstrap verifies Core, Owner, Skills, and Doctor.
`canonical_owner=null` is valid public Core mode; do not search for or synthesize another Owner.
