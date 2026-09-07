# Deep Review Protocol 5.8

## Evidence posture

Session content discovers leads; current project Owners, ADR/specs, Git, tests, runtime facts, and acceptance corroborate them. A
summary is not proof. Missing Session access is a coverage limitation, not evidence that no learning exists. Keep fact, inference,
and unproven claim separate.

## Phase 0: project front door and isolation

Before any task index, thread page, Owner comparison, or project deep read, Fresh-resolve the current Desktop project binding and
installed Skill identity, then run `python -B scripts/scout.py inspect-context` for the path-free Git/baseline snapshot. If already
in an isolated worktree, continue. This formal invocation authorizes exactly one read-only executor. If in Local, use the host-native
project-task creation operation with the current project, current working-tree state, and this exact invocation as the initial prompt;
do not create an empty child or ask
the user to repeat it. Do not use shell-created worktrees, guessed paths, or partial Local execution. If the project is not eligible,
binding is unavailable, or the host cannot project the task, render Terminal v1 through `python -B scripts/scout.py render-terminal`
and stop before Phase 1.

For interactive `manual_30d`, also check the host-declared current-task output root
and file-preview capability before task census. Use `scripts/scout.py
inspect-output --artifact-dir <host-output-root> --protected-root <project-root>`;
it checks containment without writing. Missing capability returns Terminal v1
before deep work. Recheck these conditions during delivery; preflight does not
prove later writability or visibility. Scheduled checks its final Inbox wrapper
surface instead; it has no file artifact root or file-preview prerequisite.

## Phase 1: identity and task census

1. Derive the project from the current Desktop binding. Compute opaque content/host identity; never trust a Prompt-supplied name,
   path, ID, or allowlist.
2. Call the native task index once with `limit=50`. Run its enclosing execution cell with a 60-second initial yield. If it returns a
   `cell_id`, call `wait` on that same cell up to two times, 60 seconds each, until terminal. Do not issue a second index call while
   the cell is running; `Script running` is not unavailable or timeout evidence.
3. An unresumed cell, invalid request, or interrupted execution is `failed / execution_protocol_failed`. It may preserve one already
   proved index terminal enum, but it produces no cards. An explicit terminal index error is
   `degraded / native_index_terminal_failure`; an explicit host cap is `bounded / native_index_host_cap`.
4. Associate tasks through native identity, current primary folder, or isolated-worktree origin. Exclude Scheduled, Scout, test, and
   delegated tasks. For every selected natural task, use native `read_thread` pages with `turnLimit=10` and
   `maxOutputCharsPerItem=20000` to the evidence-window boundary or EOF. Do not probe larger values. Any yielded execution cell
   follows the same resume-to-terminal rule. An explicit terminal page error is
   `degraded / native_thread_pages_terminal_failure`; record truncation and preserve cards independently supported by non-Session
   formal project evidence.
5. Count discovered, in-window, selected, fully read tasks and pages; list exclusions and reasons. Use `complete` only with
   `native_index_completed + native_thread_pages_completed`; use `bounded` only with
   `native_index_host_cap + native_thread_pages_completed`. The current active-task snapshot is sufficient; record concurrent
   later changes and never wait for another project task to end.
6. Never use transcript storage, file bridges, automation memory, or databases as a Session substitute.

## Phase 2: project fact reconstruction

Read the project instruction chain, L1/L2/L3 or equivalent Owners, current-status Owner, relevant ADR/specs, windowed Git changes,
tests, failures, acceptance, and isolated snapshot. Recheck Session leads against these sources. Record each source's availability.

Build the six-category `evidence_sources` inventory defined in contracts.md.
Start from current Owners and follow their relevant references in bounded
sections; record uncovered sections rather than treating truncated output as
read. The 30-day limit applies to recent Sessions/Git, not still-active design
knowledge. Explicitly inspect paired effective/ineffective paths and accepted
decisions even when no recent Session mentions them.

Before selecting detailed reads, inventory the headings and numbered normative
clauses of current behavior Owners and the accepted/reversed decisions in the
current-status Owner. Use that source index to plan bounded reads across the
whole active knowledge surface; reading every ADR does not cover unread active
axioms or later corrections. Read the full context of each selected clause,
including its exception and linked acceptance or failure. Keep unread sections
explicit; do not substitute an arbitrary prefix, recent entries or a keyword
search for the current Owner's knowledge inventory.

## Phase 3: contrastive causal review

For each high-signal event answer:

- 用户反复纠正或解释了什么？
- 哪个后续失败推翻了先前的成功判断？
- 哪项设计或行为最终获得正式接受或真实验收？
- 哪条更早存在的行为原则可以避免重复成本？
- 哪些只有机制证据，哪些已经达到用户或产品结果？

Prefer belief-before, observed contradiction, accepted change, and current boundary over generic lessons.
Link every high-value event to its declared source refs. Compare failed and
successful paths under matching conditions; do not infer causality from frequency
or task summaries alone.

## Phase 4: candidate exhaustion

Search independently for repeated correction, failed recovery, premature success, Owner drift, acceptance-boundary mistakes,
durable design decisions, and reusable analysis methods. Do not read global-owner wording until this inventory is complete. Do not
cap candidates or manufacture cards. E2 requires repetition, formal acceptance, or real acceptance; E3 requires independent
evidence from at least two projects and names only opaque project refs.

## Phase 5: counterevidence and two projections

For every E2/E3 candidate find conflict, legitimate exception, project-only constraint, stronger existing Owner, and harmful
global interpretation. Require meaningful counterevidence and a concrete Skip boundary.

Challenge each projected obligation with a legitimate successful path under
different preconditions: if the intended result is already proved, is the
prescribed action still necessary? Separate the accepted outcome from the
project's chosen means, count or sequence. Narrow `When`, preserve a concrete
`Skip`, or route the method to Project/Skill; do not turn one local procedure
into a universal gate. Apply this check to the completed projection, not just
the source excerpt, before freezing it.

Create two projections from the same evidence:

- Human Context: Simplified Chinese, familiar privacy-safe project vocabulary, concrete event/cost/recommendation/before-after and
  strongest counterpoint.
- Rule Projection: remove project names, paths, commands, product labels, local thresholds, identifiers, raw dialogue, and private
  diagnostics; retain precise `When / Do / Skip` behavior.

Route project architecture to Project Owner, repeatable methods to Skill, cross-project behavior to global candidates, and weak or
risky ideas to no persistence.

Record each signal in `observations` with its event IDs and structured
disposition. Separate the project implementation from the portable behavior;
name exact Owner coverage or the missing evidence when excluding a signal.
Single-project formal acceptance can support E2. Project ownership and absence
of a second project are not automatic global-candidate exclusions. Account for
every event and every card, including evidence-backed no-persistence decisions.
An exact rule in the project Owner proves local coverage only. If its behavior
has cross-project value, retain that portable projection for actual Global Owner
comparison; do not exclude it here merely because the project already states it.

Before freezing, perform a second omission check from the source index back to
the observations. Revisit high-value normative clauses, accepted behavior
changes and rejected paths whose independent obligations lack a matching
disposition, including clauses already linked to a related observation. Preserve
each distinct action, trigger, user cost and legitimate exception when merging
or abstracting a compound clause; a similar topic is not semantic coverage.
Record a justified disposition or the exact unread gap. This pass starts from source material, not
from the model's existing event/card list. In a large Owner, an uncovered section
that can contain reusable knowledge limits discovery qualification even when
all declared events conserve. It does not require a card for every paragraph.

## Phase 6: freeze project semantics

Create all complete Project Cards, validate privacy/Chinese narrative/evidence refs, compute normalized evidence hash, then compute
`project_claim_hash` over every semantic field. Validate the entire Project result before global comparison.
Compute `normalized_evidence_hash` from the exact canonical `direct_evidence`
array. Preserve the validated project object; integration adds previews only.
Zero cards require nonempty, evidenced dispositions; never fill a no-delta result
with an empty inventory or claim exhaustive knowledge beyond the declared scope.

## Phase 7: integration and task-scoped delivery

Run `python -B scripts/scout.py resolve-owner-parity`. With matched parity, read the active host-local global Owner and verify its bytes
against the returned hash; the equal canonical hash proves identical canonical content without revealing its physical path. With
drift or unavailable parity, mark Owner comparison incomplete and remove confirmation. Compare semantics when proved, and use
official/first-party research only to support or challenge existing candidates. Add one integration preview per frozen card. Recheck count/order conservation,
privacy, and project read-only fingerprints. Validate Project and Review Pack objects through `scripts/scout.py`. Every Python helper uses `python -B`; never use
a dynamic import or an inline import that can create `__pycache__`.

If the resolver returns `unavailable`, remove confirmation and report the limitation. Never search upward, inspect the project-root
`AGENTS.md` as a substitute, or guess a canonical path from the current checkout.

For the explicit user entry, resolve the current task's explicit host-generated output root. It must exist outside the reviewed
project; never guess a system temp directory, project `.sandbox`, arbitrary `$CODEX_HOME` path, another task, or a persistent bridge.
A host-declared task output root may physically live inside host-managed app storage; only that explicit grant is eligible. Invoke
`python -B scripts/scout.py prepare-delivery --artifact-dir <host-output-root> --protected-root <project-root>` with the Review Pack on stdin. The helper
renders, verifies, creates, flushes and reads back the complete Markdown, then emits a compact Delivery v1 manifest.

Pre-render `open_succeeded`, `open_queued` and `open_failed` compact receipts through `scripts/scout.py render-receipt` from that
manifest. Success and queued rendering receive
the exact artifact path and host-output root and recheck direct-child containment, read-only state, bytes, hashes and visible-output conservation.
Recheck project/Skill read-only fingerprints,
then open the artifact with the current-task host file-preview tool as the final tool call. Return the exact success receipt only if
the host call succeeds. An exact `queued` result returns the content-bound queued receipt and remains `surface_pending` with
confirmation disabled; any other non-success result returns the blocked receipt. Do not copy the Review Pack into chat. Missing output root, renderer
failure, artifact mismatch, host-open failure or inability to preserve the compact receipt returns `interactive_host_blocked`,
`render_integrity_failed`, or `output_budget_exceeded`; never manufacture partial or replacement Markdown. When no valid manifest
exists, construct `global_owner_scout_terminal_v1` and run `scripts/scout.py render-terminal`; do not call a manifest receipt path.

The interactive artifact open is the final tool call. Do not invoke `agent-memory`, another Skill, another tool, or a post-open audit.
The task artifact and compact receipt are already the terminal memory-review artifact. Any mandatory higher-level audit stays silent.
A separate controller task reads the actual final and invokes `python -B scripts/scout.py verify-final --artifact-root
<host-output-root>`; `surface_pending` proves discoverability/integrity only and only `surface_observed` can qualify the host. The optional paused Scheduled path continues to use
`scripts/scout.py render-review --surface scheduled` plus `scripts/scout.py verify-visible --surface scheduled` and its final wrapper.

Capture the user-level Skill directory bytecode-cache baseline before helper execution and recheck it afterward. A new or changed
`__pycache__`, `.pyc`, or `.pyo` is an external side effect and fails the run; do not delete it from inside the Scout to hide the
failure. The Bootstrap installer, not the Scout, owns cache-free atomic installation.

Terminal meanings:

- `interactive_entry_blocked`: preflight could not prove the project binding, Git eligibility, or host-native worktree projection;
  no deep review ran and confirmation is disabled.
- `ok`: at least one card plus complete/bounded coverage.
- `degraded`: material coverage gap; supported cards remain visible and the run does not count.
- `no_material_delta`: complete/bounded census and all search lenses produced no E2/E3 delta.
- `failed`: execution protocol, privacy, integrity, mutation, required-source, render, or read-only failure; no cards.
- `output_budget_exceeded`: not every card fits; no partial cards.
- `surface_pending`: the exact artifact and final link are externally verified after a host `queued` result; content is discoverable, but the user surface remains unproved and confirmation is disabled.
- `interactive_host_blocked`: no safe task output root, artifact/open failure, or an actual final without a verifiable opened/queued receipt; no partial cards or confirmation.
