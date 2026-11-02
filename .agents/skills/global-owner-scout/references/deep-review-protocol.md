# Deep Review Protocol 5.11

## Evidence posture

Session content discovers leads; current project Owners, ADR/specs, Git, tests, runtime facts, and acceptance corroborate them. A
summary is not proof. Missing Session access is a coverage limitation, not evidence that no learning exists. Keep fact, inference,
and unproven claim separate.

## Phase 0: current-task context

Follow SKILL.md preflight before evidence reads: resolve the current native project, installed Skill, explicit output grant and
an available Python 3 runtime. Use the absolute dispatcher with `-B` and `inspect-context --project-root <bound-project-root>`;
helper cwd is never project authority. Keep the full snapshot hash before and after, including untracked contents. Interactive
reviews use Local or the existing worktree without creating a new task. Scheduled experiments retain their isolated worktree.
For interactive delivery, read the host-injected environment roots before declaring output unavailable; a path pattern alone never proves a grant.
`inspect-output` checks the exact granted root without writes. Recheck at delivery. Missing binding/Git/output capability uses
Terminal v1 before deep work; a changed snapshot invalidates stability without attributing an unproved mutation to Scout.
Scheduled retains its verified inline/Inbox surface and has no artifact-root or file-preview prerequisite.

## Phase 1: identity and task census

1. Derive identity and freeze the 30-day start/end from the current Desktop binding; never a prompt-supplied path or allowlist.
2. Use native history with source `codex`, current host, limit 50; enumerate active and archived partitions separately. Follow
   the returned `nextCursor` with unchanged host/source/archive selection until EOF or a proved window boundary. Stop at a
   window boundary only when the history's ordering and all relevant entries on the page are older than the frozen start;
   a pinned/recent list or one old item is not sufficient. Deduplicate task identity across pages before counting. Record
   `index_pages_read` and `index_terminals.active/archived`; unavailable history remains bounded/degraded, not a complete census.
3. Resume a yielded cell to its actual terminal result before another call; use bounded waits so the user is not left without
   progress. An abandoned cell or invalid call is `execution_protocol_failed`; explicit terminal index failure is
   `native_index_terminal_failure`. Existing partial results are retained without inventing missing pages.
4. Associate natural tasks by native project identity or proved worktree origin. Exclude dedicated Scout, test, Scheduled and
   delegated tasks. In a mixed engineering/Scout task, retain natural work turns before the frozen invocation boundary and exclude
   Scout-generated review/acceptance turns; never drop the whole current task because it also invokes Scout. Page selected tasks to the frozen boundary or EOF using `read_thread`; begin with one turn and bounded
   output. Read relevant truncated output separately. On an explicit capacity error, retry the same cursor once with a smaller
   output request; if it still fails, record `native_thread_pages_terminal_failure` and the exact unread scope. Preserve the
   original failed attempt even if recovery succeeds. Do not change cursor, omit a failed page, or use transcript files.
5. Count discovered, in-window, selected and fully read tasks. `complete` requires both history partitions to reach
   `window_boundary/eof` plus every selected task read to boundary/EOF. `bounded` means history remains incomplete but selected
   reads completed. `degraded` exposes explicit failures. The current active-turn snapshot is sufficient; later concurrent
   updates are outside the frozen observation, not a reason to wait for the task to finish.
6. No transcript parser, database, background queue, task polling service or automation memory substitutes for native evidence.

## Phase 2: project fact reconstruction

Read the project instruction chain, L1/L2/L3 or equivalent Owners, current-status Owner, relevant ADR/specs, windowed Git changes,
tests, failures, acceptance, and bound project snapshot. Recheck Session leads against these sources. Record each source's availability.

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

For an unqualified whole-project depth claim, read the complete active behavior
axioms in bounded, non-truncated sections before selecting downstream examples.
Give each normative clause an obligation/disposition or an exact coverage gap;
headings alone do not cover compound clauses. The independent source pass uses
the same full-axioms floor. Downstream implementation and history remain
relevance-bounded. If that floor cannot be completed, retain useful candidates
but report bounded discovery and keep the whole-project depth claim open.

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
into a universal gate. Apply this check to each completed action: a logging
exception cannot excuse a cleanup or committed-result obligation. A compound
source with project-specific technology still needs a separate disposition for
its portable behavior; do not inherit one route for every action in that clause.

For a source-rich review spanning active Owners and accumulated decisions,
reserve a fresh internal review context before freezing; do not wait for a user
to identify an omission. Use an internal
subagent when available, not another user-facing task. First give it only original
sources and the source index/read gaps, never drafts, Global Owner wording or
expected candidate answers. Freeze its own source-obligation inventory before
providing draft observations/projections for comparison. This prevents the draft
from defining the denominator of the independent check. It must audit independent
source obligations and accepted/reversed paths, including partially represented
ones, and challenge each projected obligation rather than attach one decorative
counterexample to an entire compound card. Correct evidence-backed defects and
recheck associations, privacy and semantic hashes before the final freeze.
After the source inventory is frozen, give the reviewer the exact Human Context and Rule Projection fields, not only draft summaries
or an inaccessible tool-output reference. Check each card's event, cost, before/after and strongest counterpoint against its sources;
generic filler and circular references cannot replace those decision fields. Structural validation does not perform this semantic check.
Preserve earlier failed evaluation records; a correction is not retroactive
blind discovery. If independent context is unavailable, record that coverage
limitation instead of claiming a self-review is independent qualification.

Create two projections from the same evidence:

- Human Context: Simplified Chinese, familiar privacy-safe project vocabulary, concrete event/cost/recommendation/before-after and
  strongest counterpoint.
- Rule Projection: remove project names, paths, commands, product labels, local thresholds, identifiers, raw dialogue, and private
  diagnostics; retain precise `When / Do / Skip` behavior.

Route project architecture to Project Owner, repeatable methods to Skill, and only necessary cross-task behavior increments to
global candidates. Cross-project usefulness alone does not make a whole procedure an always-on instruction. Separate the short
decision obligation from its execution method and compare the obligation with the complete current Owner, including unmanaged
principles. A method route names its actual entry, inputs, applicable task and retained action/exception; an absent or unverified
entry remains a delivery gap. Keep every supported source obligation visible across these destinations, even when the resulting
global set fits. Do not relocate a mandatory behavior merely to pass capacity. Weak or risky ideas may remain without persistence.

For `make_skill`, name the versioned source Owner and whether the existing entry can absorb the method. Follow the
[method handoff SOP](https://github.com/lly-personal/agent-memory-sidecar/blob/main/docs/specs/interface.md#按需方法的维护与交接) after an authorized maintenance request;
the read-only Scout recommendation itself never installs a Skill or updates an Owner.

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
drift or unavailable parity, mark Owner comparison incomplete and remove confirmation. Compare semantics when proved. Map each proposed trigger, obligation and exception to the complete Owner, including unmanaged
principles. A differently worded conjunction of existing clauses is still covered. For `add`, identify the residual obligation
and one concrete permitted failure that existing clauses would not prevent. If none exists, use `already_covered_exact`;
uncertainty stays unproven rather than becoming an extra user choice. Do not copy an existing Skill procedure into global rules.
Use official/first-party research only to support or challenge existing candidates. Add one integration preview per frozen card. Recheck count/order conservation,
privacy, and project read-only fingerprints. Prepare the draft Review Pack through `scripts/scout.py prepare-review` before validating
or rendering it. This binds single and combined confirmation actions to the actual installed Core planner; absence or failure of that
receipt cannot be replaced with manually calculated capacity. Preserve candidates and revise exact consolidation/replacement/routing
when needed, then repeat planning before confirmation. If that requires different Rule Projections or merged source observations,
return to Phases 5–6 and create a new content-bound revision with every source obligation accounted for. Preserve the original
facts, evidence and frozen artifacts; do not overwrite them or repeat an unchanged task census. Integration does not silently edit
an existing frozen card. Validate Project and Review Pack objects through `scripts/scout.py`. Every Python helper uses `python -B`; never use
a dynamic import or an inline import that can create `__pycache__`.

If the resolver returns `unavailable`, remove confirmation and report the limitation. Never search upward, inspect the project-root
`AGENTS.md` as a substitute, or guess a canonical path from the current checkout.

For delivery, use the single artifact and receipt sequence in SKILL.md and the [Delivery contract](https://github.com/lly-personal/agent-memory-sidecar/blob/main/specs/global-owner-scout-delivery-v1.md).
The renderer puts actual decisions first and covered/no-change evidence in a reference index. No action is needed for covered
cards; every source and card still conserves. A queued request is not proof of display. Technical completion and the result link
stay in this task; no separate controller chat is required to finish the review.

For recovery, reuse `verify-final` on the actual prior receipt and original granted output root. Reconstruct the manifest from
that same immutable file; never regenerate the evidence or rewrite the previous artifact. Exact human selections resume through
the existing installed Agent Memory bundle handoff after artifact verification and Fresh Core preview. Preserve the queued
observation; it neither grants authorization nor permanently blocks a later independently verified human selection.
The optional paused Scheduled path retains `render-review --surface scheduled` and `verify-visible --surface scheduled`.

Capture the user-level Skill directory bytecode-cache baseline before helper execution and recheck it afterward. A new or changed
`__pycache__`, `.pyc`, or `.pyo` is an external side effect and fails the run; do not delete it from inside the Scout to hide the
failure. The Bootstrap installer, not the Scout, owns cache-free atomic installation.

Terminal meanings:

- `interactive_entry_blocked`: preflight could not prove the project binding, or Git eligibility;
  no deep review ran and no authorization is inferred.
- `ok`: at least one card plus complete/bounded coverage.
- `degraded`: material coverage gap; supported cards remain visible and the run does not count.
- `no_material_delta`: complete/bounded census and all search lenses produced no E2/E3 delta.
- `failed`: execution protocol, privacy, integrity, mutation, required-source, render, or read-only failure; no cards.
- `output_budget_exceeded`: not every card fits; no partial cards.
- `surface_pending`: the exact artifact and final link are externally verified after a host `queued` result; content is discoverable, but the user surface remains unproved and no authorization is inferred.
- `interactive_host_blocked`: no safe task output root, artifact/open failure, or an actual final without a verifiable opened/queued receipt; no partial cards or confirmation.
