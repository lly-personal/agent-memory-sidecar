# Global Owner Scout Delivery v2

- Status: Accepted
- Owner: project_docs
- Applies to: Scout 5.15 interactive delivery; legacy receipts remain readable
- Decision: [ADR 0076](../docs/decisions/0076-task-scoped-review-pack-delivery.zh.md)


## Current projection and recovery

Delivery v2 binds Project v7 / Review Pack v8 (also reads Project v6 / Review Pack v7) to immutable Markdown and a derived native interactive fragment. It retains all v1
manifest fields and adds `visual_name`, `visual_sha256`, `visual_bytes`. The Markdown body freezes the map context and visual
descriptor, so later template updates do not invalidate historical recovery. No old report is modified or given a synthetic map.
The context reuses project identity, the full read-only context snapshot, source references and linked advice. `verify-final`
can compare `--project-root` with that snapshot; source changes are distinct from corrupt delivery bytes. Native project binding
must also match before applying current conclusions. A changed snapshot requires relevant source reassessment, not an automatic
thirty-day census or rewriting the old report.

The receipt contains a short conclusion and complete-evidence link. `render-receipt --text-only` omits the native visual reference
without changing evidence, recovery or authorization. The default companion remains available for compatible callers; generating
it does not require showing it for every question. `prepare-delivery --visual-input <absolute-fragment-path>` freezes a different
native composition supplied in the same granted output directory. Its exact UTF-8 bytes replace the default projection in the
existing descriptor and immutable delivery. It need not copy the default template or DOM. Content fidelity is evaluated against
the frozen evidence; a matching digest only proves byte identity. Presentation changes create a new delivery generation, preserving
old files. No new schema, renderer registry or state store is added. When showing a companion, include its verified reference.
The reference points only to the direct-child HTML named in the manifest. Rendering a receipt first checks the supplied manifest
against the frozen Markdown descriptor. Recovery validates the HTML independently: missing/changed HTML gives
`visual_status=unavailable`, preserving usable Markdown and exact rule recovery. UI availability never elevates confirmation.
A native follow-up carries report hash and object kind/ID. Persisted widget selection is a convenience, not authority or approval.
`recover-delivery --object <kind:id> [--journey <id>]` resolves project/node/edge/advice/journey against the verified map and returns
`selected_context` with the selected object, related nodes/edges, visible journey and source references. An unknown selection
fails instead of switching reports. The overview uses the project key, never a fabricated node. An implicitly displayed first
journey is a real selection and travels in both the follow-up prompt and optional widget state. Without these options historical
receipt verification is unchanged. The old map and its descriptor are never rerendered in place.
Default file opening remains zero; `surface_observation=not_requested` means no file preview was requested, not that inline UI was observed.

Inspect delivers current design with null Owner parity/preview and zero cards; it does not claim a deep review. Review preserves rule preview and actual user authorization only for rule candidates; engineering advice has no rule actions. Structure, path, cross-link, evolution, evidence and layered-advice projections share evidence layers and source refs.
Historical v1 receipt parsing remains read-only. The following v1 field and safety descriptions apply unchanged where not extended above.

The reusable overview presentation follows native visual language and overview/drill-down/cross-link/return interaction. Identical native state echoes do not rerender or refocus; programmatic focus prevents scrolling. Optional persistence failure does not block local reading. Host conversation scrolling remains a separate observation. Shared objects retain their selected journey;
opening related advice retains the originating object in best-effort local widget state and offers a return to it. This does not
track maintenance progress or confer approval. Derived advice carries its verified Human Context, ownership and current disposition,
without reproducing confirmation commands. Target-project content is independent of the repository maintaining the renderer.

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

Native preview outcomes (`not_requested`, `open_succeeded`, `open_queued`, `open_failed`) belong to the actual host call
and its observation. Rendered copy does not prove that call happened. A rendered `confirmation_eligible` hint never grants approval.
Later exact human selections may resume Fresh Owner/Core authorization even when historical display was unobserved; preserve
that observation. Native question responses or tool-relayed messages do not substitute for Core's real user-event binding.

## Readback and recovery

Use `recover-delivery --artifact-root <original-host-output-root> --input-file <original-manifest.json>` with the existing
`prepare-delivery` native result for the selected report. Standard input is also supported; no new manifest format or storage
is introduced. Recover the actual producer result from native history, or the explicit report selection; do not build a new
manifest from a candidate file and treat its self-computed hash as provenance. A hash binds content, not the human's intent.

`--report-hash <review_pack_hash>` binds an independent report selection, including a widget's `report_hash`. It is the Review
Pack hash, not `delivery_manifest_sha256`. Resolve the report explicitly selected by the user or the unambiguous current
discussion; do not silently choose the latest. Both recovery entries support `--object`, `--journey` and `--project-root`.
They share direct-child containment, immutable regular-file checks, byte/hash/manifest verification, body/action conservation,
map selection and current-source checks. Changed sources keep historical evidence; recheck affected current facts before action.

`verify-final` remains a compatibility locator for old actual delivery replies, including intervening closeout prose. It extracts
one distinct artifact link and one distinct `delivery_manifest_sha256`, reconstructs the manifest from that file, checks against
the original hash, then uses the same recovery chain. Repeated identical locators are harmless. Different or missing locators
need explicit selection of the original manifest through `recover-delivery`; do not edit the old reply to make it qualify.
Headings, labels, summaries, line endings, Markdown layout, surface copy and confirmation hints are not identity credentials.
Recovery does not certify their accuracy: correct a false statement from the original artifact, without discarding valid evidence.
A wrong UI pointer invalidates that presentation/association claim; only the frozen HTML's own bytes determine `visual_status`.
Missing/tampered HTML does not invalidate verified Markdown. Never treat a verified HTML file as proof that UI was displayed.

Both entries return `status=artifact_verified`, `confirmation_eligible=false`, the verified `manifest`, existing `recovery_bundle`
and map when present. These fields attest data recovery only, even for historical opened/queued receipts. This intentionally
replaces statuses previously inferred from chat copy; downstream consumers must use actual host evidence for display state.
Historical files remain readable without migration. Missing bundle/map stays null; refresh only an affected preview before new
authorization and never invent old tokens. Actual Core checks still require current explicit user approval of the exact content,
selection/scope, Fresh Owner/target state and one-time approval consumption. File recovery does not authorize writes.

Follow-up is ordinary conversation, not another Delivery receipt. Explain each real delta, recommendation, maintenance Owner,
scope, exception and evidence; support switching items, edits, batch requests and deferral. Reuse current-chat progress. Authorized
project/method work follows existing maintenance and readback; global rule changes retain the existing exact approval flow.
A valid file or concise recommendation is not proof of user comprehension, natural adoption, or revocation experience.

## Acceptance criteria

1. 0/1/3/6/7/8/24-card fixtures conserve bytes, hashes, every card, per-card actions, bundle and wrapper.
2. Existing files are reused only when identical; project-contained roots, links/reparse points, multiple hard links, path escapes,
   locator mismatches and artifact tampering fail closed. Recovery preserves the original read-only bytes and does not repeat discovery.
3. Covered/no-persistence cards have zero actions and are not counted as required decisions. Evidence and stable card identities
   remain complete; rule text and actions must not be silently summarized or dropped.
4. Queued recovery returns the same manifest as `artifact_verified`; actual queued display remains unobserved. No recovery grants approval or claims UI visibility.
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

A host-open failure occurs after manifest creation and retains verified advice and the link; actual display failure is separate from `artifact_verified` recovery.
The manifest-only blocked receipt is a legacy compatibility path. Neither is a Terminal v1 reason.

The active Skill calls validators, Owner resolution, rendering, visible verification, delivery, receipts, terminal rendering, and
controller verification only through `scripts/scout.py`. Frozen v4 helpers remain historical compatibility inputs, not competing
active command surfaces.
