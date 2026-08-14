# Workstation Bootstrap 1.8 contracts

This reference owns the external Bootstrap workflow's Deployment Pack, Enrollment Pack, and Host Profile contracts. It does not
extend the Core v1 public contract surface.

## Cold-start source and trust boundary

The stable source identity is a release-manifest-bound Sidecar repository; a canonical Global Owner is an optional private backend.
They are capability authorities, not the host's project enrollment list. A continuity-enabled repository may expose a small
`agent-memory-bootstrap-anchor` plus a repo marketplace; public distribution requires its Anchor to resolve and verify the stable
immutable Release, checksums, manifests, and portable bundle before consuming the commit-bound source manifest. A marketplace entry
alone is not source authority. Neither surface may
contain local paths, project IDs, a fixed business-project list, Owner text, or host activation state.

Bootstrap materializes clean, reconstructable source snapshots only under the active Codex home's
`agent-memory/sources/{sidecar,canonical_owner}` roots. It stages both sources before replacing either target. An existing managed
source must have the expected normalized origin and a clean worktree; identity mismatch or dirty state fails closed. Active project
checkouts are never reset, cleaned, pulled, or overwritten.

All workstation deployment uses `source-cutover --dry-run` followed by exact-hash apply. Fresh install and `noop` are covered by the
user's deployment request; an existing Sidecar identity replacement requires one visible plan and one confirmation. The plan exposes
only hashed source identities and binds the current state, desired release commits, and `keep_owner`/`public_core` action. There is
no force path. An omitted public Owner preserves an existing Owner only when its clean checkout exactly matches Core's bound root and
commit. One-sided, dirty, or mismatched state fails closed. Apply retains source and Skill rollbacks until strict Doctor succeeds.

`managed_sources.py source-cutover` owns the unified source and host transaction: deterministic Core setup, global binding, Doctor,
and per-target atomic Bootstrap/Scout installation. `sync-sources` and `materialize-host` remain lower-level strict contracts and do
not gain implicit identity replacement or Owner discovery. Agent-authored shell sequences are not an alternative production contract.

The source manifest binds each configured source to a credential-free remote identity, ref, and full commit. Public Core mode sets
`canonical_owner=null`; on a fresh host this keeps global parity unavailable without blocking project-scope Core, while a legacy host
may retain an already exact Core-bound Owner. Private Owner authentication uses the host's existing Git credentials. Failure to
authenticate is `source_sync_blocked`, not a request for project paths and not proof that the capability is installed. A newly
installed plugin or Skill is guaranteed automatically discoverable only after one Codex refresh or from a new task; host
materialization finishes in the current deployment task.

## Deployment Pack

`agent_memory_workstation_deployment_pack_v1` has these exact top-level fields:

```text
contract_version, status, display_locale, bootstrap_version, generated_at,
portable_distribution, source_sync, host_materialization, project_activation,
limitations, pack_hash
```

- `status`: `ready`, `reload_required`, `source_sync_blocked`, or `host_materialization_blocked`.
- `display_locale`: `zh-CN`; `bootstrap_version`: `1.8.0`.
- `portable_distribution` exact fields are `repo_anchor`, `plugin`, and `marketplace`; values are `verified`, `installed`,
  `unavailable`, or `failed`.
- `source_sync` contains exact `sidecar` and `canonical_owner` receipts. Each receipt has `status`, `ref`, and `commit`; status is
  `synced`, `unchanged`, `unavailable`, or `failed`.
- `host_materialization` contains Core setup, global binding, Doctor, Bootstrap Skill, and Scout Skill states plus exact versions.
- `project_activation` reports `interactive_entry` independently from `scheduled`. Interactive values are
  `available_next_turn`, `verified`, or `blocked`; Scheduled values are `paused`, `not_configured`, or `unchanged`.
- `limitations` must explicitly retain the real-second-device proof boundary when only a same-host clean-profile test exists.
- `pack_hash` is SHA-256 of canonical UTF-8 JSON excluding `pack_hash`.

The renderer produces one Chinese result table ordered as `portable distribution / source synchronization / host materialization /
project activation`. It never exposes source URLs, absolute paths, project IDs, automation IDs, raw JSON, or credentials.

## Enrollment Pack

`global_owner_scout_enrollment_pack_v1` is a JSON object with these exact top-level fields:

```text
contract_version, status, display_locale, bootstrap_version, generated_at,
portable_layer, discovery, projects, recommended_project_refs, current_automation_count,
automation_change_count, allowed_actions, limitations, pack_hash
```

- `status`: `ready`, `bounded`, or `host_activation_blocked`.
- `display_locale`: `zh-CN`; `bootstrap_version`: `1.8.0`.
- `portable_layer` exact fields: `sidecar`, `canonical_owner`, `core_setup`, `doctor`, `scout_skill_version`,
  `scout_skill_hash`. State values are `synced`, `unchanged`, `installed`, `verified`, `failed`, or `unavailable`.
- `discovery` exact fields: `inventory_status`, `activity_status`, `desktop_project_count`, `accessible_count`,
  `active_count`, `eligible_count`, `enrolled_count`, `task_index_limit`, `limitations`.
- Each project has exact fields: `project_ref`, `display_name`, `identity_kind`, `content_identity_hash`,
  `host_project_ref`, `discovered`, `accessible`, `activity`, `activity_coverage`, `eligibility`, `eligibility_reason`,
  `enrollment_status`, `existing_automation_ref`, `recommended_action`, `recommendation_reason`.
- `identity_kind`: `content` or `host_local`; `activity`: `active`, `inactive`, or `unknown`; coverage is
  `complete`, `bounded`, or `unavailable`; eligibility is `eligible` or `ineligible`; enrollment is `enabled`,
  `deferred`, `excluded`, or `not_enrolled`.
- Recommendations are `migrate_enabled`, `enable`, `trial`, `defer`, `exclude`, `keep`, or `blocked`.
- `recommended_project_refs` contains only accessible, `active + eligible` projects recommended as `enable`, plus eligible
  `migrate_enabled` projects. `trial` is never default-selected.
- `automation_change_count` is always zero in an inspect pack. The count and unique project refs must conserve the Desktop
  inventory exactly.
- `allowed_actions` is exactly `apply_recommended`, `enable_selected`, `defer_selected`, `exclude_selected`, `keep_current`,
  `rescan` when ready/bounded. Host-blocked output may expose only `rescan` and `keep_current`.
- `pack_hash` is SHA-256 of canonical UTF-8 JSON excluding `pack_hash`.

The renderer prints: portable state; explicit interactive Scout availability; discovered/active/eligible/enrolled counts; a table with at most four columns
`项目 / 活跃与覆盖 / 安全条件 / 推荐动作`; warnings; and exact Chinese reply actions. It never displays absolute paths,
raw remotes, project IDs, automation IDs, profile paths, or JSON. When Scheduled capability is blocked, discovery remains
informational and the result does not require enrollment action to use the interactive Scout.

## Host Profile

`global_owner_scout_host_profile_v1` has exact fields:

```text
contract_version, profile_version, updated_at, scout_skill_version, entries, profile_hash
```

Each entry has exact fields:

```text
content_identity_hash, host_project_ref, automation_ref, status, cadence,
time_slot, last_verified_at
```

- `status`: `enabled`, `deferred`, or `excluded`.
- `cadence`: `weekdays_daily` for enabled entries; `none` otherwise.
- `time_slot`: local `HH:MM` for enabled entries; empty otherwise.
- `automation_ref` is required for enabled entries after successful reconciliation and empty otherwise.
- No entry may contain evidence, candidate content, Review Packs, Owner text, paths, raw remotes, task text, or run counters.
- `profile_hash` is SHA-256 of canonical JSON excluding `profile_hash`.

The profile lives under the active Codex home at `global-owner-scout/host-profile.json`. It is host-local, rebuildable, and never
committed or synchronized. Its absence means no v5 enrollment, not permission to infer enrollment from another host.

`status=enabled` records the user's host enrollment decision only. The matching automation may remain `PAUSED` while production
capability is unproven or blocked; it must not be described as production enabled. Actual automation status is re-read from the
host and is not duplicated into the profile.

## Identity and rebinding

For Git projects with a usable remote:

```text
remote_identity = normalize(remote without credentials, query, fragment, or trailing .git)
content_identity_hash = sha256(remote_identity + "\n" + repo_relative_primary_folder)
```

The raw remote is never returned or persisted. Same content identity plus a changed local path or project ID may rebind without
new authorization only when exactly one enrolled entry and exactly one discovered project match. Multiple matches, remote changes,
or identity changes require a refreshed pack and confirmation. A remote-less or non-Git project gets a host-local opaque identity,
is displayed, and is ineligible for isolated periodic execution.

Global Owner source rebinding is a separate host-materialization operation. Bootstrap may request the explicit Core rebind flag only
after the canonical managed checkout passed remote-identity, clean-tree, and commit checks. Core must still reject the migration if
the local global target no longer matches the last recorded binding; the generic `setup` path continues to reject silent rebinding.

## Transaction semantics

`inspect` is read-only for automations and Host Profile. It first synchronizes managed source snapshots and materializes Core,
global binding, Bootstrap, and Scout. Successful installation makes `$global-owner-scout 复盘当前项目`
available independently of Host Enrollment. `apply_enrollment` is reserved for explicit Scheduled retest/configuration and must snapshot profile content and every affected
automation, validate the intended next state, reconcile tasks, atomically write the profile, then re-read both. Any failure restores
all touched state. Project disappearance pauses but does not delete; deletion requires a separate explicit confirmation.

New or repaired enrollment automations are created or updated as `PAUSED`. A disposable automation-source canary must then prove a
terminal `list_threads(limit=50)` result within an externally observed 180-second budget. The canary is deleted after observation.
Failure or a still-running call keeps all affected Scouts paused and reports `host_activation_blocked`; it does not change the
profile enrollment decision. Only one Scout is activated after a passing canary, and the remaining Scouts wait for one real
Review Pack plus one completed user card action.
