# Global Owner Scout 5.6 contracts

## Common rules

- Skill `5.6.0`; Project result `global_owner_scout_project_v4`; Review Pack
  `global_owner_scout_review_pack_v4`; Delivery `global_owner_scout_delivery_v1`; user locale `zh-CN`.
- Canonical hashes use UTF-8 JSON with sorted keys and compact separators, excluding their own hash field.
- `project_claim_hash` covers every Project Card field except itself. `review_pack_hash` covers the pack except itself.
- Evidence references may identify owner sections, ADRs, tests, commits, or event classes. They may not contain absolute paths,
  raw dialogue, complete commands, accounts, tokens, raw remotes, project IDs, automation IDs, or diagnostic bodies.
- E1 remains an observation. Every E2/E3 card is shown; no fixed project denominator, count cap, ranking, or silent truncation.
- Human Context is Simplified Chinese and project-specific; Rule Projection is abstract and Owner-ready.

## Project result

`global_owner_scout_project_v4` has these exact top-level fields:

```text
contract_version, mode, status, display_locale, project_key, project_identity,
run_id, task_id, skill_version, evidence_window, model_observation, owner_snapshot,
session_coverage, evidence_sources, events, observations, project_cards,
read_only_proof, limitations
```

`project_identity` exact fields:

```text
identity_kind, content_identity_hash, host_project_ref_hash,
git_worktree_eligible, binding_status
```

Identity kind is `content` or `host_local`; binding is `bound`, `rebound`, or `ambiguous`. Raw local project IDs, paths, and remotes
are forbidden. A Scheduled v5 run requires `content`, worktree eligibility, and non-ambiguous binding. The formal interactive entry
also runs in an independent Git worktree and uses `manual_30d`.

Status is `ok`, `degraded`, `no_material_delta`, `failed`, or `output_budget_exceeded`. Coverage exact fields are:

```text
task_index_limit, discovered_task_count, window_task_count, selected_task_count,
fully_read_task_count, turn_pages_read, excluded, truncated, status, discovery_methods
```

Coverage is `complete`, `bounded`, or `degraded`. The first and only native index request uses limit 50. A yielded execution cell
must be resumed on the same cell for up to two 60-second waits before classification; an unresumed cell is a failed execution
protocol, not degraded coverage. `discovery_methods` contains only terminal enums:

```text
native_index_completed, native_index_host_cap, native_index_terminal_failure,
native_thread_pages_completed, execution_protocol_failed
```

Complete requires `native_index_completed + native_thread_pages_completed`, all selected tasks read, and no truncation. Bounded
requires `native_index_host_cap + native_thread_pages_completed`, a proved host cap, and all selected tasks read. Degraded requires
an explicit `native_index_terminal_failure`. `execution_protocol_failed` requires Project status `failed` and cannot coexist with
an index terminal result. `no_material_delta` requires complete/bounded coverage and candidate exhaustion.

Each Project Card has exact fields:

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

`human_context` exact fields:

```text
display_locale, decision_title, project_story, user_cost, recommended_outcome,
concrete_before, concrete_after, strongest_counterpoint, evidence_refs
```

The title is at most 60 characters. Story is one to three short paragraphs. All narrative fields are concrete Simplified Chinese;
evidence refs must resolve to direct evidence. Privacy-safe domain terms stay; paths, commands, IDs, secrets, and raw dialogue do
not. `rule_payload` is exactly `trigger, action, skip_boundary, scope, why, evidence, instruction_target`.

## Review Pack

`global_owner_scout_review_pack_v4` exact top-level fields:

```text
contract_version, mode, status, display_locale, skill_version, project_result,
owner_parity, review_cards, limitations, review_pack_hash
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
For a confirmable card, `selection_token` is the 32-hex operation identity derived from card ID, project claim, proposal,
sorted `supersedes`, instruction target, and the current canonical source hash. It is `null` otherwise. `edit` and
`ignore` are always available. `confirm` exists only for matched-parity, `global_agents`, `add/replace/consolidate` cards. Project
Owner and Skill routes recommend `keep_project` and `make_skill`. Drift removes confirmation but never a card.

Renderer order: warnings; surface-specific decision index; every card's 30-second view; complete evidence and Rule Projection;
technical appendix; validation receipt; and only for Scheduled, one final Inbox wrapper. Invoke `render_review.py --surface
interactive|scheduled` directly from the scripts directory with the validated Pack on stdin. Interactive uses `本次需要判断`,
has zero wrapper, and contains no Scheduled/Inbox/14-run copy. Scheduled uses `今日需要判断` and exactly one wrapper. The receipt
records surface, `review_pack_hash`, `visible_body_sha256`, Project Card count, visible card count, a per-card action-count vector,
total visible action count, atomic bundle action count, and wrapper count. `verify_visible_output.py --surface ...` rejects body drift,
lost or cross-card-moved actions, duplicate or
non-final wrappers, raw JSON, trailing notes, and truncation. The verifier proves renderer/artifact bytes only; it does not prove the
actual task final. Renderer failure may not be repaired by hand-written Markdown. `output_budget_exceeded` is a whole-run failure.

## Interactive Delivery

`global_owner_scout_delivery_v1` has these exact fields:

```text
contract_version, status, delivery_surface, artifact_name, artifact_sha256,
artifact_bytes, review_pack_hash, visible_body_sha256, project_cards,
visible_cards, visible_action_counts, visible_actions, bundle_action_count,
wrapper_count, delivery_manifest_sha256
```

Status is exactly `prepared`; surface is exactly `task_artifact`; wrapper count is zero. The artifact name is
`global-owner-scout-review-pack-<first 16 hex of review_pack_hash>.md`. The manifest hash is canonical UTF-8 sorted compact JSON
excluding its own hash field. The manifest contains no absolute path, task ID, Review Pack body, Owner body, evidence body, approval,
or persistence state. `prepared` proves deterministic creation and same-file readback only; it is not `surface_observed`.

Run `prepare_delivery.py --artifact-dir <host-output-root> --protected-root <project-root>` with the validated Review Pack on stdin.
The output root must be an explicit current-task host-generated workspace, exist already, be a normal directory, and be outside every
protected project root. The helper creates a single-link regular Markdown file exclusively; an existing identical file is idempotent,
while any different bytes, link/reparse point, unsafe root, write failure, or readback mismatch fails closed. It does not write a
manifest file.

Pre-render compact success, queued and blocked receipts from the manifest; success and queued rendering must receive both the exact
artifact path and artifact root and must recheck direct-child containment, read-only state, bytes, hashes and visible-output
conservation. Then make the current-task host artifact open the final tool call. Return the exact success receipt only for an explicit
terminal opened/success result. An exact `queued` host result returns the content-bound queued receipt with the artifact link and
confirmation disabled; its controller result is `surface_pending`, never Production qualification. `pending`, missing, failed, or
unobservable results use the path-free blocked receipt with confirmation disabled. A
separate controller reads the actual task final and runs `prepare_delivery.py --verify-final --artifact-root <host-output-root>`.
Both `surface_pending` and `surface_observed` prove that the final receipt, artifact path, manifest hash, file bytes, Review Pack/body
hashes, cards and actions conserve; only `surface_observed` proves the user surface and qualifies the host. Until three independent
worktree canaries pass, the
interactive product state is `production_unproven / interactive_host_blocked`.
The controller normalizes line endings and may remove exactly one host-added terminal blank line; every other trailing or semantic
edit fails closed.
The controller also binds the canary's actual installed Skill identity before execution. Repository-local source presence is not
runtime adoption. A task that resolves another Scout version or returns the legacy inline renderer envelope is ineligible rather
than failed/passed, and cannot contribute to Production qualification.

Every Python helper invocation uses `python -B`. The installed Skill and its before/after proof contain no newly created or changed
`__pycache__`, `.pyc`, or `.pyo`; any bytecode-cache write is an external side effect and fails read-only validation.

## User actions

- `确认 <card_id>@<selection_token>[、<card_id>@<selection_token>...]`: select one or more confirm-eligible cards from the same
  Review Pack and target. The reply must exactly equal the canonical sorted command; the user may remove whole pairs. Reread the
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

The only formal user invocation is `$global-owner-scout 复盘当前项目`. It selects `manual_30d`, uses no automation memory, inherits
the current task model/reasoning/Speed, and never displays Scheduled acceptance counters. A v5.4 Scheduled Prompt contains
Skill/mode, rolling window, contract versions, model/reasoning, and safety boundaries only. Reject
prompts containing a fixed `project_key`, absolute path, host project ID, project allowlist, expected candidate, or full review
  protocol. The current Desktop task binding supplies project identity and, when available, its distinct host-generated output root.

## Production activation gate

Enrollment and activation are separate. A Host Activation Control task must create a disposable standalone automation canary and
observe its single `list_threads(limit=50)` call from a separate interactive task. The gate passes only when the real
automation-source task reaches an explicit terminal result within 180 seconds. Still-running state at the budget boundary is
`host_activation_blocked / native_index_non_terminal`; it is not a terminal native error or degraded Session coverage. The
control task re-reads the affected automation as `PAUSED` and deletes the disposable automation. Ordinary tasks and fixtures do
not satisfy this gate. The Scout never changes its own automation state.
