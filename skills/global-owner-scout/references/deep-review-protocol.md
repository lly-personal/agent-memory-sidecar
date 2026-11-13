# Deep Review Protocol

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

Native-session candidate adapters are defined in contracts.md. Pi uses the current ExtensionContext, Claude the current
native init stream programmatically or the ordinary Skill's distinct native substitution context; mechanically pass those to
`inspect-native` before history. The latter also checks inherited execution cwd against the native startup project; do not
change cwd to make a mismatch pass. A current, explicitly user-selected output root
is also allowed; inspect the actual native request/selection, never grant from a model assertion or quoted path.
For Pi/Claude review use Project v8/Pack v9 native scopes, preserve the original SDK records and expose unknown/error coverage.
Do not fabricate Codex active/archived partitions, EOF or completed task histories. Current active-turn snapshots remain usable;
the native turn observer does not require the whole chat to finish or prove business success. The Codex procedure below stays unchanged.

## Phase 1: identity and task census

1. Derive identity and freeze the 30-day start/end from the current Desktop binding; never a prompt-supplied path or allowlist.
   Native task cwd plus one matching same-host inventory Git root is sufficient when projectId is absent/null. A conflicting
   non-null ID, ambiguous root or unproved worktree relation is not. Use this same evidence rule for task association below;
   missing optional project membership metadata does not discard natural project work.
2. Use native history with source `codex`, current host, limit 50; enumerate active and archived partitions separately. Follow
   the returned `nextCursor` with unchanged host/source/archive selection until EOF or a proved window boundary. Stop at a
   window boundary only when the history's ordering and all relevant entries on the page are older than the frozen start;
   a pinned/recent list or one old item is not sufficient. Deduplicate task identity across pages before counting. Record
   `index_pages_read` and `index_terminals.active/archived`; unavailable history remains bounded/degraded, not a complete census.
3. Resume a yielded cell to its actual terminal result before another call; use bounded waits so the user is not left without
   progress. Retain and diagnose rejected calls and local transfer/parse errors. If the same source and cursor can be recovered
   within the original authorization and retry limits, correct the call and continue; unfinished work alone is not a failure.
   An unrecovered cell, lost source provenance or unrecovered interruption is `execution_protocol_failed`; explicit terminal
   index failure is `native_index_terminal_failure`. Never hide the original error or invent missing pages.
4. Associate natural tasks by native project identity or proved worktree origin. Exclude dedicated Scout, test, Scheduled and
   delegated tasks. In a mixed engineering/Scout task, retain natural work turns before the frozen invocation boundary and exclude
   Scout-generated review/acceptance turns; never drop the whole current task because it also invokes Scout. Page selected tasks to the frozen boundary or EOF using `read_thread`; begin with one turn and bounded
   output. Read relevant truncated output separately. On an explicit capacity error, retry the same cursor once with a smaller
   output request; if it still fails, record `native_thread_pages_terminal_failure` and the exact unread scope. A successful
   page with fields still truncated after available native reads uses that same compatibility enum, with the actual successful
   return and missing fields stated in `coverage/uncovered` and `limitations`, not a claimed native exception. Preserve earlier
   failed attempts even after recovery. Do not change cursor, omit a failed page, or use transcript files.
5. Count discovered, in-window, selected and fully read tasks. `complete` requires both history partitions to reach
   `window_boundary/eof` plus every selected task read to boundary/EOF. `bounded` means history remains incomplete but selected
   reads completed. `degraded` exposes explicit failures or unrecoverable selected-content truncation. The current active-turn snapshot is sufficient; later concurrent
   updates are outside the frozen observation, not a reason to wait for the task to finish.
6. No transcript parser, database, background queue, task polling service or automation memory substitutes for native evidence.

Forward actual native page objects through host code orchestration to a file-write data tool, then
`import-history --input-file`; do not embed large pages in executable JavaScript or split code to avoid
host review-size limits. Seal each page once,
reuse its native_file/hash and preserve original cursors/truncation. Never transcribe raw history in model-written
JSON chunks. Use `--input-file` for result validation/preparation and `describe-input` for current field requirements.
For continuation, reuse the verified report and update only changed sources; do not restart its census.

Acquisition and comprehension are different. A tool batch that fetches pages and prints only counts has not exposed their
meaning to the analysis pass. Read or surface the selected bounded passages, including the user's correction, actual action
and result; retain exact source references in the existing evidence inventory. Mark unread or only summarized content as
such. Full pagination is a transport result, not proof of whole-project analytical depth.

## Phase 2: project fact reconstruction

Start from user outcomes, not a catalogue of normative clauses. Reconstruct the engineering map before choosing lessons:
identify goals and boundaries, actors and real entry points, critical journeys, module/tool consumers, state ownership,
environment differences, failure/recovery/revoke paths, and the maintenance/release/deployment chain. Follow the actual handoffs
through code, interfaces and available runtime evidence. For each critical path, explain preconditions, input/output,
authorization, state transitions and failure recovery. A module inventory or correct documentation does not prove this path works.

Use `project_map.nodes/edges/journeys` and coverage dimensions suited to this project's goals and risks. A relation claim can
record the handoff's prerequisites and input/output; journey recovery names the actual entry and authorization boundary.
Compare intended and effective behavior across relevant environments; installation, enablement, execution and adoption remain
separate claims. Label design, implementation, observation, inference and unknown explicitly. Keep counterevidence and missing
links visible. Do not fabricate a complete graph or demand a fixed number of cells. Semantic coverage is checked against user
outcomes and source material, not node counts. No new recommendations is compatible with a useful engineering map.

This is a reusable capability across target projects and environments. The Sidecar repository owns its implementation, not
the reviewed project's topology. Order journeys by the reader's main outcome, then supporting/recovery paths; the overview first explains overall responsibilities and key relationships, not merely the first journey. Derive every label, step, owner and environment from the target evidence. Do not copy the example project's
memory lifecycle, release mechanism or path counts into other projects, or draw a sequence between unrelated journeys.

Before arranging the view, outline how a reader can connect the goal and boundary to the main responsibilities, a concrete
entry-to-result path, and its maintenance or recovery point. Distinguish structural containment/dependency, execution handoffs
and state authority; a flat inventory with identical arrows does not explain all three. Choose the representation by the
question: grouped structure for responsibility, an ordered path for handoffs, a state view for recovery, or a matrix for actual
environment/evidence comparisons. Do not force every relation into one graph or require a fixed layer/node count. Overview,
path and matrix keep the same object/source identities and reading context. The main explanation remains readable without
interaction; selection reveals relevant detail instead of requiring the reader to assemble the whole system across tabs.

The mental model is goal -> actor and task -> action -> system effect -> downstream feedback -> recovery. For user-facing
fields and controls, explain what to enter, what the action changes, when it takes effect, what other entries observe, and
what remains unchanged where that distinction resolves a real confusion. Reuse node summaries, typed edge claims and journey
outcome/recovery; do not add a parallel scenario store. A path that only names modules is insufficient even if every link works.
Show the consequence claims on the normal path, not only in an expert relationship tab. Distinguish promised behavior from
observed behavior and unknowns in place. Legitimate architectural choices explain why to retain or change a boundary;
prohibited shortcuts are counterexamples, not alternative solutions used to make the preferred option look inevitable.

Use the current installed `visualize` contract when an inline explorable explanation helps the user. It owns transport and
host interactions, while this Skill owns source interpretation. Choose an appropriate presentation; the existing overview renderer is one reusable option, not a universal format.
Learn from the visual language and interaction of actual user-accepted presentations without assuming that the user approved
their content structure. Compare hierarchy, spacing, control clarity, selection feedback and continuity in the current host.
Choose the content structure separately from the actual reader question. The diagram is an optional view of the same facts. Keep the initial content coherent,
progressively expose relationships, and preserve location and return. Do not require another tool or installation when the
native surface is absent; use the same Markdown and current chat. Positive presentation feedback does not pass content depth.

Before styling, prioritize the reader's questions and content/actions: what the project accomplishes, how its main journey
works, how supporting capabilities connect, then the selected object's evidence, exceptions and maintenance. Use that priority
to choose type hierarchy, alignment, proximity and visual emphasis in the existing template. Avoid equal-weight module grids
or a permanent stack of overview, navigation, path and every detail. Progressive disclosure preserves context and return paths;
it does not remove difficult relations from coverage. Public designer discussions and design systems can challenge this choice,
but record the concrete transferred decision and its limits instead of copying a brand, adding a dependency or treating a source's
reputation as acceptance. Keep source-backed design principles in the existing presentation contract, not a parallel style authority.

Use the current host's presentation contract and choose capabilities by explanatory value. The existing renderer may be reused when it fits; a native alternative may be frozen through Delivery's visual-input. Text and static comparisons do not require interactive UI. Upstream templates or guideline servers are research
inputs, not proof of host compatibility or a reason to add a renderer, client or MCP. Verify a concrete missing capability at its
consumer before reuse; omit interactions and decorative structure that add no observable value. Keep semantic coverage, layout
checks and user comprehension separate. Explicit design rejection remains a failed review, even when technical checks pass;
preserve the unaffected evidence. The current [presentation contract](https://github.com/lly-personal/agent-memory-sidecar/blob/main/docs/specs/interface.md#project-scout-global_owner_scout_project_v7)
and M1 evaluation own these requirements; do not create another design checklist or regenerate an immutable report to conceal a failure.

For inspect, perform this current-design reconstruction only. Sessions are not applicable; still declare unavailable design,
implementation or runtime evidence. Freeze the map without manufacturing events/cards or reading Global Owner. For review,
continue the following source/causal phases and link real maintenance deltas to map objects. Project/Skill improvements survive
existing global coverage; route repeatable methods to an existing Skill or Engineering Contract Review when appropriate.

When reviewing reuse or drift, trace the natural task through its current routing Owner, actual tool call, required dependencies,
and independent result consumer. Distinguish a selection failure from invocation, dependency, consumer-verification or maintenance
drift. A document read, matching file count, tool name in prose or self-selected checklist does not prove execution. Preserve
valid equivalent paths and scoped exploratory probes. An optional workflow evaluator may supply frozen case/host/version-bound
traces and checks; inspect their actual evidence and unmeasured scope, not just the report verdict. Its absence does not block
Scout. Do not start an evaluation, install a dependency, alter a model, or write target-project cases from this read-only review.
User-requested capture/execution continues through that capability in the appropriate project scope. Use existing map sources,
journeys and engineering cards; do not create another registry or a mandatory per-task review.


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

Before selecting recommendations, trace goals and quality requirements through responsibility boundaries, constraints,
implementation, consumers, recovery and historical decisions. Examine effective designs as well as failures: what premise
justified a boundary, what changed, which stable mechanism repeats, whether native capabilities can replace glue, and what can
be removed while preserving the user outcome. Use typed relationships in the existing map, not a second inventory.

Engineering advice is distinct from a rule candidate. Current source facts may support an E1 discussion hypothesis without a
recent failure or accepted change. Present relevant retention, integration, abstraction, replacement and removal alternatives;
substantial refactoring is a legitimate alternative, not a last resort admitted only after smaller options fail. Link parent and
child advice when it helps separate decisions. Each layer explains affected and unaffected responsibilities, evidence,
benefit hypothesis, migration cost, counterexamples, owner and validation conditions. Do not cap depth or manufacture layers.
An opinion, a map click or a hypothesis never grants implementation authority. Reuse existing authorization when it already
covers the maintenance; do not ask again merely because a proposal spans layers.


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
cap candidates or manufacture cards. For rule candidates, E2 requires repetition, formal acceptance, or real acceptance; E3 requires independent
evidence from at least two projects and names only opaque project refs.

## Phase 5: counterevidence and two projections

For every rule candidate find conflict, legitimate exception, project-only constraint, stronger existing Owner, and harmful
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

For each destination compare the actual maintained implementation, not just the existence of a rule. A documented obligation can
be fully covered globally while its project implementation or method still fails. Represent a supported residual maintenance delta
as an existing `route_to_owner` Project Card with its concrete before/after and versioned Owner; use `route_supported` for its
integration. Existing global coverage must not turn that card into ignore. If the target already satisfies the finding, retain
the exact Owner evidence as an exclusion instead. Do not invent work from the number of observations. Before freezing, order
actionable recommendations by evidenced user impact and dependencies; preserve that order afterward, with no candidate cap.

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

Freeze map and recommendations together. Recheck each critical journey against original implementation and observed handoffs,
including recovery and environment differences; the independent pass must challenge whole-path omissions as well as obligations.
Map `source_revision` is the read-only snapshot HEAD, and `observed_at` is the frozen observation time. Preserve exact source
references and advice links. Static and interactive views must derive from these same fields.

Create engineering or rule-candidate Project Cards with their appropriate fields, validate privacy/Chinese narrative/evidence refs, compute normalized evidence hash, then compute
`project_claim_hash` over every semantic field. Validate the entire Project result before global comparison.
Compute `normalized_evidence_hash` from the exact canonical `direct_evidence`
array. Preserve the validated project object; integration adds previews only.
Zero cards require nonempty, evidenced dispositions; never fill a no-delta result
with an empty inventory or claim exhaustive knowledge beyond the declared scope.

## Phase 7: integration and task-scoped delivery

For rule candidates only, run `python -B scripts/scout.py resolve-owner-parity`. Engineering-only reviews skip this phase of rule integration and retain null Owner/preview fields. With matched parity, read the active host-local global Owner and verify its bytes
against the returned hash; the equal canonical hash proves identical canonical content without revealing its physical path. With
drift or unavailable parity, mark Owner comparison incomplete and remove confirmation. Compare semantics when proved. Map each proposed trigger, obligation and exception to the complete Owner, including unmanaged
principles. A differently worded conjunction of existing clauses is still covered. For `add`, identify the residual obligation
and one concrete permitted failure that existing clauses would not prevent. If none exists, use `already_covered_exact`;
uncertainty stays unproven rather than becoming an extra user choice. Do not copy an existing Skill procedure into global rules.
Use official/first-party research only to support or challenge existing candidates. Add one integration preview per frozen rule candidate; engineering Review Cards use discuss with no rule actions or token. Recheck count/order conservation,
privacy, and project read-only fingerprints. Prepare the draft Review Pack through `scripts/scout.py prepare-review` before validating
or rendering it. For rule candidates, this binds single and combined confirmation actions to the actual installed Core planner; absence or failure of that
receipt cannot be replaced with manually calculated capacity. Engineering-only prepare-review does not resolve Owner or call Core. Preserve candidates and revise exact consolidation/replacement/routing
when needed, then repeat planning before confirmation. If that requires different Rule Projections or merged source observations,
return to Phases 5–6 and create a new content-bound revision with every source obligation accounted for. Preserve the original
facts, evidence and frozen artifacts; do not overwrite them or repeat an unchanged task census. Integration does not silently edit
an existing frozen card. Validate Project and Review Pack objects through `scripts/scout.py`. Every Python helper uses `python -B`; never use
a dynamic import or an inline import that can create `__pycache__`.

If the resolver returns `unavailable`, remove confirmation and report the limitation. Never search upward, inspect the project-root
`AGENTS.md` as a substitute, or guess a canonical path from the current checkout.

For delivery, use the frozen projections and receipt sequence in SKILL.md and the [Delivery contract](https://github.com/lly-personal/agent-memory-sidecar/blob/main/specs/global-owner-scout-delivery-v1.md).
The renderer provides a short overview and expands the first actionable recommendation in the same chat. Complete evidence is
linked and opened only on request; absence of an open call is not an error. It puts actual decisions first and covered/no-change evidence in a reference index. No action is needed for covered
cards; every source and card still conserves. A queued request is not proof of display. Technical completion and the result link
stay in this task; no separate controller chat is required to finish the review.

For recovery, reuse `verify-final` on the actual prior receipt and original granted output root. Reconstruct the manifest from
that same immutable file; never regenerate the evidence or rewrite the previous artifact. Exact human selections resume through
the existing installed Agent Memory bundle handoff after artifact verification and Fresh Core preview. Preserve the queued
observation; it neither grants authorization nor permanently blocks a later independently verified human selection.
The optional paused Scheduled path retains `render-review --surface scheduled` and `verify-visible --surface scheduled`.

For continuation from an already mechanically acquired Codex native page, the following host-code example selects one exact
final without retyping it. Run it with Python `-B` and the acquired native file, selected source turn ID and a new input file
under the current checked output grant as its three arguments. These values come from the current native metadata and output
selection, not user setup or a guessed path. This reads no new history and does not establish the acquired file's provenance.

```python
import json
import sys
from pathlib import Path

page = json.loads(Path(sys.argv[1]).read_bytes())
final, = [item for turn in page["turns"] if turn["id"] == sys.argv[2]
          for item in turn["items"] if item["type"] == "agentMessage" and item.get("phase") == "final_answer"]
if final.get("truncated") or final.get("textTruncated"):
    raise ValueError("selected native final is truncated")
with Path(sys.argv[3]).open("xb") as output:
    output.write(final["text"].encode("utf-8"))
```

Pass that file unchanged to the existing `scout.py verify-final --input-file` with the original `--artifact-root` and current
native-bound `--project-root`. A missing, ambiguous or natively marked truncated final, or an existing input file fails without
overwriting evidence. A valid receipt cannot prove that the surrounding final prose survived clipping; `verify-final` retains
its artifact/receipt verification scope. This example proves only byte-preserving selection; original acquisition, helper
execution and semantic acceptance remain separate.

Capture the user-level Skill directory bytecode-cache baseline before helper execution and recheck it afterward. A new or changed
`__pycache__`, `.pyc`, or `.pyo` is an external side effect and fails the run; do not delete it from inside the Scout to hide the
failure. The Bootstrap installer, not the Scout, owns cache-free atomic installation.

Terminal meanings:

- `interactive_entry_blocked`: preflight could not prove the project binding, or Git eligibility;
  no deep review ran and no authorization is inferred.
- `ok`: at least one card plus complete/bounded coverage.
- `degraded`: material coverage gap; supported cards remain visible and the run does not count.
- `no_material_delta`: complete/bounded census and no evidenced engineering or qualified rule-candidate delta.
- `failed`: execution protocol, privacy, integrity, mutation, required-source, render, or read-only failure; no cards.
- `output_budget_exceeded`: not every card fits; no partial cards.
- `surface_pending`: the exact artifact and final link are externally verified after a host `queued` result; content is discoverable, but the user surface remains unproved and no authorization is inferred.
- `interactive_host_blocked`: no safe task output root before artifact creation; no partial cards or confirmation.

Artifact creation or integrity failure uses the existing failure contract in [contracts.md](contracts.md#manifest-free-terminal).
After the artifact is verified, delivery observations follow the
[Interactive Delivery contract](contracts.md#interactive-delivery): not requesting a preview is valid, and a queued or failed preview
does not block discussion of the verified advice. Neither observation proves display or grants authorization.
