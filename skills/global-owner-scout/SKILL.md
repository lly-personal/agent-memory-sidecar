---
name: global-owner-scout
description: Understand a project's goals, actors, scenarios and real workflows when asked for an overview; deeply review it when requested; continue from an identifiable delivered map. Give a brief explanation and any supported recommendation in the current chat, with complete evidence by link. Do not restart discovery for follow-ups or trigger for unrelated ordinary work.
---

# Global Owner Scout

## Contract

- Skill version: `5.19.6`
- Project result: `global_owner_scout_project_v7`
- User review: `global_owner_scout_review_pack_v8`
- Manifest-free terminal: `global_owner_scout_terminal_v1`
- Preflight snapshot: `global_owner_scout_preflight_v1`
- Mode: `project_scout`; interactive-only `central_review` remains optional.
- For a new review, read [references/contracts.md](references/contracts.md) and execute
  [references/deep-review-protocol.md](references/deep-review-protocol.md) completely. For follow-up, use Recovery and continuation below.
  Prefer the host's file-read tool for long required references; batch independent reads when supported and reuse acquired content.

This Skill creates project-read-only review drafts. It never creates proposals, approval refs, Owner mutations, project files,
database rows, commits, pushes, or external-system writes. Its writes are immutable review artifacts and their captured native inputs under the
current task's explicit host-generated or explicitly user-selected output root, outside the reviewed project and every capability/state root not explicitly
granted as that task output surface. The explicit entry is `$global-owner-scout 复盘当前项目` or “看懂当前工程全貌” in the currently bound target Git project task. Review uses `manual_30d`; inspect uses `current`. Interactive runs never read automation memory,
and never asks the user to provide resource settings. The Scout uses the current task's host-resolved model/reasoning settings and records observable requested/actual values; it supplies no override. The current Desktop project binding is authoritative; no Prompt may contain a
project name, path, project ID, candidate hint, or the deep-review procedure.

For “梳理当前工程的角色、场景和操作流程”, use inspect through this same entry. Derive relevant roles from the project;
the user need not name companion Skills or supply a long procedure. Explain who wants what, the starting state and entry,
continuous actions, branches and handoffs, the actual result consumer, and failure recovery. Reuse the existing map fields;
missing evidence remains unknown. A clear map with no recommendation is valid. Mapping authorizes neither implementation
nor runtime testing. On a later authorized follow-up, use the existing project workflow and the appropriate review or test
tool only when it answers that task; Scout does not become a mandatory execution coordinator.

The default contract above is the Codex lane. The Pi package exposes the same Scout source through
`/skill:global-owner-scout`; call the read-only `global_owner_scout_context` tool first. Use the actual current runtime context,
not a Desktop binding: mechanically export Pi ExtensionContext, run `inspect-native`, then the same output-containment
preflight. Inspect still skips history. Native review uses Project v8 / Pack v9 and the actual SDK scopes with
unknown/degraded coverage; never fabricate Codex partitions or complete history. Follow the host contract in
references/contracts.md. Package discovery, source-level execution and installed natural use remain separate evidence.
Forward its actual `native_context` to `inspect-native`; it reads no history and grants no artifact access.
Its selected-model metadata is host configuration, not independent proof of the model that served an API request.
After checking the current output grant, use that tool's `operation=capture_current, artifact_dir=<exact-granted-root>`.
It resolves an available Python3.11+ once, fixes its absolute interpreter, checks native/Git identity and output containment,
then seals the current SDK session through the formal importer. Read selected passages from its returned file for meaning;
never retype the snapshot. Other project sessions remain uncovered unless a separately qualified native source is available.
When invoking Pi, ask for the overview or review in the current project as usual; the agent resolves these tool parameters.
If the host provides no task output grant, the user may select an exact project-external output root in the current request.
No model/thinking override, JSON preparation or full-history claim follows from this choice. Missing context, output grant
or runtime prerequisites stop the affected operation with its precise recovery condition, before reading history.

In Claude, invoke `/agent-memory-sidecar:global-owner-scout` in the target Git project, with an overview or review request.
This is the same method source. These values are supplied by Claude when this Skill is loaded:
session `${CLAUDE_SESSION_ID}`, project `${CLAUDE_PROJECT_DIR}`, Skill `${CLAUDE_SKILL_DIR}`,
plugin `${CLAUDE_PLUGIN_ROOT}`, dependency data `${CLAUDE_PLUGIN_DATA}`.
Invoke the loaded Skill's `scripts/claude_native.mjs context` with `--session-id`, `--project-root`,
`--skill-dir` and `--plugin-root` mapped to those current values. Treat substituted paths as data, never shell code.
Prefer a host argument-vector API. With a shell, encode every value as a shell literal: PowerShell single quotes with each
embedded single quote doubled; POSIX single quotes with each embedded single quote escaped by closing/reopening the literal.
Expandable double quotes are insufficient for paths containing `$()` or backticks. Escape the Node/script paths too.
Resolve the existing Node executable normally under the current host policy; do not run an unresolved placeholder.
This checks current binding without history or writes.
Keep the helper in the current tool's inherited working directory; never cd or set cwd to the startup project merely to pass
binding. Claude's project substitution is startup-stable, so a different current Git tree blocks this route rather than reviewing
the old tree. A child directory in the same Git tree is valid. Historical SDK scope remains the selected native project directory.
For review, first check the output grant in the current request, then use the same entry with `capture`, adding
`--plugin-data` from its current native value and `--artifact-dir`
from the exact current output grant, with the same literal-argument handling.
The agent handles these arguments; the user supplies a review request and, only if absent, an output location.
For parameter discovery, run the loaded `claude_native.mjs --help`; it needs neither a project nor a prepared SDK.
Resolve sibling methods through their native namespaced Skill entry or the installed marketplace's explicit `skills` paths.
Those methods have their own reference base, which may differ from the Scout's directory layout.
For an explicitly selected historical session, add `--source-session-id` without changing the current caller's session.
Page with `--offset` and `--limit`; SDK pages remain observed-only and never prove full history or a chat terminal.
Read selected passages from the returned immutable file, then continue the native review and delivery contract.
The deployment prerequisite prepares the pinned SDK separately; Scout never installs it on demand. If unavailable, report
that exact condition. All helper calls obey existing permissions: preserve a refusal and do not reroute around it.
Discovery, scoped capture and natural semantic review are distinct evidence; none alone proves the full chain.

## Purpose and native presentation

Preserve each actual native return object in host code before printing a summary. Use the same dispatcher's
`capture-native --artifact-dir <granted-root> --protected-root <target-root>` with stdin or `--input-file` when a
native data-file writer is unavailable. It freezes the complete object, including index/error/truncation fields,
and returns `raw_file/sha256`; it proves neither provenance, successful calls, coverage nor comprehension.
The executable host-transfer examples and retained-error behavior are in Phase 1 of the deep-review protocol.
For native history, pass the actual tool result directly through host code orchestration into
`scout.py import-history --project-root <native-source-root> --session-id <native-id> --artifact-dir <granted-root> --protected-root <target-root>`.
The helper reads JSON on stdin or `--input-file`, seals one acquired page and returns its file/hash,
cursor and truncation metadata. Reuse that native_file for authorized workflow-eval capture; never
retype large history JSON through model-written chunks. Host tools may forward objects to the native
file-write tool as data and pass that exact path with `--input-file`. Generate that transfer in host
code from the actual tool object; do not embed an entire page in executable REPL code, which has a
separate review-size limit. Small native REPL transfers remain optional. Use the current tool schema,
not a guessed database or transcript. Do not split executable payloads to evade a host review limit.
If direct transfer is unavailable, expose the precise evidence gap instead of claiming a complete raw export.
Read the selected source passages for meaning; mechanical import/counts do not prove understanding.
Validation and preparation accept `--input-file`. Pi/Claude use `describe-input native-project|native-review` for Project v8 /
Pack v9; Codex uses `describe-input project|review` for Project v7 / Pack v8. Read these current field/mode requirements
before writing semantic results, rather than searching engine source or maintaining a second schema copy.

Choose from the user's actual request, not the repository name. “看懂当前工程全貌” uses `purpose=inspect`: recover an existing
map if identifiable, check its source revision and relevant source changes, and reuse it when still current. If absent or stale,
reconstruct current design with the project-map method in Phase 2; skip the task census, candidate search, Global Owner resolver
and Core preview. Freeze `view_ready` or `degraded` with the uncovered scope. Do not label this a deep review.
“复盘当前工程” uses `purpose=review` and the complete protocol, including whole-system reconstruction before candidate selection.
Both purposes explain the whole system even with zero recommendations; the evidence model does not prescribe a visible diagram. Ordinary authorized development maintains the affected Owner and
acceptance through its existing workflow; it does not start a whole-project review. The user chooses model, reasoning and time
investment; do not inject overrides or impose a fixed matrix size, advice count or review time limit.

For reuse-related questions, explain how a natural task reaches the current Owner, formal tool and actual result consumer.
Keep intended routing, observed invocation, fulfilled dependencies and accepted results separate. Existing workflow-evaluation
evidence can inform a review, but Scout never launches its batches or writes project cases. Target-project maintenance and
acceptance stay in the scope the user selected; asking for an overview does not authorize either.

Choose presentation from the user's question and the target project's actual architecture. Plain prose or a table can be sufficient;
a static relation can use Mermaid; an explorable process, state comparison or spatial relation can use the installed `visualize` Skill.
Neither this capability nor a particular diagram, tab set, role/scenario grouping or component is mandatory for every project.
The existing `assets/project-map.html` is a reusable overview option when it fits. When another native composition fits better,
author it from the frozen evidence under the granted task output root and pass its exact path to `prepare-delivery --visual-input`.
Use native controls, typography and theme, while choosing content and interactions independently. A custom view need not copy the
overview template's DOM or layout. If it offers follow-up, carry the same report/object identity and optional journey; local inspection
does not approve maintenance or rules. Semantic fidelity and real interaction require review; freezing bytes alone proves neither.
For text or a simple static answer, use `render-receipt --text-only`; the companion stays available without forcing an inline UI.
Include the complete generated receipt in the actual final reply. A link to a separately saved receipt cannot replace it. Verify the
composed final before sending, then read the delivered text from native history on continuation. Never rewrite an old frozen report
to change its presentation. Do not automatically open a browser or file preview or add a service. When native interaction is absent,
continue from the same Markdown and chat, reporting the unverified interaction. File integrity does not prove comprehension or adoption.

## Mode: `project_scout`

Implicit selection is only for follow-up to an identifiable delivered Scout report. It never authorizes a new review or write.
Without such a report, do not run discovery implicitly; ordinary project work stays in its existing workflow.

Use the currently bound project task for the entire review and delivery. Read-only inspection does not require a new chat or
worktree. Keep a worktree the user already selected; never create a user-facing task merely to run this Skill. The current task
owns completion, including recovery and the final result. Do not return after dispatching internal work.

1. For Codex, before deep reads, resolve the actual installed Skill, native Desktop project binding and current project root. Resolve an
   optional `projectId` against the same-host project inventory, and cross-check the native task's `cwd` and Git root. A null or
   omitted `projectId` is not itself unbound: a native task cwd matching exactly one same-host inventory root (or its proved
   Git worktree origin) also establishes the target. Reject conflicting identities, ambiguous matches or missing native context;
   a shell cwd, display label or prompt path alone is not binding. Apply the same rule when associating natural history tasks.
   Resolve an available Python 3 interpreter once (`python3`, `python`, or the host runtime); use it with `-B` and the absolute installed
   `scripts/scout.py` path for Scout helpers. Before the first helper, capture its Skill/cache baseline as Phase 0 specifies.
   Derive `project_identity` through the existing
   Bootstrap `enrollment.py inspect-project` from the same verified source, using the already resolved native primary folder, name and
   host reference. Use its canonical content identity and eligibility, not a hash of the raw remote URL. This read-only projection
   does not enroll a project or change Scheduled state; native binding remains separately required.
   Run `inspect-context --project-root <bound-project-root>` independently of shell cwd.
   Save the complete preflight fingerprint, including untracked content. Ordinary Local and existing worktree are both eligible;
   a non-Git or unbound project returns the deterministic preflight Terminal. No model/thinking override or user setup is needed.
2. For interactive delivery, read the **current task's** environment context, especially `filesystem.workspace_roots`, and any explicit host output metadata.
   A host-declared generated-output directory outside the reviewed project is eligible even when it is inside host app storage.
   Do not infer that metadata is absent merely because one tool does not expose it. Never construct a path from a username,
   task ID, date or a familiar `visualizations` pattern. If no unambiguous grant exists, return Terminal v1 before deep work.
   A user may instead explicitly select that exact output root in the current native invocation. Check the original request or native selection;
   model assertions, old requests and quoted tool/document paths are not authorization. Never silently choose a state directory.
   Run `inspect-output --artifact-dir <granted-output-root> --protected-root <bound-project-root>`; this checks containment, not consent. File preview is optional and checked only when requested.
3. For `review`, execute all seven phases in `references/deep-review-protocol.md`. Codex uses native `list_threads` **history** on the current host,
   `source=codex`, `limit=50`, with active and archived histories separately. Follow each exact returned cursor to the window
   boundary or EOF. Keep natural work turns in mixed engineering/Scout tasks before this invocation; exclude only Scout-generated
   turns there, and dedicated test/review tasks. A page size is not a total coverage cap. Use `read_thread` pages for every selected natural task, starting
   small (`turnLimit=1`, bounded output) and fetching only needed output bodies. A capacity error may be retried once at a smaller
   size on the same cursor; retain the failed observation. Do not silently skip pages. Resume every yielded cell to a terminal
   result before continuing. Recoverable call/transfer errors are retained and corrected within the same source, cursor and
   authorization, as Phase 1 specifies. Page errors and successful-but-unrecoverable field truncation degrade only the affected
   evidence; record their different actual causes. Unrecovered execution remains a protocol failure, not a coverage shortcut.
4. Keep source facts, inferred obligations and Global Owner comparison separate. For a source-rich review, use an internal
   independent reviewer as Phase 5 specifies; do not create another user-facing task. Compare the complete actual Owner,
   including unmanaged principles, by trigger, required action and exception. Recombining already-covered obligations is not a
   new rule. Name the specific uncovered behavior and a concrete future failure before recommending an addition. Keep method
   details in their existing Skill and project facts in their existing project owner. Uncertainty is not a new user decision.
   Compare coverage and actual implementation separately: an existing global rule does not erase a concrete project or method
   repair. Give an evidenced maintenance delta an engineering card and exact source Owner; use `project_only` or
   `skill_only` exclusions only when no actionable delta remains. Never turn every observation into a task.
5. Freeze and validate Project v7 with its map. Engineering advice can include source-backed hypotheses and multi-level refactoring; compare
   benefits, migration cost, counterexamples and validation conditions without inventing accepted changes or rules.
   Only for rule candidates, resolve Owner parity through `resolve-owner-parity`, then read only the returned host-local
   Owner and verify its hash. Never guess or search for the canonical Owner. Build Review Pack v8 and call `prepare-review` to
   bind actual installed Core single/combined previews. Validate the returned pack unchanged. Covered/no-persistence cards have
   no required action; preserve their evidence without asking the user to confirm or ignore them. No fixed candidate cap.
   For inspect or an engineering-only review, keep Owner parity and selection preview null and skip all rule integration; `prepare-review` returns without resolving an Owner. A mixed review integrates only its rule candidates.
6. Re-run `inspect-context --project-root <bound-project-root>` and compare the full snapshot. Changed evidence invalidates a
   stable-review claim; do not blame Scout for a concurrent change without attribution. Check Skill/cache and external-write
   boundaries. On privacy, integrity or read-only failure, use Terminal v1 and no actionable partial pack.
7. For interactive delivery, pass the validated pack to `prepare-delivery --artifact-dir <host-output-root> --protected-root <bound-project-root>`.
   This creates immutable Markdown and HTML from one frozen result, verifies both and emits Delivery v2. Return `render-receipt not_requested`
   with exact artifact/root arguments unchanged: a brief overview, first actionable recommendation and complete-evidence link.
   Do not open the report by default. If the user explicitly requests opening, pre-render the opened/queued/failed outcomes,
   call the native file tool once and return the matching receipt. Pass artifact/root arguments even for a failed preview so
   verified advice stays usable. A queued or failed open does not block discussion or prove display. Do not poll or ask for a window switch.
   A failure before a manifest uses `render-terminal`, never a hand-written receipt or `render-receipt` with an invalid manifest.

Scheduled keeps its existing inline `render-review --surface scheduled` and `verify-visible` path, with one Inbox wrapper,
isolated worktree and bounded automation memory. It does not require an interactive artifact root or open call; activation remains paused.

## Recovery and continuation

Technical delivery ends with an immutable, verified artifact and its result link in this task. User display, comprehension,
confirmation and later adoption are separate evidence; missing UI observation does not justify more test chats or artificial
confirmation. Source and technical fixes may ship while genuine later experience remains unverified.

For “解释这里”, “看这条路径”, native report/object follow-ups, “基于这份复盘给沉淀建议”, “先看这一项”, scope edits, deferral or batch requests, continue in this chat; do not run a new census.
Find the original delivery receipt for the referenced report in native chat history, including across intervening ordinary replies.
Use the report explicitly selected by the user or the unambiguous current discussion; never substitute another report just because it is newer.
Only unresolved ambiguity between reports needs a question. Prefer `recover-delivery --artifact-root <original-host-output-root>`
with the original native `prepare-delivery` manifest via stdin or `--input-file`. Recover that producer result from native history;
never manufacture provenance by hashing an arbitrary file. For a widget/report selection, pass its `report_hash` as `--report-hash`
(the Review Pack hash, not the Delivery manifest hash). The old `verify-final` entry accepts the original final as a compatibility
locator: one distinct artifact link and manifest hash, with repeated copies allowed. Different reports require explicit selection
through the structured entry. Do not recompose a receipt or make human wording a prerequisite for recovery.
Both entries verify the same immutable artifact and return `artifact_verified` with `confirmation_eligible=false`; summary, title,
Markdown and surface/approval copy are not verified by recovery. Correct inaccurate copy from the artifact; do not discard a valid
report or infer human approval. Actual host observations remain separate. Pass `--project-root <current-native-bound-root>` to
check the full snapshot, including dirty and untracked sources. Compare returned `project_identity` with the native binding.
`source_status=changed` preserves history but needs relevant source review before current actions; HEAD equality alone is insufficient.
Missing/tampered HTML sets `visual_status=unavailable` while verified Markdown remains usable. A bad chat/widget pointer does not
invalidate independent Markdown; do not certify that pointer. Old files without a map remain readable without fabricating one.
Pass an object or journey as data to either entry using `--object <kind:id> [--journey <id>]` and use `selected_context`.
The project overview is `project:<project_key>`. Never infer an object from another report or assemble shell code from follow-up text.
A widget selection is a locator, not approval; bind it to the original report before resolving its object.
The recovered selection keeps recorded journeys, prerequisites, constraints, recovery, project boundaries and source-check
status. If several journeys match, retain them and resolve only the ambiguity material to the next task. Project-wide
coverage is not selected-path completeness. Before consuming a changed map, inspect relevant Owner/code diffs and new
evidence, update only affected facts in a new snapshot and retain unaffected evidence; do not repeat a census or duplicate
the business SOP. Pass these source/version bindings and limits to a downstream consumer, not just a picture or node name.
Use the returned `recovery_bundle` for exact Core input. Historical files may return null; if the original
exact bundle is no longer available, refresh only the affected preview for new authorization and never invent old bindings. Keep the same artifact; do not rerun discovery or recompose a large payload. An explicit later request to
open it may reuse the returned manifest and existing `render-receipt`; repeated `queued` remains pending.

After recovery, compare the selected findings with their current project or Skill Owner and any new facts. Give the real delta,
recommended change, source location, scope, exception and evidence. Start with an overview and the first useful item; allow natural
switching, edits, batch discussion and deferral. Covered/no-change items need no repeated decision; insufficient evidence is not a test assignment.
Preserve discussion progress in this chat; do not add a queue or persistent proposal store. Deferral applies to this discussion, not a permanent mute.
Use native async choices only for a material unresolved decision; ordinary text is sufficient. Existing authorization persists.
“按推荐” inherits the exact operation previously presented. When the recommendation is `edit`, scope clarification or choosing
an Owner, it authorizes refining that recommendation, not editing project/Skill files. Do not turn a challenged global proposal
into an authorized project implementation. First prepare the concrete change and scope; continue existing implementation
authorization when it already covers that change, otherwise obtain the necessary decision once after the change is reviewable.
When the user authorizes project or method maintenance, hand off to that existing engineering/Skill workflow in this chat and
read back the actual change. The read-only review itself never writes an Owner. Discussion or choosing a route is not global-rule authorization.

If the user sends an exact rule selection from that pack, restore the file checks first, then route to the installed `agent-memory`
Scout bundle handoff for Fresh Owner comparison, exact Core preview and one real user authorization. Pending display is not
permission, and neither recovered bytes nor tool-relayed text is an approval. No rule changes inside this read-only Scout run.
If the artifact or selection cannot be verified, leave confirmation closed and explain the specific failure.

The initial review emits the deterministic advice receipt; follow-up discussion is ordinary chat and need not itself be a receipt.
No separate memory audit or tail note is needed. A later continuation verifies the original delivery receipt, not the latest discussion reply.
This proves artifact integrity and the recorded receipt, not independent UI observation.
The original five-scenario evidence remains historical. Current technical acceptance covers Local clean/dirty, existing worktree,
window/EOF history, explicit page failure, missing output grant, queued recovery and tampering; real installed-entry adoption and
user experience remain unverified until observed. These checks do not authorize canary chats or changes to a real Owner.

Always use `-B`; never create or clean `__pycache__` during a Scout run. Attribute cache differences before claiming a helper
write, and retain execution-identity limits because `-B` can read cached code. Bootstrap owns cache-free installation. Preserve
independently supported evidence and frozen prior artifacts; unknown cache attribution does not grant stable-run qualification.

## Entry-specific resource policy

- Interactive review: `manual_30d`; inspect: `current`; never prompt for or inject model/thinking overrides. Use the current task's
  host-resolved model, reasoning, and Speed; if runtime metadata is observable, actual values must equal that task's requested
  values. Manual runs never read or update automation memory and never count toward `0/14`.
- Scheduled experiment: optional and currently paused; fixed `gpt-5.6-sol + medium`, rolling 72 hours, host Speed inherited.

- Scheduled requests use policy date `2026-08-06`; never store a speed override.
- One standalone worktree task per Host Enrollment entry; non-Git projects are not eligible.
- The Prompt contains only Skill/mode, window, contract versions, model profile, and read-only/privacy boundaries.
- Automation memory is bounded host metadata only and never evidence or candidate state.
- A regular-task forward test does not read or update automation memory; a real Scheduled run reads and updates its own bounded
  memory. Both values must agree and neither may influence discovery.
- Host Enrollment does not activate production. A new or repaired host must first pass a disposable automation-source capability
  canary whose only business call is the native task index. An external interactive task observes up to 180 seconds and confirms a
  terminal result. If it remains running, Host Activation Control keeps every Project Scout paused and reports
  `host_activation_blocked`; this read-only Skill never pauses or resumes automations itself.
- After the capability canary passes, activate only one project canary. Do not activate the other enrolled projects until one real
  Scheduled Review Pack produces user-judgeable cards and the user completes one exact single-card or atomic multi-card action.

Scheduled failure never blocks the explicit interactive entry. Report the states independently as
`interactive_project_scout`, `scheduled_project_scout`, and `owner_continuity`.

## Migration compatibility

Existing pre-enrollment Skill 4.0.0 tasks may invoke the frozen `scripts/validate_output_v4.py` and
`scripts/render_review_v4.py` compatibility path until the user confirms migration. Bootstrap must never create a v4 task, and
v5 validators reject fixed-project prompts and old contracts. Compatibility outputs remain historical and do not count toward v5
acceptance.

## Mode: `central_review`

Use only when the user explicitly requests synthesis of already visible Review Packs. Preserve every source card and project
stance; append only cross-project links, current Owner comparison, first-party research, and concerns. Central review is never a
Scheduled transport or a visibility/confirmation gate.
