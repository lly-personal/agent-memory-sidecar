# Global Owner Scout Delivery v1

- Status: Accepted
- Owner: project_docs
- Applies to: Scout 5.11 interactive delivery
- Decision: [ADR 0076](../docs/decisions/0076-task-scoped-review-pack-delivery.zh.md)

## Purpose

`global_owner_scout_delivery_v1` binds a validated `global_owner_scout_review_pack_v6` to one immutable Markdown artifact in the
current task's host-generated output root. It closes the boundary between deterministic renderer bytes and the actual task surface.
It is an output contract, not a Store record, proposal, approval, Inbox, cross-task bridge, or behavior owner.

## Exact manifest

The manifest has exactly these fields:

```text
contract_version, status, delivery_surface, artifact_name, artifact_sha256,
artifact_bytes, review_pack_hash, visible_body_sha256, project_cards,
visible_cards, visible_action_counts, visible_actions, bundle_action_count,
wrapper_count, delivery_manifest_sha256
```

Required values and invariants:

- `contract_version=global_owner_scout_delivery_v1`;
- `status=prepared` and `delivery_surface=task_artifact`;
- `artifact_name=global-owner-scout-review-pack-<review_pack_hash[0:16]>.md`;
- hashes are lowercase SHA-256; `artifact_bytes` is the exact UTF-8 file length;
- `project_cards == visible_cards == len(visible_action_counts)`;
- `visible_actions == sum(visible_action_counts)`;
- `bundle_action_count` is zero or one; interactive `wrapper_count` is zero;
- `delivery_manifest_sha256` is SHA-256 of sorted compact UTF-8 JSON after removing that field.

The manifest must not contain an absolute path, task/thread/project ID, Review Pack body, evidence body, Owner body, approval,
selection payload, credentials, or persistence state.

## Preparation

`python -B scripts/scout.py prepare-delivery --artifact-dir <host-output-root> --protected-root <project-root>` accepts the complete Review Pack on stdin.
The output root must already exist, be absolute, be a normal directory rather than a link/reparse point, and be outside every
protected root. The helper renders and verifies the complete interactive Markdown, creates a single-link regular artifact with
exclusive semantics, flushes it, reads it back, reruns visible-output verification, and emits the manifest on stdout. An existing
byte-identical artifact is idempotent; any other pre-existing target fails closed.

The only authorized output write is this artifact. The helper must not create a manifest file, project file, temp fallback,
arbitrary `$CODEX_HOME` file outside the explicitly granted task-output root, Store row, Inbox item, database, or cross-task index.
The host may physically place its declared task-output root inside host-managed app storage; the current-task grant, not a path
prefix, is the authority.

## Task surface and receipts

Before the final host call, the Scout pre-renders opened, queued and blocked receipt outcomes from the manifest. Opened and queued
rendering receive the exact artifact path and original output root and recheck direct-child containment, regular read-only file state, bytes, hashes, and
visible-output conservation. It then asks the current task's host file
preview to open the exact artifact. That host call is the last tool call.

- an explicit terminal opened/success result: return the exact compact receipt with the absolute local artifact link and
  `surface_observation=open_succeeded; confirmation_eligible=true`.
- an exact `queued` result: return the exact content-bound receipt with the same absolute artifact link and
  `surface_observation=open_queued; confirmation_eligible=false`; external verification maps it to `surface_pending`.
- `pending`, missing, failed, unobservable, or any other host outcome: return only `interactive_host_blocked` with
  `surface_observation=open_failed; confirmation_eligible=false`.

The full Review Pack is never copied into the final. Technical delivery requires the verified artifact and its link in the
original task. `surface_pending` does not prove display, comprehension or authorization; do not poll opening or require a foreground
switch. The new queued copy explains recovery; historical exact queued receipts remain valid as historical pending evidence.
`confirmation_eligible=false` prevents interpreting the queued outcome as approval/readiness by itself. A subsequent real user
selection of exact content-bound pairs may resume artifact checks and the existing Fresh Core authorization flow; it does not
change the old surface observation or authorize other cards.

## Readback and recovery

Use the actual previous final as stdin to `verify-final --artifact-root <original-host-output-root>` in the same continuation,
or an already authorized controller. The helper validates the exact receipt, direct-child immutable file, reconstructed manifest,
body and per-card action conservation. It returns the reconstructed `manifest` for reuse with the existing receipt commands;
new reports also return `recovery_bundle`, the existing `rule_revision_bundle_v2` payload saved in one collapsed technical block
inside the same artifact. Its bytes participate in the visible-body and Delivery hashes. It contains only cards whose content-bound
selection was actually offered, and is input to a fresh Core preview, never approval. Scheduled inline verification returns the
same payload without requiring a file. Historical artifacts without that block return `recovery_bundle=null`: their file integrity
can recover, but missing original proposal bindings must not be guessed. If the original exact bundle is unavailable, refresh only
the affected preview and request authorization for the new binding; do not claim old-token recovery.
No discovery rerun, new file, queue, database or cross-task bridge is required. It accepts CRLF/CR and zero to two terminal LF
characters, rejecting other semantic/trailing edits. It can read a historical renderer artifact without migrating its contents.

The status describes the recorded receipt and byte integrity. `surface_observed` names a parsed opened receipt; it does not independently prove UI
visibility; `queued` remains unobserved. Source implementation, installed identity, technical delivery, actual UI experience and
later rule adoption are reported separately. No mandatory new controller task or manufactured canary is needed for technical delivery.

## Acceptance criteria

1. 0/1/3/6/7/8/24-card fixtures conserve bytes, hashes, every card, per-card actions, bundle and wrapper.
2. Existing files are reused only when identical; project-contained roots, links/reparse points, multiple hard links, path escapes,
   receipt edits and tampering fail closed. Recovery preserves the original read-only bytes and does not repeat discovery.
3. Covered/no-persistence cards have zero actions and are not counted as required decisions. Evidence and stable card identities
   remain complete; rule text and actions must not be silently summarized or dropped.
4. Queued recovery returns the same manifest and remains pending; no recovered result grants approval or claims UI visibility.
   An exact later user selection still requires verified artifact content, Fresh Owner comparison and Core's existing real-event binding.
5. Local clean/dirty and existing-worktree checks bind explicit project context and the full before/after snapshot, including
   untracked content. Review never changes project, Owner, Store, Git or installed Skill cache.
6. History covers both active/archived partitions to the frozen window boundary/EOF; a 50-item page is not a total cap. Failed
   reads preserve independent evidence and exact coverage gaps.
7. Real installed-entry discovery, display, comprehension, confirmation, adoption and revocation remain unverified until observed;
   tests and installation do not replace these outcomes. Scheduled activation remains independently paused.

## Manifest-free terminal

Failures before a valid Delivery manifest use `global_owner_scout_terminal_v1` rather than a Delivery receipt. Its exact fields are:

```text
contract_version, status, phase, reason_code, project_state,
confirmation_eligible
```

`confirmation_eligible=false`; phase, status, reason, and project state are closed enums validated by the active runtime. The Scout
passes this object to `python -B scripts/scout.py render-terminal`, which emits a path-free Chinese terminal receipt bound to the
canonical object hash. It never shows partial cards. Calling `render-receipt` without a Delivery manifest or hand-writing a failure
receipt is a contract violation.

The exact reason mappings are:

```text
project_binding_unavailable -> interactive_entry_blocked / preflight / unverified
git_worktree_ineligible -> interactive_entry_blocked / preflight / unverified
worktree_projection_unavailable -> interactive_entry_blocked / preflight / unchanged|unverified
execution_protocol_failed -> failed / session_census / unchanged|unverified
read_only_violation -> failed / project_review / changed
privacy_or_contract_failed -> failed / project_review / unchanged|unverified
output_root_unavailable -> interactive_host_blocked / delivery / unchanged|unverified
render_integrity_failed -> render_integrity_failed / delivery / unchanged|unverified
output_budget_exceeded -> output_budget_exceeded / project_review / unchanged|unverified
```

A host-open failure occurs after manifest creation and uses the manifest-bound blocked receipt. It is not a Terminal v1 reason.

The active Skill calls validators, Owner resolution, rendering, visible verification, delivery, receipts, terminal rendering, and
controller verification only through `scripts/scout.py`. Frozen v4 helpers remain historical compatibility inputs, not competing
active command surfaces.
