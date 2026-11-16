# Global Owner Scout contracts

## Current project-map contracts

- **Orientation & schemas**: `python -B scripts/scout.py preflight-summary --host codex|pi|claude --purpose review|inspect` returns `global_owner_scout_preflight_summary_v1` with contract versions and command order without reading files or Git. Use `describe-input project|review` (Codex v7/v8) or `native-project|native-review` (Pi/Claude v8/v9) before authoring JSON; `python -B scripts/validate_output.py --hash-project-card` / `--hash-review-pack` compute derived hashes from stdin without validating or synthesizing fields.
- **Native capture & import**: `capture-native` freezes one complete returned JSON object (including index/error/truncation fields) as private immutable raw bytes (`raw_file/sha256`); it grants no source, identity, call-success, or coverage qualification. `import-history` consumes one actual `read_thread` response (or `raw_file` when eligible) plus independently resolved project/session identity and seals a content-addressed export + index (`global_owner_scout_history_page_v1`), preserving cursors and truncation without claiming comprehension or full chat coverage. Both pin output directory identity (Windows denies ancestor write/delete sharing; POSIX uses directory descriptors) so concurrent redirection cannot write into protected projects. Missing containment blocks without fallback.
- **Versions**: Active results use Project v7 (`global_owner_scout_project_v7`), Review Pack v8 (`global_owner_scout_review_pack_v8`), and Delivery v2 (`global_owner_scout_delivery_v2`). Historical Project v5/v6 and Review Pack v6/v7 stay readable without regeneration.
- **Edges & claims**: v7 edges add `kind` (`contains`, `depends_on`, `constrains`, `implements`, `handoff`, `evolves`). Containment is acyclic (multi-parent shared ownership allowed); `depends_on` points dependent -> prerequisite; `constrains` points constraint -> limited target. Structural validation proves reference resolution and connected directed journeys, not semantic truth or intervention attribution (checked by Phase 5).
- **Engineering vs. rule cards**:
  - `kind=engineering`: `kind, parent_card_id, card_id, human_context, evidence_level, normalized_evidence_hash, owner_recommendation, direct_evidence, owner_rationale, anti_examples, privacy_check, unproven, benefit_hypothesis, implementation_cost, validation_conditions, alternatives, project_claim_hash` (each alternative has `approach, tradeoff`; E1/E2/E3 allowed; parent links acyclic, unbounded). Routes only to `project_owner` or `skill`; Review Card uses `recommended_action=discuss`, `allowed_actions=[]`, `integration_preview=null`, `selection_token=null`; `owner_parity=null` allowed when zero rule candidates exist.
  - Rule candidates keep full Project Card fields below and route through Owner parity + Core preview.
- **`project_map` fields**:
  - Top: `title, goal, boundary, observed_at, source_revision, nodes, edges, journeys, coverage`.
  - Node: `id, label, kind, summary, owner, evidence_refs, claims, card_ids`.
  - Edge (v7): `id, source, target, kind, label, evidence_refs, claims, card_ids` (v6 omits `kind`).
  - Claim: `layer, environment, statement, evidence_refs` (`layer`: `design|implementation|observed|inference|unknown`).
  - Journey: `id, label, entry, edge_ids, outcome, recovery, evidence_refs, card_ids`.
  - Coverage: `dimension, status, explanation, evidence_refs` (`status`: `covered|partial|unknown|not_applicable`).
  - All IDs are unique per kind; edges resolve nodes; journeys form connected directed paths; evidence refs resolve declared sources; card IDs resolve actual Project Cards; unknown claims stay explicit.
- **Selection recovery (`selected_context`)**: Resolving a node, edge, or advice recovers all containing journeys (including containment ancestors) without silently picking one; an explicit `--journey` keeps that path plus containment ancestry and recursive prerequisites/constraints (never unrelated downstream branches; v6 omits typed prerequisites). Carries `purpose, project_key, project_identity, context_snapshot_hash, goal, boundary, observed_at, source_revision, coverage` and optional `project_contract`. Coverage remains project-wide. `verify-final` adds `source_status` and optional `source_reason` (`not_checked`, `changed`, `unavailable` never grant currentness or mutation authority).
- **Inspect vs. Review**: `inspect` uses `status=view_ready|degraded`, `evidence_window.kind=current`, `session_coverage=null`, empty events/observations/cards, `owner_parity=null`, `selection_preview=null`, and skips Owner resolution and Core preview. `review` retains full census, dispositions, Owner parity, and Core preview.
- **Delivery v2 & visuals**: `global_owner_scout_delivery_v2` binds `visual_name, visual_sha256, visual_bytes`. `assets/project-map.html` is optional; custom compositions use `prepare-delivery --visual-input`. Presentation never becomes a state store: missing/tampered HTML reports separately without invalidating verified Markdown or granting approval.

## Native session source snapshots

`import-history` also accepts Pi and Claude source snapshots (native source proof only — never promotes to complete history or desktop binding):

- **Pi (`global_owner_scout_native_session_v1`)**:
  ```text
  contract_version = global_owner_scout_native_session_v1
  native_host = pi
  session = unmodified SessionManager.getHeader() (format 3)
  entries = unmodified SessionManager.getEntries()
  ```
  Exported read-only by `scripts/native_session_export.mjs`; emits `global_owner_scout_history_page_v2` index (`native_host, entry_ids, record_count`).
- **Claude (`global_owner_scout_native_page_v1`)**:
  ```text
  contract_version = global_owner_scout_native_page_v1
  native_host = claude
  session = unmodified getSessionInfo(session_id, {dir})
  messages = unmodified getSessionMessages(session_id, options)
  page_request = {offset, limit, includeSystemMessages: true}
  ```
  Called by `exportClaudeSessionPage(sdk, {project_root, session_id, offset, limit})` after validating absolute root, nonempty `session_id`, nonnegative `offset`, positive `limit`. Emits v2 index (`message_ids, record_count, page_request`) without inventing cursors/EOF.

## Common rules

### Native-session hosts (candidate)

- Pi and Claude use `global_owner_scout_project_v8` + `global_owner_scout_review_pack_v9`.
- `session_coverage` exact keys: `native_host` (`pi|claude`), `scopes` (`kind`: `project_sessions|session_messages`, `coverage`: `observed_only|unknown|failed`, `record_count, evidence_refs`), `discovered_task_count, selected_task_count, fully_read_task_count, status, discovery_methods`.
- Always `coverage=degraded`, `status=degraded`, `fully_read_task_count=0`, `discovery_methods=native_scoped_sources_observed`; never fabricate Codex partitions (`active/archived`). Supports engineering advice only (`allowed_actions=[]`, no Codex-bound rule confirmation).
- **Pre-history `inspect-native`**: Wrap live ExtensionContext (Pi), live `system/init` (Claude programmatic), or live `source_kind=claude_skill_substitution` (`cwd, project_dir, session_id, skill_dir, plugin_root`) inside `global_owner_scout_native_context_v1`. Never `cd` to mask startup vs. current Git tree drift (`binding_scope=native_skill_substitution_git`). Returns `global_owner_scout_native_binding_v1`.
- **Host adapters**:
  - Pi registers `global_owner_scout_context` + shared Scout Skill; `capture_current` validates `artifact_dir`, resolves Python 3.11+ outside the workspace (`-E -s -B`), and calls the immutable importer.
  - Claude marketplace exposes shared Scout + two sibling methods via `/agent-memory-sidecar:global-owner-scout`. `claude_native.mjs context|capture` keeps caller session separate from `--source-session-id` and requires pre-deployed pinned SDK `0.3.322` (`prepare_claude_runtime.mjs`, `npm ci --ignore-scripts --omit=optional`). `--help` works read-only without Python/SDK.
  - `observePiTurn(before, events, after)` and `observeClaudeTurn(init, events)` emit `global_owner_scout_native_turn_v1` (observation only; an active-turn snapshot stays usable without waiting for chat termination).
- **Output grants & binding**: Output roots come only from current host task metadata or explicit current-turn user selection (`inspect-output` verifies physical containment, not consent). Native binding uses same-host inventory (`projectId` or unique native `cwd` / worktree origin match); shell cwd/labels/prompt paths never bind.

### Versions, hashing & privacy

- Skill `5.19.9`; Project result `global_owner_scout_project_v7`; Review Pack `global_owner_scout_review_pack_v8`; Delivery `global_owner_scout_delivery_v2`; manifest-free terminal `global_owner_scout_terminal_v1`; user locale `zh-CN`.
- Canonical hashes use UTF-8 JSON with sorted keys and compact separators excluding their own hash field (`project_claim_hash`, `review_pack_hash`).
- Evidence refs allow owner sections, ADRs, tests, commits, or event classes; forbid absolute paths, raw dialogue, full commands, accounts, tokens, raw remotes, project IDs, automation IDs, or diagnostic bodies.
- E1 supports clearly labelled engineering hypotheses only (never rule candidates). Show every E2/E3 card (no cap/truncation); order actionable advice by evidenced impact and dependencies before freezing.
- Human Context uses concrete Simplified Chinese; Rule Projection is abstract and Owner-ready.
- `global_owner_scout_preflight_v1` exact fields (zero paths): `contract_version, git_repository, execution_context, head, status_sha256, staged_diff_sha256, unstaged_diff_sha256, untracked_files_sha256, context_snapshot_sha256`. Run `python -B scripts/scout.py inspect-context --project-root <bound-project-root>` before deep reads.

## Project result

### Discovery trace

- `evidence_sources`: all six categories (`sessions, owners, decisions, successes, failures, acceptance`), `status` (`available|degraded|unavailable|not_applicable`), `coverage`, `refs` (`{type, ref, summary}`), `uncovered`. Owners cannot be `not_applicable`; active knowledge ignores the 30-day Session window.
- Events & Observations: every event resolves declared sources and maps to an observation (`observation_id, evidence_level, summary, direct_evidence, event_ids, disposition`). Disposition has `kind` (`candidate|already_covered|project_only|skill_only|insufficient_evidence|not_reusable`), `reason, card_ids, owner_refs, local_scope, portable_delta`. Every card links once (`normalized_evidence_hash` = SHA-256 of `direct_evidence`). Identical `{type, ref, summary}` must match across occurrences; human-context refs must be a subset of card evidence refs.
- Degraded Sessions require at least one non-Session formal source per retained card. `no_material_delta` requires nonempty observations, zero cards, and `complete|bounded` Session coverage. Validation checks trace consistency, not semantic recall (tested separately by blind rubric evaluation).

### `global_owner_scout_project_v7`

Top-level exact fields (v6 shares fields; v5 omits `purpose, project_map`):

```text
contract_version, mode, status, display_locale, project_key, project_identity,
run_id, task_id, skill_version, evidence_window, model_observation, owner_snapshot,
session_coverage, evidence_sources, events, observations, project_cards,
read_only_proof, limitations, purpose, project_map
```

- `project_identity`: `identity_kind` (`content|host_local`), `content_identity_hash, host_project_ref_hash, git_worktree_eligible, binding_status` (`bound|rebound|ambiguous`). Scheduled requires `content`, worktree eligibility, and non-ambiguous binding. Derived via Bootstrap `enrollment.py inspect-project` (`project_content_identity_v1`), never raw-remote hashing.
- `session_coverage`:
  ```text
  task_index_limit, index_pages_read, index_terminals, discovered_task_count, window_task_count, selected_task_count,
  fully_read_task_count, turn_pages_read, excluded, truncated, status, discovery_methods
  ```
  - `task_index_limit=50` is per-page, never a total cap. `index_terminals` has `active, archived` (`window_boundary|eof|has_more|unavailable|failed`).
  - `discovery_methods` enum: `native_index_completed, native_index_host_cap, native_index_terminal_failure, native_thread_pages_completed, native_thread_pages_terminal_failure, execution_protocol_failed`.
  - `complete` requires both partitions at boundary/EOF, all selected tasks read, and no truncation. `bounded` means unfinished partition + all selected tasks read. `degraded` means explicit index/page failure or unrecoverable field clipping (do not relabel as complete or claim clipped return threw an exception). Unrecovered cells or lost provenance require `status=failed` + `execution_protocol_failed` with zero cards.
- Rule-candidate Project Card exact fields:
  ```text
  card_id, project_claim_hash, human_context, classification, evidence_level,
  project_support, normalized_evidence_hash, owner_recommendation, pain,
  event_timeline, direct_evidence, counterevidence, causal_chain, abstraction,
  owner_rationale, anti_examples, privacy_check, unproven, rule_payload
  ```
  - `project_support`: `count, project_refs, basis, coverage_note` (`count == len(unique(project_refs)) >= 1`; E3 >= 2).
  - `classification`: `already_covered|add|replace|consolidate|route_to_owner`; `owner_recommendation`: `project_owner|skill|global_agents|no_persistence`.
  - `human_context`: `display_locale, decision_title, project_story, user_cost, recommended_outcome, concrete_before, concrete_after, strongest_counterpoint, evidence_refs` (`decision_title <= 60` chars, Simplified Chinese).
  - `rule_payload`: `trigger, action, skip_boundary, scope, why, evidence, instruction_target`.

## Review Pack

`global_owner_scout_review_pack_v8` exact top-level fields:

```text
contract_version, mode, status, display_locale, skill_version, project_result,
owner_parity, review_cards, selection_preview, limitations, review_pack_hash
```

- `owner_parity`: `status` (`matched|drift|unavailable`), `canonical_source_ref` (`canonical_global_agents`), `canonical_source_hash`, `local_target_ref` (`host_local_global_agents`), `local_target_hash, snapshot_id`. Populated solely via `resolve_owner_parity.py` (never exposes physical paths or falls back to project `AGENTS.md`). Confirmations require `matched` parity with verified host-local bytes.
- Review Card exact fields (1-to-1 ordered with Project Cards):
  ```text
  project_claim_hash, selection_token, recommended_action, recommended_action_reason,
  integration_preview, expected_behavior_change, allowed_actions
  ```
  - Integration fields: `global_relation, research, owner_comparison, before_after, globalization_risk, repeat_status, supersedes`.
  - Actual integration relation drives `recommended_action` (`already_covered_exact` -> `ignore`; challenged -> `edit`; `route_supported` -> `keep_project`/`make_skill`). Revising merged obligations or projections returns to Phases 5–6 for a new revision without overwriting frozen artifacts.
- **Core preview (`prepare-review`)**: Pass draft Pack on stdin (optional repeated `--select-card <id>`). Reads installed Core artifact without writes and binds `selection_preview` (`core_artifact_sha256, result` = `rule_bundle_preview_v2` with per-rule + `managed_block` capacity, `error_code`) or `null` when no global mutation is proposed. Covered/no-persistence cards use `recommended_action=ignore`, `allowed_actions=[]`, `selection_token=null`. `confirm` exists only for matched-parity `global_agents` `add/replace/consolidate` cards with ready Core preview.
- **Deterministic render & verify**: `render-review --surface interactive|scheduled` emits warnings, decision index (nonempty action sets only), cards (single verbatim `When/Do/Skip` body referenced thereafter), evidence, technical appendix, and validation receipt (plus 1 trailing Inbox wrapper for `scheduled`, 0 wrappers and never `今日需要判断` for `interactive`). `verify-visible --surface ...` checks body hash, card/action conservation, wrapper count, single recovery JSON block only, and zero trailing notes. `output_budget_exceeded` fails the whole run.

## Interactive Delivery

`global_owner_scout_delivery_v2` exact fields (v1 omits `visual_*`):

```text
contract_version, status, delivery_surface, artifact_name, artifact_sha256,
artifact_bytes, review_pack_hash, visible_body_sha256, project_cards,
visible_cards, visible_action_counts, visible_actions, bundle_action_count,
wrapper_count, delivery_manifest_sha256, visual_name, visual_sha256, visual_bytes
```

- `status=prepared`, `delivery_surface=task_artifact`, `wrapper_count=0`, `artifact_name=global-owner-scout-review-pack-<16hex>.md`, single-link read-only file in explicit project-external task output root (never writes a manifest file; idempotent on identical bytes, fail-closed on mismatch).
- Default `render-receipt not_requested`; open once only if user explicitly asks. Queued/failed opens preserve verified advice and links without polling or enabling confirmation (`confirmation_eligible=false`).
- **Recovery (`recover-delivery` & legacy `verify-final`)**: Consumes original manifest + artifact root (and `--report-hash` / `--object <kind:id> [--journey <id>]` / `--project-root`). Both return `artifact_verified` and `confirmation_eligible=false`. Missing/tampered HTML sets `visual_status=unavailable` while verified Markdown remains usable. Changed sources keep historical findings while requiring affected source diff checks before current actions.
- Always run helpers with `python -B`; attributable `__pycache__` writes fail read-only validation, while `-B` cache attribution limits are reported explicitly without deleting caches.

## Manifest-free terminal

`global_owner_scout_terminal_v1` exact fields (`confirmation_eligible` is always `false`):

```text
contract_version, status, phase, reason_code, project_state, confirmation_eligible
```

Render exclusively via `python -B scripts/scout.py render-terminal` for any pre-manifest failure (never pass partial/invalid manifests to `render-receipt` or hand-write Markdown):

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
| `output_preflight_unavailable` | `interactive_host_blocked` | `preflight` | `unchanged` or `unverified` |

`host-open` occurs after a valid manifest and uses `render-receipt`, never Terminal v1.

## User actions

- `确认 <card_id>@<selection_token>[、<card_id>@<selection_token>...]`: same Review Pack and target, exact sorted canonical string (or every `@` escaped once as `\@`). Agent rereads latest Owner, jointly recomputes relations + aggregate before/after, and executes one atomic `rule deploy-bundle`. Any stale/mismatch/conflict/capacity failure yields zero Owner changes. Single-card confirmation is a bundle of size one. After bundle confirmation, unselected Project Cards stay immutable (only integration previews rebase later without re-running discovery unless project evidence changed).
- `修改 <card_id>：…`: renders a revised card without writing.
- `留在项目 <card_id>` / `改做 Skill <card_id>`: creates a separately confirmable owner change.
- `忽略 <card_id>`: persists nothing. Do not mix confirmation with non-confirm actions in one reply.

## Entry and Prompt gate

- Formal interactive entry: `$global-owner-scout 复盘当前项目` in the bound target Git task (`manual_30d`, zero automation memory, host-resolved resource metadata, no Scheduled counters). Completes read-only in Local or existing worktree; preflight failure emits Terminal v1 before deep reads.
- Scheduled Prompt (v5.4 paused policy): contains Skill/mode, rolling window, contracts, model/reasoning, and safety boundaries only (no fixed `project_key`, path, host ID, allowlist, candidate, or procedure).

## Production activation gate

Host Activation Control must run a disposable standalone `automation-source` canary (`list_threads(limit=50)` observed within 180s from a separate interactive task) before resuming one project canary. Timeout yields `host_activation_blocked / native_index_non_terminal`, re-reads automation as `PAUSED`, and deletes the disposable automation. Scout never alters automation state.
