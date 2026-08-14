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
`~/.codex/AGENTS.md`; any failure restores both.

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

Automated tests prove only contracts, deterministic state and configured
runtime. Core completion additionally requires real Desktop deploy/adopt/revoke,
global two-project, primary-folder, compact and Memories-off scenarios. Ambient
single-card/control remains experimental and cannot block stable Core.

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
