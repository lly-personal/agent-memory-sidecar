# Global Owner Scout Delivery v1

- Status: Accepted
- Owner: project_docs
- Applies to: Scout 5.7 interactive delivery
- Decision: [ADR 0076](../docs/decisions/0076-task-scoped-review-pack-delivery.zh.md)

## Purpose

`global_owner_scout_delivery_v1` binds a validated `global_owner_scout_review_pack_v4` to one immutable Markdown artifact in the
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

The full Review Pack is never copied into the chat final. `surface_pending` restores artifact discoverability without claiming that
the user surface opened. It is not success, does not enable confirmation, and does not count toward Production qualification.

## External qualification

A separate controller reads the actual Scout task final and runs
`python -B scripts/scout.py verify-final --artifact-root <host-output-root>`. It must parse the exact opened or queued compact receipt,
constrain the linked file to that root, validate the reconstructed manifest hash, read and hash the artifact, and rerun visible-output
verification. `status=surface_pending` proves an intact, discoverable artifact but not an opened user surface. Only
`status=surface_observed` proves this task's delivery surface. Internal validation, `prepared`, file existence, queued host-open, or
host-open invocation alone does not prove Production.

The controller normalizes CRLF/CR to LF and may remove exactly one additional terminal blank line observed in the Desktop final
envelope. It rejects three or more terminal newlines, spaces, tail notes, field changes, missing fields, or any other receipt rewrite.

`interactive_project_scout` remains `production_unproven / interactive_host_blocked` until the five-scenario entry matrix passes:
Local clean automatic projection, Local dirty automatic projection, already-worktree execution, explicit thread-page terminal
degradation, and missing-output-root Terminal v1. Happy-path cases additionally require artifact open, actual-final readback,
artifact verification, and project/Owner/Store/Git read-only checks.
Scheduled Scout remains independently production-blocked.

Before task creation, the external controller must bind the exact installed Scout version and content identity resolved by the
formal `$global-owner-scout` entry. A newer Skill file in the task worktree is not runtime adoption. A task that resolves another
version, lacks Delivery v1, or returns the legacy inline renderer envelope is `ineligible / runtime_skill_identity_mismatch` and
does not count toward the five-scenario matrix.

## Acceptance criteria

1. 0/1/3/6/7/8/24-card fixtures conserve file bytes, hashes, cards, per-card actions, total actions, bundle action, and wrapper.
2. Project-contained roots, link/reparse targets, multi-link artifacts, conflicting existing bytes, write/readback changes, receipt
   edits, path escapes, and artifact tampering fail closed.
3. No failure path emits partial cards or enables confirmation.
4. An exact queued receipt remains content-bound, externally verifies as `surface_pending`, exposes the complete artifact link, and
   never enables confirmation or counts toward Production qualification.
5. One host-added terminal blank line is the only accepted final-envelope normalization; any other trailing or semantic edit fails.
6. The reviewed project, Owner, Store, Git state, and installed Skill cache remain unchanged.
7. Review Pack v4 and `selection_token` remain unchanged; user confirmation continues through `rule_revision_bundle_v2` Fresh
   recomputation.
8. Canary eligibility binds the installed runtime Skill identity before task creation; mismatched or legacy consumers never count.

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
