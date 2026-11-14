# Global Owner Scout contracts

## Current project-map contracts

`capture-native` seals one complete returned JSON object as private raw evidence using the same output protection and
immutable writer; it performs no history read and grants no source, session/project, call-success or coverage qualification.
Indexes and errors remain their original objects. Its `raw_file` can feed `import-history` only when that original payload
meets the existing history contract below. The executable transport examples live in [Phase 1](deep-review-protocol.md#mechanical-native-object-transfer).

Native history import is a private artifact operation, not another project/result Owner. `import-history`
accepts one actual read_thread response plus independently resolved session/project identity, writes one
content-addressed native export and index in the granted root, and preserves cursor/truncation metadata.
The receipt never claims that the source was understood or that the full chat was read. Re-importing the
same page reuses read-only bytes; changed pages create new identities. No database/transcript discovery.
Both writes/readback hold the output directory identity: Windows denies ancestor write/delete sharing, POSIX
uses relative directory descriptors. Concurrent redirection cannot send private pages into a protected
project. Missing containment blocks; it never loosens system security or retries by another writer.
Use `--input-file` with existing validation/preparation commands. `describe-input project|review` describes Codex v7/v8;
`describe-input native-project|native-review` describes Pi/Claude v8/v9, including observed-only coverage. Both use the
shared validator. These helpers do not synthesize missing semantic evidence.

New results use Project v7, Review Pack v8 and Delivery v2. Historical Project v5/v6 and Review Pack v6/v7
remain readable; do not rewrite old artifacts or infer a missing map. The definitions below remain the review lane's shared
fields. Project v6 additionally requires `purpose` (`inspect` or `review`) and `project_map`.

Project v7 retains those fields. Each edge adds `kind`: `contains`, `depends_on`, `constrains`, `implements`, `handoff`, or `evolves`.
Containment is acyclic; shared ownership may have multiple parents. Other relations may be cyclic. Unknown hierarchy does not
block independent nodes or journeys. Claims carry the reasons, conditions and evidence of decisions; do not invent dates or edges.
`depends_on` points from the dependent to its prerequisite; `constrains` points from a constraint to what it limits.
These relations retain their source claims, including permission limits and unresolved or conflicting evidence.

V7 engineering cards have `kind=engineering`, nullable `parent_card_id`, `card_id`, `human_context`, `evidence_level`,
`normalized_evidence_hash`, `owner_recommendation`, `direct_evidence`, `owner_rationale`, `anti_examples`, `privacy_check`,
`unproven`, `benefit_hypothesis`, `implementation_cost`, `validation_conditions`, `alternatives`, `project_claim_hash`.
Each alternative has `approach` and `tradeoff`. Evidence may be E1/E2/E3; E1 is a discussion hypothesis, never implementation
authority. No accepted change, rule body, project-support count or invented failure is required. Parent links must identify
another engineering card and remain acyclic; no depth or size ceiling. Compare the relevant alternatives, including substantial
refactoring when supported; do not require proof that every smaller option failed. Uncertainty and migration costs remain visible.
Legacy-shaped rule candidates retain their existing eligibility and exact authorization requirements. Engineering cards only
route to project or Skill owners. Their Review Card uses `recommended_action=discuss`, `allowed_actions=[]`,
`integration_preview=null`, `selection_token=null`; `owner_parity=null` is valid when there are no rule candidates.
The new map recovery context includes `project_contract`; legacy context stays readable without regeneration.

`project_map` has exact fields `title, goal, boundary, observed_at, source_revision, nodes, edges, journeys, coverage`.
Each node has `id, label, kind, summary, owner, evidence_refs, claims, card_ids`.
Each v7 edge has `id, source, target, kind, label, evidence_refs, claims, card_ids`; v6 omits kind.
Each claim has `layer, environment, statement, evidence_refs`; layers are `design, implementation, observed, inference, unknown`.
Each journey has `id, label, entry, edge_ids, outcome, recovery, evidence_refs, card_ids`.
Each coverage item has `dimension, status, explanation, evidence_refs`; status is `covered, partial, unknown, not_applicable`.
IDs are unique within their kind; edges resolve nodes; journeys form a connected directed path from entry. All evidence refs
resolve declared available/degraded sources, and card IDs resolve actual Project Cards. Unknown claims and uncovered dimensions
remain explicit; no synthetic edge or fixed dimension quota proves completeness. Source revision binds the read-only proof's HEAD. Recovery also retains the existing project identity and full after-context snapshot hash, including dirty/untracked state; a matching HEAD alone does not prove currentness.

Selection recovery is a view of this same map. Without an explicit journey, a node, edge or linked advice recovers all recorded
journeys containing it (including a node's containment ancestors); it does not choose one silently. An explicit journey keeps
that path. Include its containment ancestry and recursively recorded prerequisites/constraints, never unrelated dependent
branches. Historical v6 relations have no typed prerequisite semantics. Preserve journey outcomes/recovery, claim layers and
evidence sources. `selected_context` also carries `purpose, project_key, project_identity, context_snapshot_hash, goal, boundary,
observed_at, source_revision, coverage` and the optional `project_contract`. Coverage remains project-wide, not proof that this
selection is complete. The `verify-final` entry adds its actual `source_status` and optional `source_reason` to this context;
`not_checked`, `changed` and `unavailable` never grant currentness, execution or mutation authority. No missing journey is invented.

Inspect uses `status=view_ready` (or `degraded` with limitations), `evidence_window.kind=current`, and `session_coverage=null`.
Events, observations and cards are empty. Session sources are not applicable. Review Pack has `owner_parity=null`,
`selection_preview=null` and no review actions. Inspect never runs Owner resolution or Core preview. Review retains its actual
census, discovery dispositions, Owner comparison and exact confirmation boundaries.

The renderer freezes the map and its declared source/linked-advice context in the same Markdown body hash. Delivery v2 adds
`visual_name, visual_sha256, visual_bytes` for its evidence-bound native HTML projection. The reusable overview template is optional; another composition may be supplied through prepare-delivery --visual-input. No particular diagram, interaction or content grouping is required by these byte bindings. The projection is presentation, not another
state store. Missing or changed HTML is reported separately and cannot block verified Markdown discussion or grant approval.
The initial preparation verifies both files; recovery never repairs an old artifact silently. Native follow-up messages carry
the report hash, object kind and ID; widget state is best effort and cannot replace this binding or Core authorization.
The target project's journeys are ordered by user outcomes; the overview explains overall responsibilities; the first journey is not the whole architecture. Names, counts, tools, owners and
environments are evidence-derived, never a fixed Sidecar topology. Derived advice preserves Human Context, owner recommendation
and rationale, current recommended action/reason and unproven scope. It contains no confirmation token or duplicate rule text.
Covered advice remains in the frozen report but creates no UI task; challenged advice retains its current clarification status.
Older contexts without these fields stay readable from their original artifacts rather than being regenerated or embellished.

## Native session source snapshots

The existing `import-history` operation also accepts a mechanically exported Pi session:

```text
contract_version = global_owner_scout_native_session_v1
native_host = pi
session = the unmodified SessionManager.getHeader() object (session format 3)
entries = the unmodified SessionManager.getEntries() array
```

`scripts/native_session_export.mjs` exports this object from the current host's read-only session manager.
It reads no files, lists no sessions and does not create a project identifier. Pass its returned object through
host orchestration to the same `import-history` entry, with the exact expected native session ID, project root
and already granted artifact root. Do not transcribe the payload or supply a directory merely because it is writable.
The importer retains the original objects, verifies session/root identity, and uses the existing immutable output guards.
Codex page input and its `global_owner_scout_history_page_v1` index remain unchanged. Pi returns a
`global_owner_scout_history_page_v2` index with `native_host`, `entry_ids` and `record_count`; entries are not renamed turns.

The same operation accepts a scoped Claude SDK page:

```text
contract_version = global_owner_scout_native_page_v1
native_host = claude
session = the unmodified getSessionInfo(session_id, {dir}) result
messages = the unmodified getSessionMessages(session_id, options) result
page_request = {offset, limit, includeSystemMessages: true}
```

`exportClaudeSessionPage(sdk, {project_root, session_id, offset, limit})` calls the official SDK with an explicit
project directory, checks the native session/workspace identity before reading messages, and returns this object.
The project root must be absolute, the session ID nonempty, offset a nonnegative integer and limit a positive integer;
invalid page requests fail before either SDK call.
The importer checks every message's native session/UUID and preserves the request separately from response records.
Its v2 index contains `message_ids`, `record_count` and `page_request`; it invents no cursor, EOF or task terminal.

These are native source snapshots, **not** qualified Pi/Claude Scout entries or proof of native project binding,
complete project history, native task termination, or output authorization. Pi's current SDK can skip malformed
history lines and turn directory errors into an empty list. Neither a successful export nor a final assistant
message may be promoted to `native_index_completed`, a task terminal result or full Scout qualification.
Missing host binding/output grants still block the full entry. Claude SDK source identity is distinct from
Desktop association; only a claim about Desktop requires that additional association. Do not fabricate Codex-shaped pages.

## Common rules

### Native-session hosts (candidate)

Pi/Claude use `global_owner_scout_project_v8` with `global_owner_scout_review_pack_v9`;
Codex and historical v5–v7 projects/v6–v8 packs retain their original interpretation.
V8 retains the v7 map and advice fields. Its review `session_coverage` has exact keys
`native_host, scopes, discovered_task_count, selected_task_count, fully_read_task_count, status, discovery_methods`.
`native_host` is `pi` or `claude`; each scope has `kind, coverage, record_count, evidence_refs`.
Kinds are `project_sessions` or `session_messages`; coverage is `observed_only`, `unknown` or `failed`.
Refs resolve declared Session evidence; every scope explicitly exposes what the SDK returned or could not prove.
Counts are nonnegative and `fully_read_task_count <= selected_task_count <= discovered_task_count`.
These source APIs cannot prove loss-free history, so both coverage and review status are `degraded`,
`fully_read_task_count` is zero, and methods are exactly `native_scoped_sources_observed`.
Neither a successful nor empty SDK result earns `complete`; Codex active/archived partitions are never invented.
Existing independent non-Session corroboration for advice under degraded coverage still applies.
The native candidate accepts engineering advice only, with no rule confirmation actions. The existing Global Owner/Core
preview remains Codex-bound; migrating rule confirmation is separate work, not inferred from native source or map support.

Before history reads, mechanically export the actual current Pi ExtensionContext or Claude native `system/init`
with `native_session_export.mjs`, then call `inspect-native --project-root <bound-root>`.
The `global_owner_scout_native_context_v1` envelope has `native_host, context` in addition to its version.
Pi context contains native `cwd, session_id, session` (the untouched session header) and `mode`;
Claude programmatic context is the untouched current `system/init` object, not a historical SDK session summary.
The ordinary Claude Skill instead forwards current native substitutions with exact fields
`source_kind=claude_skill_substitution, cwd, project_dir, session_id, skill_dir, plugin_root`. This is a distinct provenance
variant, never a synthesized init event. `project_dir` is the native startup substitution; `cwd` is the inherited helper
process directory, not a replacement authority. The helper must run in the current tool context without changing cwd to
match the startup path. `inspect-native` rejects disagreement between their Git roots (including a worktree switch), checks
the running Skill's physical location and Git root,
and returns `binding_scope=native_skill_substitution_git`. Substitution values must come from the current loaded
Skill, not historical material or guessed shell state; CLI fixtures do not qualify natural invocation.
The dispatcher derives the Git root from the native cwd, or checks an explicitly supplied root, and returns
`global_owner_scout_native_binding_v1` with the source hash and existing Git preflight snapshot.
This is the session-host equivalent of current-task/workspace binding; it does not invent a Desktop inventory or association.
The caller must pass its actual live native object through host code; a copied old context or model-authored JSON is not
current invocation proof. A frozen prior context remains evidence only of that prior invocation.
Pi's native package registers the read-only `global_owner_scout_context` tool and the shared Scout Skill.
Its default returns the actual ExtensionContext snapshot without history or writes. `capture_current` requires the exact current
authorized artifact_dir, derives the Git protection root, checks containment before reading entries, and calls the existing
immutable importer with a mechanically forwarded SDK snapshot. Python is resolved once from existing absolute PATH directories
outside the reviewed Git workspace (no implicit current-directory search), followed by a
version/executable readback, then the observed absolute interpreter is used with `-E -s -B` and UTF-8 for the standard-library helper.
Child cancellation inherits the native tool signal. No credentials, model request, permission change,
private parser or second writer is introduced. Root derivation appears only in the private binding receipt, never public evidence refs.
Git probes likewise use an absolute PATH executable outside the reviewed workspace; project-supplied runtime names are not executed.
Git-source paths and portable-archive paths are projected from the same package manifest; no second method source is maintained.

Claude's root marketplace entry explicitly selects the two existing plugin methods and the shared Scout directory.
The portable producer projects only paths and generates root plugin metadata for native local-plugin consumption;
it never copies a second Scout method. Ordinary invocation is `/agent-memory-sidecar:global-owner-scout`.
The loaded Skill supplies session/project/Skill/plugin paths through native Markdown substitutions, with no
dynamic shell injection, permission grant, Hook, model override or private transcript parser.
`claude_native.mjs context|capture` resolves the existing Python helper, validates current binding before history,
and, for capture, checks the current authorized output before using the scoped official SDK and immutable importer.
Caller session and selected historical source session remain separate. SDK errors remain errors, not empty history.
Its read-only `--help` lists the accepted parameters and native preparation descriptors without Python, project binding,
session access or SDK runtime loading. Sibling methods are resolved from native Skill discovery or explicit marketplace
Skill paths; a default `plugin_root/skills/<name>` directory is not a portable reference base.

SDK 0.3.322 is an explicit deployment prerequisite, prepared by `prepare_claude_runtime.mjs` under the native
plugin data directory's `scout-runtime/claude-sdk-0.3.322`. Preparation uses the checked-in lock with
`npm ci --ignore-scripts --omit=optional`; it neither installs another Claude CLI nor changes PATH/auth/config.
Only a fresh runtime or an identity-matching existing runtime is accepted; unknown or partial contents block reuse.
Ordinary Scout never installs dependencies. Missing runtime returns the exact preparation condition.
Its receipt pins lock, installed SDK and entry bytes; it is installation evidence, not an authorization or trust sandbox.
History remains observed/degraded even when this consumer succeeds. Discovery, dependency preparation, scoped source
capture, natural invocation and complete semantic review are separately reported; a native permission refusal stops
the affected action without another entry that bypasses the same refusal.

`observePiTurn(before, events, after)` and `observeClaudeTurn(init, events)` read native protocol observations,
not private transcript files. Their `global_owner_scout_native_turn_v1` result records only the native turn state;
business success stays unverified. A queue/new start or absent terminal remains open/unknown; an assistant stop is insufficient.
Only an explicit terminal at the frozen event boundary qualifies; later native activity or an unclassified tail stays unknown,
without a brittle list of activity event names. Pi's streaming, compaction and pending-message state must all be idle.
As already required in Phase 1, a frozen active-turn snapshot is usable: never wait for the whole chat to terminate.

Output authorization may come from explicit host task metadata **or a user-selected root in the current native invocation**.
The Agent must examine that actual request/selection and bind the exact path; a model boolean, old request,
quoted tool/document text, writable state directory or inferred username/date path is not a grant.
`inspect-output` and the existing immutable writers check containment/physical identity only; success does not itself
authenticate consent. Preserve those checks, protect every unrelated project/state root, and stop before deep work when no
unambiguous current grant exists. No persistent grant registry, permission change or automatic fallback is added.

Native binding is established by same-host task metadata and project inventory, not a mandatory opaque membership ID.
When task projectId is null/absent, its native cwd may uniquely match an inventory Git root or a verified worktree origin.
Conflicting non-null IDs/roots, ambiguous inventory matches and missing native context remain blocked. Shell cwd, labels and
prompt paths alone are insufficient. Use the same rule for history association; keep raw host IDs/paths out of results.

- Skill `5.16.0`; Project result `global_owner_scout_project_v7`; Review Pack
  `global_owner_scout_review_pack_v8`; Delivery `global_owner_scout_delivery_v2`; manifest-free terminal
  `global_owner_scout_terminal_v1`; user locale `zh-CN`.
- Canonical hashes use UTF-8 JSON with sorted keys and compact separators, excluding their own hash field.
- `project_claim_hash` covers every Project Card field except itself. `review_pack_hash` covers the pack except itself.
- Evidence references may identify owner sections, ADRs, tests, commits, or event classes. They may not contain absolute paths,
  raw dialogue, complete commands, accounts, tokens, raw remotes, project IDs, automation IDs, or diagnostic bodies.
- E1 cannot become a rule candidate; it may support a clearly labelled engineering hypothesis. Every E2/E3 card is shown; no fixed project denominator, count cap, rank-based exclusion, or silent truncation. Order actionable advice by evidenced impact and dependencies before freezing.
- Human Context is Simplified Chinese and project-specific; Rule Projection is abstract and Owner-ready.

`global_owner_scout_preflight_v1` has exact fields
`contract_version, git_repository, execution_context, head, status_sha256, staged_diff_sha256, unstaged_diff_sha256,
untracked_files_sha256, context_snapshot_sha256`. It emits no path. `execution_context` is `local` or `linked_worktree`; the snapshot
hash covers every other field. Invoke it only through `python -B scripts/scout.py inspect-context --project-root <bound-project-root>` before any deep read.

## Project result

### Discovery trace (Project v5 / Review Pack v5)

The v5 contracts replace v4; old payloads must be regenerated, not filled with
synthetic evidence. Top-level fields are retained. The following nested fields
are exact and required:

- `evidence_sources`: `kind, status, coverage, refs, uncovered`. Kinds include
  `sessions, owners, decisions, successes, failures, acceptance`; all six are
  declared, including unavailable or not-applicable categories. Status is
  `available, degraded, unavailable, not_applicable`. `refs` contains existing
  `{type, ref, summary}` evidence references; `uncovered` lists concrete missing
  scope. Available sources have refs, degraded/unavailable sources have gaps,
  and not-applicable sources have no refs and explain why in coverage. Owners
  cannot be not-applicable. Active knowledge is not limited by the Session window.
- Events keep their fields. IDs are unique; direct evidence resolves to declared
  available/degraded source refs. Every event is accounted for by an observation.
- Observations: `observation_id, evidence_level, summary, direct_evidence,
  event_ids, disposition`. Levels are E1/E2/E3 for signals, not automatic
  candidate eligibility. Disposition is `kind, reason, card_ids, owner_refs,
  local_scope, portable_delta`. Kinds are `candidate, already_covered,
  project_only, skill_only, insufficient_evidence, not_reusable`.
  Every observation cites declared sources and valid event IDs. Its local
  implementation and portable behavior are compared explicitly, including why
  no distinct portable delta exists. Existing-owner exclusions cite exact
  declared Owner refs; weak exclusions name missing evidence in reason. E1 cannot
  produce a rule-candidate card. A rule candidate links at least one event and matching-level cards; its evidence
  is contained in the linked events and observation. An engineering candidate may be E1 and have no events;
  its direct source evidence must still be contained in its observation. All cards are linked
  exactly once. Other dispositions have no cards. Routing a project-owned fact
  does not by itself exclude a different portable behavior candidate.
- The same ref has identical `type/ref/summary` in every source, event, observation
  and card occurrence. Card evidence refs resolve to declared sources. `normalized_evidence_hash`
  is the canonical SHA-256 of `direct_evidence`; all evidence used by a card must
  be in its observation. Human-context refs are a subset of card evidence refs.

Successful discovery requires available Owners and no unavailable/degraded
non-Session category; otherwise use `degraded` with explicit limitations while
preserving supported cards. Degraded or unavailable Sessions require at least one
non-Session formal source on every retained card; semantic independence still needs review.
`no_material_delta` requires nonempty observations,
zero cards and complete/bounded Session coverage. It means only no qualified
delta in the declared covered scope. Empty observations cannot prove exhaustion.
Failed/preflight results may omit unvisited categories and observations.

Validation proves trace consistency, not semantic completeness or truth. A
separate blind source exercise with an independently held rubric checks important
learning recall, correct exclusions and useful abstraction; it never imposes a
card quota. Future-task adoption and revocation remain separate acceptance.

`global_owner_scout_project_v7` has these exact top-level fields (v6 shares these fields; legacy v5 omits purpose and project_map):

```text
contract_version, mode, status, display_locale, project_key, project_identity,
run_id, task_id, skill_version, evidence_window, model_observation, owner_snapshot,
session_coverage, evidence_sources, events, observations, project_cards,
read_only_proof, limitations, purpose, project_map
```

`project_identity` exact fields:

```text
identity_kind, content_identity_hash, host_project_ref_hash,
git_worktree_eligible, binding_status
```

Identity kind is `content` or `host_local`; binding is `bound`, `rebound`, or `ambiguous`. Raw local project IDs, paths, and remotes
are forbidden. A Scheduled v5 run requires `content`, worktree eligibility, and non-ambiguous binding. Project identity
uses the existing `project_content_identity_v1` projection owned by Bootstrap's `enrollment.py inspect-project`, with the
already validated native primary folder/reference. Raw-URL hashing is not that projection. Do not invent an opaque value to satisfy its
shape. Git snapshot equality is separate: recovery's `source_status=unchanged` does not certify a correctly projected identity.
If an old report has a noncanonical identity, revoke that exact identity claim, retain independently verified bytes/native
association/facts, and use the formal output in a new result without rewriting the old artifact.
The formal interactive entry starts and completes in the current bound Git project task. Local and an already selected worktree are both eligible for
interactive read-only inspection. Use the absolute dispatcher with an available Python 3 interpreter and `-B`; pass
`inspect-context --project-root <bound-project-root>` explicitly. Do not create a new task or worktree for interactive review.
The current task owns `manual_30d` evidence, the immutable artifact, recovery and the final result. Scheduled still uses its
isolated worktree and independent activation policy.

Review status is `ok`, `degraded`, `no_material_delta`, `failed`, or `output_budget_exceeded`; inspect uses `view_ready` or `degraded`. Review coverage exact fields are:

```text
task_index_limit, index_pages_read, index_terminals, discovered_task_count, window_task_count, selected_task_count,
fully_read_task_count, turn_pages_read, excluded, truncated, status, discovery_methods
```

Coverage is `complete`, `bounded`, or `degraded`. `task_index_limit=50` is the per-page maximum, never the total cap.
`index_pages_read` counts completed native history pages. `index_terminals` has exactly `active, archived`, each one of
`window_boundary, eof, has_more, unavailable, failed`. Both partitions must reach a proved boundary/EOF for complete coverage;
record the current host/source/frozen window in evidence, and deduplicate native task identities. Failed or unsupported history
must be degraded and cannot be relabeled complete or a host-cap result. Every yielded execution cell is resumed to a terminal result; abandoned execution is a protocol failure.
`discovery_methods` contains only terminal enums:

```text
native_index_completed, native_index_host_cap, native_index_terminal_failure,
native_thread_pages_completed, native_thread_pages_terminal_failure,
execution_protocol_failed
```

Complete requires `native_index_completed + native_thread_pages_completed`, both history partitions completed, all selected tasks read, and no truncation. Bounded
requires `native_index_host_cap + native_thread_pages_completed`, an unfinished history partition, and all selected tasks read. Degraded requires
an explicit `native_index_terminal_failure` or one proved index terminal result plus
`native_thread_pages_terminal_failure`; the latter requires truncation and fewer fully read than selected tasks. In either degraded
case, cards independently supported by formal project evidence remain. The compatibility enum
`native_thread_pages_terminal_failure` records an observed boundary of incomplete selected-task reading: a native page error,
or a successful page whose truncated fields cannot be recovered within the native interface. It does not assert that a
successful native call threw an error. Record the actual cause and exact unread scope in the existing Session source
`coverage/uncovered` and `limitations`; do not count that task as fully read.
Retain a rejected call or local transfer/parse error. If the same native source and cursor can be recovered within the original
authorization and retry limits, correct it and continue; unfinished work alone is not a failure. An unrecovered execution cell,
lost source provenance or unrecovered execution interruption is `execution_protocol_failed`, which requires Project status
`failed`; it may preserve one previously proved index terminal result, but never thread-pages completed and never cards.
`no_material_delta` requires complete/bounded coverage and evidenced dispositions within the declared covered scope.

Each rule-candidate Project Card has exact fields (engineering fields are defined above):

```text
card_id, project_claim_hash, human_context, classification, evidence_level,
project_support, normalized_evidence_hash, owner_recommendation, pain,
event_timeline, direct_evidence, counterevidence, causal_chain, abstraction,
owner_rationale, anti_examples, privacy_check, unproven, rule_payload
```

`project_support` exact fields are `count`, `project_refs`, `basis`, and `coverage_note`. Count equals unique refs and is at least
one. E2 normally has one project; E3 requires at least two independently evidenced project refs. It never implies a fixed total.
Classifications are `already_covered`, `add`, `replace`, `consolidate`, `route_to_owner`; owner recommendations are
`project_owner`, `skill`, `global_agents`, `no_persistence`.
Cross-project reuse is not sufficient for `global_agents`: compare the necessary cross-task decision with the complete current
Owner and keep task-specific procedures in their actual method entry. Method routing preserves the source action and exception,
names the applicable task and inputs, and distinguishes a tested entry from a draft or missing capability. Capacity never proves
semantic coverage or authorizes relocating a mandatory behavior.

`human_context` exact fields:

```text
display_locale, decision_title, project_story, user_cost, recommended_outcome,
concrete_before, concrete_after, strongest_counterpoint, evidence_refs
```

The title is at most 60 characters. Story is one to three short paragraphs. All narrative fields are concrete Simplified Chinese;
evidence refs must resolve to direct evidence. Privacy-safe domain terms stay; paths, commands, IDs, secrets, and raw dialogue do
not. `rule_payload` is exactly `trigger, action, skip_boundary, scope, why, evidence, instruction_target`.

## Review Pack

`global_owner_scout_review_pack_v8` exact top-level fields (Project result v7; Pack v7/v6 pair with Project v6/v5):

```text
contract_version, mode, status, display_locale, skill_version, project_result,
owner_parity, review_cards, selection_preview, limitations, review_pack_hash
```

Owner parity fields are `status, canonical_source_ref, canonical_source_hash, local_target_ref, local_target_hash, snapshot_id`.
Logical refs are exactly `canonical_global_agents` and `host_local_global_agents`; status is `matched`, `drift`, or `unavailable`.
Their physical endpoints come only from the read-only `resolve_owner_parity.py` helper: canonical source from Core
`global_instruction_binding`, local target from the active Codex home. Missing binding, Store, or files is `unavailable`; project
root `AGENTS.md`, repository search, prompt paths, and guessed paths are forbidden fallbacks. The helper emits no physical path.
For matched parity, the Scout reads the active local target and verifies its bytes against the returned hash; equal hashes prove the
canonical bytes are identical. Drift/unavailable makes Owner comparison incomplete and removes confirmation.

Every review card corresponds one-to-one and in order with a Project Card and contains:

```text
project_claim_hash, selection_token, recommended_action, recommended_action_reason,
integration_preview, expected_behavior_change, allowed_actions
```

Integration fields are `global_relation, research, owner_comparison, before_after, globalization_risk, repeat_status, supersedes`.
Actual integration relation owns the recommendation: exact existing coverage is ignore, a challenged or unclear global projection
is edit, and a supported project/Skill route keeps that scope. The frozen project's initial classification cannot override it.
`add` has no superseded rules, `replace` exactly one, and `consolidate` at least two. Compare overlapping candidate obligations
before preview, preserving their distinct triggers and exceptions; a shared topic alone is not a reason to merge.
If Owner comparison or candidate merging changes a projection, return to deep-review Phases 5–6 and produce a new content-bound
Project/Review revision. Keep every source obligation's disposition and the original frozen artifacts; do not edit frozen cards
in place or repeat an unchanged source census.

Run `python -B scripts/scout.py prepare-review` with the draft Review Pack on stdin. This reads the active installed Core artifact
identity from the existing registry without writes, verifies the artifact bytes, and calls its read-only `preview-bundle` entry.
With no selection flags, preview the full proposed set. To preview a deliberate subset, repeat
`--select-card <card-id>` for its exact members; retain all Project/Review Cards and all single-item projections. The Core receipt's
`bundle_sha256` binds the full proposed catalog, while `combined.card_ids` binds the exact selected subset and its after hash.
It preserves Project Cards and semantic integration, populating only action qualification, tokens and `selection_preview` before
hashing the final pack. Drafts may set `selection_preview=null`; they cannot be rendered as confirmable final packs.
The selection preview is null when no global mutation is proposed; otherwise it has exactly
`core_artifact_sha256, result, error_code`. `result` is the exact `rule_bundle_preview_v2` receipt or null with an error;
legacy v1 receipts remain readable. V2 preserves the top-level fields and adds `capacity` to every item and combined projection.
It contains `rules` (`rule_id, actual_bytes, budget_bytes, exceeded`) and `managed_block`
(`before_bytes, projected_bytes, budget_bytes, exceeded`), or is null for a structural/target failure. Rules count normalized
UTF-8 LF bytes; the block counts its physical target newlines. Ready requires both budgets to pass; a capacity failure must retain
both measurements even when both exceed budget. Validators reject missing or inconsistent measurements and false ready states.
Ship a v2-producing Core with a Scout that accepts v2; do not treat an old v1 receipt as proof of detailed per-rule measurements.
Every individual confirmation requires its ready item. A combined confirmation requires the ready combined projection;
individual success never manufactures a combined success. A card used only in a valid combination exposes its bound combination
identity without offering an invalid standalone confirmation. Unavailable Core or stale Owner never qualifies confirmation.
All supported cards remain visible when combination/capacity is blocked; explain that the set needs revision and retain edit,
project/Skill routing and ignore. Other user-selected combinations are previewed before final approval, without rerunning project
discovery or silently truncating candidates. Deployment still validates the exact current approval and replans under locks.
Routing is a recommendation until authorized formal Owner content and any mandatory `AGENTS.md` reading trigger are read back.
Preserve each obligation, condition and exception at its correct authority; optional memory saves never substitute for deployment.
For a confirmable card, `selection_token` is the 32-hex operation identity derived from card ID, project claim, proposal,
sorted `supersedes`, instruction target, and the current canonical source hash. It is `null` otherwise. Covered/no-persistence cards recommend `ignore` as a no-op disposition, with `allowed_actions=[]`
and no required user choice. They remain complete reference material; the renderer counts only nonempty action sets as decisions.
Other cards retain `edit` and `ignore`. `confirm` exists only for matched-parity, `global_agents`, `add/replace/consolidate` cards. Project
Owner and Skill routes recommend `keep_project` and `make_skill`. Drift removes confirmation but never a card.

Renderer order: warnings; surface-specific decision index; each card's decision summary with its exact Rule Projection; evidence;
technical appendix; validation receipt; and only for Scheduled, one final Inbox wrapper. Invoke `python -B scripts/scout.py
render-review --surface interactive|scheduled` from the Skill root with the validated Pack on stdin. Interactive uses `本次需要判断`,
has zero wrapper, and rejects the Scheduled decision heading and Inbox wrapper. Factual prose may discuss other modes and
their unverified scope; those words alone are not an invalid interactive structure. Scheduled uses `今日需要判断` and exactly one wrapper. The receipt
records surface, `review_pack_hash`, `visible_body_sha256`, Project Card count, visible card count, a per-card action-count vector,
total visible action count, atomic bundle action count, and wrapper count. `python -B scripts/scout.py verify-visible --surface ...` rejects body drift,
lost or cross-card-moved actions, duplicate or
non-final wrappers, raw contract JSON outside the single canonical recovery block, trailing notes, and truncation. The verifier proves renderer/artifact bytes only; it does not prove the
actual task final. Renderer failure may not be repaired by hand-written Markdown. `output_budget_exceeded` is a whole-run failure.
Within a card, show the exact When/Do/Skip body once and reference that named field when another field repeats it exactly.
Keep distinct qualifications, evidence and before/after facts; semantic similarity does not authorize compression.

## Interactive Delivery

`global_owner_scout_delivery_v2` has these exact fields (legacy v1 omits visual_name/visual_sha256/visual_bytes):

```text
contract_version, status, delivery_surface, artifact_name, artifact_sha256,
artifact_bytes, review_pack_hash, visible_body_sha256, project_cards,
visible_cards, visible_action_counts, visible_actions, bundle_action_count,
wrapper_count, delivery_manifest_sha256, visual_name, visual_sha256, visual_bytes
```

Status is exactly `prepared`; surface is exactly `task_artifact`; wrapper count is zero. The artifact name is
`global-owner-scout-review-pack-<first 16 hex of review_pack_hash>.md`. The manifest hash is canonical UTF-8 sorted compact JSON
excluding its own hash field. The manifest contains no absolute path, task ID, Review Pack body, Owner body, evidence body, approval,
or persistence state. `prepared` proves deterministic creation and same-file readback only; it is not `surface_observed`.

Run `python -B scripts/scout.py prepare-delivery --artifact-dir <host-output-root> --protected-root <project-root>` with the validated Review Pack on stdin.
The output root must be an explicit current-task host-generated workspace, exist already, be a normal directory, and be outside every
protected project root. The helper creates a single-link regular Markdown file exclusively; an existing identical file is idempotent,
while any different bytes, link/reparse point, unsafe root, write failure, or readback mismatch fails closed. It does not write a
manifest file.

Default to `render-receipt not_requested` with the exact artifact/root. Return the artifact-bound overview and first
recommendation plus the evidence link; do not automatically open the report. Only an explicit request uses native preview once.
Queued/failed preview still returns verified advice and the link, without polling, user window switching or approval claims.
`not_requested`, `open_queued` and `open_failed` keep confirmation false; opened with no confirmable bundle also keeps it false.
Card and Core authorization structures remain unchanged; Project/Pack/Delivery evolve as specified above.

`recover-delivery` consumes the original native `prepare-delivery` manifest and granted artifact root. `verify-final` is a
legacy locator adapter for one distinct artifact link and original manifest hash; it tolerates repeated identical locators.
Both use Delivery's single artifact verification chain. Bind a report selection with `--report-hash` (the Review Pack hash),
and resolve object/journey against that verified map. No new manifest, result store or Markdown parser is introduced.
Human summaries, headings, formatting and display/confirmation copy are not machine credentials. Correct inaccurate copy from
original evidence; recovery never certifies chat prose or UI. Distinct unresolved reports require selection, not a newest-file guess.
Recovery always returns `artifact_verified` and `confirmation_eligible=false`, replacing display statuses formerly inferred from
copy. Observe actual native display separately. Historical bundles/maps remain null when absent; do not invent bindings or migrate
old files. Exact global selections still require Fresh Owner/Core and current real-event authorization. Current-source status is
separate from historical artifact integrity; changed sources require affected fact checks before current actions.

Every Python helper invocation uses `python -B`; an attributable helper write to `__pycache__`, `.pyc` or `.pyo` still fails
read-only validation. A cache difference alone proves neither its writer nor execution identity: `-B` can read valid cached
code. Preserve before/after evidence, distinguish external changes from helper writes and recheck the affected execution
source. Unknown attribution is not a mutation finding or an automatic pass; retain the affected stability/identity limit and
independently supported evidence. Never delete caches or replace the old baseline to hide the observation.

## Manifest-free terminal

`global_owner_scout_terminal_v1` has these exact fields:

```text
contract_version, status, phase, reason_code, project_state,
confirmation_eligible
```

`confirmation_eligible` is exactly false. Phase is `preflight`, `session_census`, `project_review`, or `delivery`; project state is
`unchanged`, `changed`, or `unverified`. Status is `interactive_entry_blocked`, `interactive_host_blocked`,
`render_integrity_failed`, `output_budget_exceeded`, or `failed`. Reason is a closed enum implemented by the dispatcher and cannot
contain a path, task ID, evidence body, or free-form diagnostic. Before a valid Delivery manifest exists, pass this object to
`python -B scripts/scout.py render-terminal`. Never call `render-receipt` without a manifest, hand-write replacement Markdown,
display partial cards, or enable confirmation.

Every reason has one exact status and phase; only its listed project states are legal:

| reason_code | status | phase | project_state |
|---|---|---|---|
| `project_binding_unavailable` | `interactive_entry_blocked` | `preflight` | `unverified` |
| `git_worktree_ineligible` | `interactive_entry_blocked` | `preflight` | `unverified` |
| `worktree_projection_unavailable` | `interactive_entry_blocked` | `preflight` | `unchanged` or `unverified` |
| `execution_protocol_failed` | `failed` | `session_census` | `unchanged` or `unverified` |
| `read_only_violation` | `failed` | `project_review` | `changed` |
| `privacy_or_contract_failed` | `failed` | `project_review` | `unchanged` or `unverified` |
| `output_root_unavailable` | `interactive_host_blocked` | `delivery` | `unchanged` or `unverified` |
| `render_integrity_failed` | `render_integrity_failed` | `delivery` | `unchanged` or `unverified` |
| `output_budget_exceeded` | `output_budget_exceeded` | `project_review` | `unchanged` or `unverified` |

`host-open` happens after a valid manifest and therefore uses the manifest-bound blocked/queued/opened receipt path, never
Terminal v1.

## User actions

- `确认 <card_id>@<selection_token>[、<card_id>@<selection_token>...]`: select one or more confirm-eligible cards from the same
  Review Pack and target. The reply must exactly equal the canonical sorted command, or that complete command with every `@`
  escaped once as `\@`; the user may remove whole pairs before confirming. Reread the
  latest canonical/local Owner once, jointly recompute exact relations and aggregate before/after, then execute exactly one
  `rule deploy-bundle` operation. Core recomputes every token and binds the exact current prompt. The selected set is an unordered,
  all-or-nothing transaction; any stale relation, content mismatch, conflict, capacity failure, or write error
  produces zero Owner changes and one refreshed aggregate preview or failure receipt.
- `修改 <card_id>：…`: render a revised card, no write.
- `留在项目 <card_id>` / `改做 Skill <card_id>`: create a separately confirmable owner change.
- `忽略 <card_id>`: persist nothing.

One user message may confirm one or more cards, or perform one non-confirm action. Do not mix confirmation with edit/routing/ignore
actions. A single-card confirmation is a bundle of size one. After a successful bundle, unselected Project Cards remain immutable;
only their Owner integration previews are stale. Rebase them against the latest Owner when later selected—do not rerun project
discovery unless project evidence itself changed. A file change proves only `instruction_deployed/adoption_unproven`; later natural
tasks prove adoption and revocation.

## Entry and Prompt gate

The only formal user invocation is `$global-owner-scout 复盘当前项目` in the current bound target Git project task. It selects
`manual_30d`, uses no automation memory, never asks for resource settings, and never displays Scheduled acceptance counters.
The current task's host-resolved requested and actual settings remain subject to the model-observation contract; no override is supplied. A v5.4 Scheduled Prompt contains
Skill/mode, rolling window, contract versions, model/reasoning, and safety boundaries only. Reject
prompts containing a fixed `project_key`, absolute path, host project ID, project allowlist, expected candidate, or full review
  protocol. The current Desktop task binding supplies project identity and, when available, its distinct host-generated output root.
The current project task completes the read-only review in Local or its existing worktree; no new chat or worktree is required.
Preflight failure returns Terminal v1 before deep reads, never a request for the user to prepare the environment.

## Production activation gate

Enrollment and activation are separate. A Host Activation Control task must create a disposable standalone automation canary and
observe its single `list_threads(limit=50)` call from a separate interactive task. The gate passes only when the real
automation-source task reaches an explicit terminal result within 180 seconds. Still-running state at the budget boundary is
`host_activation_blocked / native_index_non_terminal`; it is not a terminal native error or degraded Session coverage. The
control task re-reads the affected automation as `PAUSED` and deletes the disposable automation. Ordinary tasks and fixtures do
not satisfy this gate. The Scout never changes its own automation state.
