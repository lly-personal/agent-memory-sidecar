# Agent Memory Core v1

Status: Accepted
Owner: project_docs
Decision owner: user
Accepted at: 2026-07-24
Implements: ADR 0057, ADR 0059, ADR 0070
Supersedes for current implementation: every earlier root contract

## Acceptance criteria

### AC-1 — Single behavior authority

Only a rule parsed from the actual project or global `AGENTS.md` can be
`生效中`. SQLite, Git, Hook, Skill, Memories, tests and Agent statements cannot
create behavior state.

### AC-2 — Exact Core schema

The Store contains exactly:

```text
core_schema
prompt_events
runtime_sessions
proposal_tokens
approval_consumptions
runtime_installation
global_instruction_binding
```

Legacy tables and generic `state` are forbidden. Prompt and proposal bodies are
not persisted.

### AC-3 — Proposal and authorization

The canonical payload contains exactly `trigger`, `action`, `skip_boundary`,
`scope`, `why`, `evidence`, and `instruction_target`. Scope/target pairs are
`project/project_agents` or `global/global_agents`.

The semantic proposal SHA-256 is derived from those seven fields. Every new
proposal token that mutates an instruction target and every approval
consumption binds `rule_revision_v1`: the semantic proposal SHA-256, selected
target, complete pre-mutation document SHA-256 and a unique, sorted list of
superseded rule IDs. A legacy token containing only the semantic proposal hash
may confirm an add-only proposal, but can never acquire superseded IDs.

Expired events, consumed refs, replaced tokens, mismatched payloads, reused
sessions, mismatched primary-folder scope, stale documents and changed
superseded sets fail before file mutation.

Consumption is keyed by the resolved source event, not by the spelling of its
reference. Alternate spellings and previously stored reference hashes cannot
authorize another operation for that event. The check also runs atomically at
consumption, including proposal discard and migrated cutover approvals.
Consumption also atomically rechecks current session/event, scope and expiry;
a prompt replaced after initial validation cannot authorize the operation.
Legacy cutover accepts only canonical refs. An unrecognized legacy consumption
hash has no recoverable event identity: the approving prompt must be strictly
newer than every such record, and migrated sessions whose current prompt is not
strictly newer lose only that authorization pointer. Events and session rows
remain. Invalid consumption timestamps fail closed; canonical consumed events
remain consumed even if their optional legacy result metadata is malformed.

An explicit Review Pack selection binds `rule_revision_bundle_v2`: one or more
unique cards for the same scope/target, each card/project claim, seven-field
proposal, selected superseded set and deterministic selection token, plus the
complete pre-mutation and post-mutation document SHA-256. The current prompt
must exactly equal the canonical confirmation text for the selected set. The
bundle is an unordered set: every permutation produces the same after bytes,
revision hash, receipts or error. It consumes one approval as one operation.
Any invalid, prompt-mismatched, no-op, stale, overlapping, over-capacity or
failed item leaves every target byte unchanged and does not consume approval.

### AC-4 — Instruction repository

Before presenting confirmation, `rule preview-bundle --target-file <observed-owner> --from-json -` consumes the exact
`rule_revision_bundle_v2` through stdin and runs the same bundle planner as deployment without Store, approval, locks, journals or
file writes. The target bytes must match the bundle's before hash. `rule_bundle_preview_v1` contains
`target_before_sha256, bundle_sha256, before_bytes, budget_bytes, items, combined`; each item has
`card_id, status, projected_bytes, target_after_sha256, error_code`, and combined has the corresponding sorted `card_ids`.
Ready results bind the exact after bytes; blocked results retain the planner error, with unavailable projections represented by null.
Individual feasibility never implies combined feasibility. The installed immutable runtime exposes the same read-only
`preview-bundle` command. Actual deployment still rechecks authorization and replans under its existing locks.
Both preview entrypoints accept repeated `--select-card <id>` arguments for a deliberate combined subset. Without them the full
proposed catalog is selected. IDs must be unique known members. `bundle_sha256` binds the complete input catalog, individual
projections preserve every member, and `combined.card_ids` plus its after hash identify the exact selected combination.

Persistent rules contain only derived `rule_id` and `When / Do / Skip`. One
rendered rule is at most 1 KiB and one complete managed block is at most 8 KiB.
The 8 KiB limit is a Sidecar edit budget for the managed block, not a Codex
document limit. Full document bytes are reported but never authorize edits
outside the managed block.

One superseded ID replaces one rule. Multiple unique IDs consolidate rules in
one file transaction: every ID must exist in the selected target, the new rule
occupies the earliest replaced position, and all unaffected rule ordering and
outside bytes remain unchanged.

The repository preserves every byte outside the managed block. Invalid encoding,
duplicate blocks, override shadowing, drift, capacity failure, symbolic links,
Windows reparse points, non-regular files and multi-hardlink targets reject the
whole operation. The check occurs before resolving and again immediately before
replacement. Capacity failure reports current, projected and budget bytes without
consuming approval. There is no TTL, LRU, automatic deletion or background rule
compaction.

Project operations atomically mutate the primary repository `AGENTS.md`. Global
operations lock and atomically mutate the bound complete Git source and local
`~/.codex/AGENTS.md`; a failure before database commit restores both. After
commit, cleanup failure (including lock release) preserves the committed targets and consumed approval;
it reports `instruction_cleanup_required` with `operation_committed=true`,
`approval_consumed=true` and `recovery_required=true`. It must never report that
the operation was not completed or suggest reusing that approval. Existing
authorized mutation recovery retains its before/after and drift checks.
Recovery re-reads the journal, snapshots and commit evidence after acquiring target locks; pre-lock inspection reads target identities only.
After commit or complete rollback, while target locks are still held, atomically rename the journal to the `.cleanup-tx_` namespace
before deleting any snapshot. That namespace contains settled transaction garbage only: retrying its partial deletion never reads or
restores instruction targets. This keeps interrupted cleanup retryable without requiring already-deleted rollback evidence.
If another executor has already removed the complete retired directory or a child within it, cleanup continues idempotently on
every supported Python version. Other deletion errors, including permission failures, still report incomplete cleanup.
The journal root and each transaction directory must have a physical directory chain; recovery, journal creation and retirement
reject symbolic links and Windows reparse points before reading or deleting transaction contents.
A durable committed journal remains commit proof after bounded runtime events
expire. New `instruction_transaction_v2` journals bind `source_event_id`; absent
consumption proves non-commit only while that event is retained. If neither a
commit proof nor the source event survives, return `instruction_recovery_unproven`
and preserve targets and journal. Legacy v1 journals with a committed marker or
retained database commit remain recoverable; other legacy journals require
explicit reconciliation instead of an inferred rollback. Event retention and
the seven-table Store schema do not change.

### AC-5 — CLI and result

The public surface is:

```text
rule list
rule deploy [--supersedes <rule_id>]...
rule deploy-bundle
rule revoke
setup
doctor
```

There are no legacy aliases. Internal experimental proposal operations are
`create`, `replace`, `confirm`, and `discard`; create/replace/confirm bind the
same repeated superseded IDs. `rule list` reports managed bytes, the unchanged
8192-byte budget, remaining bytes, complete document bytes and rule count per
target. JSON output uses
`agent_memory_result_v1`; success/idempotent no-op exits `0`, every failure exits
`1` with an error code. `rule list --target` reads one exact instruction target
so an unrelated target failure cannot block Fresh authorization checks.
Listing never runs transaction recovery or removes journals. It reports actual
target bytes; recovery runs after current approval validation (and exact bundle
confirmation), before mutation planning reads target/binding state. Final apply
still checks recovery and drift; an invalid approval never triggers recovery.

### AC-6 — Runtime

Setup creates a content-addressed immutable zipapp and makes both Hook entries
invoke it. Runtime Python sources are canonicalized to LF before archive hashing,
so checkout newline policy cannot change the artifact for the same source
content. `UserPromptSubmit` writes one bounded event/session update and emits the
fixed capability. `SessionStart(source=compact)` performs a read-only lookup and
retransmits the same capability. Other events are no-op. The maintenance lock
makes normal Hook calls fail open.

Every `CoreDatabase(runtime=True)` connection must set and verify
`journal_mode=PERSIST` and `synchronous=NORMAL` before its first business read or
write. It must not silently fall back to another journal or synchronous mode.
Failure to enter `PERSIST` is `runtime_journal_mode_unavailable`; the Hook fails
open and artifact self-test refuses activation. Non-runtime connections do not
actively select a journal policy.

The Store directory and database file are private by construction and after
opening: POSIX mode is `0700`/`0600`; Windows grants only the current user and
SYSTEM. A link, reparse point, non-regular file, multi-hardlink file or
unprovable private ACL fails closed.

Runtime transaction p95 is at most 10 ms and Hook subprocess p95 is at most
150 ms on the supported local acceptance environment.

### AC-7 — Cutover

Dry-run is zero-write and returns source/target schema, row counts, copy/drop
policy, runtime artifact hash, permanent backup destination and stable
`plan_hash`. Append-only prompt events may change displayed counts without
changing the plan hash.

Apply requires a separately authorized current event. It takes the shared
maintenance lock, writes a complete backup plus SHA-256, creates and validates a
neighboring Core Store, preserves retained events/sessions, attributable
approval consumptions, database namespace and global binding, invalidates all
old proposals, self-tests the zipapp, and replaces Store and Hook configuration.
Any failure restores legacy Store and Hook bytes. The backup is never
automatically deleted.

### AC-8 — Evidence boundary

Automated tests prove contracts, deterministic state and configured runtime in
isolated Owner, Store and event fixtures. Passing the checks relevant to a change
completes its technical validation; it does not prove real user acceptance.
Engineering approval does not authorize changes to the user's Global Owner.

Real Desktop deploy/adopt/revoke, global two-project, primary-folder, compact and
Memories-off scenarios establish only their observed acceptance scope. Observe
them during user-initiated use or an explicitly requested acceptance run, within
its authorized effects. Formal Owner updates require the user's confirmation of
the exact change and scope. If the user defers real acceptance, stop at technical
delivery; do not manufacture adoption evidence or require these scenarios for
every change. Ambient single-card/control remains experimental and cannot block
stable Core.

## Test mapping

| Acceptance | Automated owner |
| --- | --- |
| AC-1, AC-3, AC-4 | `tests/test_rules.py` |
| AC-2, AC-3, AC-6 compact | `tests/test_core_database.py` |
| AC-5, immutable artifact | `tests/test_cli_and_package.py` |
| AC-7 | `tests/test_core_cutover.py` |
| Contract routing and retired source | `tests/test_contracts.py` |
| AC-6 performance | `tests/test_performance.py` |

Real Desktop scenarios are dated acceptance evidence, not a substitute for this
contract.
