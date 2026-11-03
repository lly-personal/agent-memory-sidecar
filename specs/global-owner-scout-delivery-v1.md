# Global Owner Scout Delivery v2

- Status: Accepted
- Owner: project_docs
- Applies to: Scout 5.12 interactive delivery
- Decision: [ADR 0076](../docs/decisions/0076-task-scoped-review-pack-delivery.zh.md)


## Current projection and recovery

Delivery v2 binds Project v6 / Review Pack v7 to immutable Markdown and a derived native interactive fragment. It retains all v1
manifest fields and adds `visual_name`, `visual_sha256`, `visual_bytes`. The Markdown body freezes the map context and visual
descriptor, so later template updates do not invalidate historical recovery. No old report is modified or given a synthetic map.
The context reuses project identity, the full read-only context snapshot, source references and linked advice. `verify-final`
can compare `--project-root` with that snapshot; source changes are distinct from corrupt delivery bytes. Native project binding
must also match before applying current conclusions. A changed snapshot requires relevant source reassessment, not an automatic
thirty-day census or rewriting the old report.

The default receipt contains a short conclusion, complete-evidence link and a verified in-conversation visualization reference.
The reference points only to the direct-child HTML named in the manifest. Rendering a receipt first checks the supplied manifest
against the frozen Markdown descriptor. Recovery validates the HTML independently: missing/changed HTML gives
`visual_status=unavailable`, preserving usable Markdown and exact rule recovery. UI availability never elevates confirmation.
A native follow-up carries report hash and object kind/ID. Persisted widget selection is a convenience, not authority or approval.
Default file opening remains zero; `surface_observation=not_requested` means no file preview was requested, not that inline UI was observed.

Inspect delivers current design with null Owner parity/preview and zero cards; it does not claim a deep review. Review retains
existing rule preview and actual user authorization. Overview, path and matrix projections share evidence layers and source refs.
Historical v1 receipt parsing remains read-only. The following v1 field and safety descriptions apply unchanged where not extended above.

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

The default is `scout.py render-receipt not_requested --artifact-path <exact-file> --artifact-root <original-root>`.
It verifies the same immutable artifact and emits its brief overview, first actionable recommendation, evidence link and compact
receipt. Do not call file preview by default. The brief is rendered from existing Human Context and Owner/action fields inside
one `<!-- scout:brief:start -->` / `<!-- scout:brief:end -->` section of the complete artifact. It participates in the existing
body and file hashes; no manifest field or second persistence record is added. It also presents the current integration action/reason,
qualifies challenged original advice and preserves failed terminal states. Advice consumes the same bytes verified against the manifest.
It does not duplicate rule commands or card headings.
Covered/no-change items are grouped, not decisions; zero actual deltas produce no invented first item or confirmation invitation.

Only an explicit user request opens the file. Pre-render the outcomes, then call native preview once and emit the matching receipt.
All new receipts retain the verified brief and artifact link, including preview failure. No polling or foreground request is needed.

| Outcome | `verify-final` status | Meaning |
| --- | --- | --- |
| `not_requested` | `artifact_verified` | File verified, no open attempted; display unknown |
| `open_succeeded` | `surface_observed` | Recorded native open success; user understanding/adoption unknown |
| `open_queued` | `surface_pending` | Open accepted and queued; display unknown |
| `open_failed` | `surface_unavailable` | Preview unavailable; verified advice remains usable |

`confirmation_eligible` is false except an opened receipt with an actual recovered confirmable bundle. It never grants approval.
Later exact human selections may resume existing Fresh Owner/Core authorization even when the historical surface was unobserved;
this does not rewrite that observation. Native question responses or tool-relayed messages are not assumed to meet Core event binding.
The legacy manifest-only blocked renderer remains a failure receipt and cannot invent a missing artifact path.

## Readback and recovery

Locate the original delivery receipt for the report referenced in the current discussion, using native chat history across
intervening ordinary replies. Do not assume the latest assistant message is a receipt or silently switch to a newer report.
Feed that exact final to `verify-final --artifact-root <original-host-output-root>`. It validates direct-child containment,
immutable file identity, reconstructed manifest, body and action conservation. New advice receipts must match the exact brief
read from that artifact; edits to the advice, link, status or binding fail closed.

Historical opened/queued receipts, including the legacy queued wording, remain readable without migrating the artifact. An old
artifact without a brief may be linked and discussed after verification; never invent an original summary. Recovery returns the
same `manifest` and the existing `recovery_bundle` when present. Missing historical bundle bindings remain null and are not guessed;
refresh only the affected rule preview before new authorization. Accept CRLF/CR and zero to two terminal LF characters; reject
other receipt edits. No new discovery, file, queue, database or controller is needed.

Follow-up is ordinary conversation, not another Delivery receipt. Explain each real delta, recommendation, maintenance Owner,
scope, exception and evidence; support switching items, edits, batch requests and deferral. Reuse current-chat progress. Authorized
project/method work follows existing maintenance and readback; global rule changes retain the existing exact approval flow.
A valid file or concise recommendation is not proof of user comprehension, natural adoption, or revocation experience.

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

A host-open failure occurs after manifest creation and retains the verified advice and link with `surface_unavailable`.
The manifest-only blocked receipt is a legacy compatibility path. Neither is a Terminal v1 reason.

The active Skill calls validators, Owner resolution, rendering, visible verification, delivery, receipts, terminal rendering, and
controller verification only through `scripts/scout.py`. Frozen v4 helpers remain historical compatibility inputs, not competing
active command surfaces.
