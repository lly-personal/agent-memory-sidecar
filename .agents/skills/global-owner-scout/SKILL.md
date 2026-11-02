---
name: global-owner-scout
description: Run an explicitly requested, evidence-first, project-read-only 30-day review in the currently bound Codex project and deliver a complete Chinese Review Pack through a task-scoped host artifact. Use only when the user invokes $global-owner-scout or for a separately configured Scheduled experiment; never trigger for ordinary project work.
---

# Global Owner Scout

## Contract

- Skill version: `5.11.0`
- Project result: `global_owner_scout_project_v5`
- User review: `global_owner_scout_review_pack_v6`
- Manifest-free terminal: `global_owner_scout_terminal_v1`
- Preflight snapshot: `global_owner_scout_preflight_v1`
- Mode: `project_scout`; interactive-only `central_review` remains optional.
- Read [references/contracts.md](references/contracts.md) and execute
  [references/deep-review-protocol.md](references/deep-review-protocol.md) completely.

This Skill creates project-read-only review drafts. It never creates proposals, approval refs, Owner mutations, project files,
database rows, commits, pushes, or external-system writes. Its only output write is an immutable Review Pack artifact under the
current task's explicit host-generated output root, outside the reviewed project and every capability/state root not explicitly
granted as that task output surface. The formal product entry is the exact explicit invocation
`$global-owner-scout 复盘当前项目` in the currently bound target Git project task. It always uses `manual_30d`, never reads automation memory,
and never asks the user to provide resource settings. The Scout uses the current task's host-resolved model/reasoning settings and records observable requested/actual values; it supplies no override. The current Desktop project binding is authoritative; no Prompt may contain a
project name, path, project ID, candidate hint, or the deep-review procedure.

## Mode: `project_scout`

Use the currently bound project task for the entire review and delivery. Read-only inspection does not require a new chat or
worktree. Keep a worktree the user already selected; never create a user-facing task merely to run this Skill. The current task
owns completion, including recovery and the final result. Do not return after dispatching internal work.

1. Before deep reads, resolve the actual installed Skill, native Desktop project binding and current project root. Resolve an
   available Python 3 interpreter once (`python3`, `python`, or the host runtime); use it with `-B` and the absolute installed
   `scripts/scout.py` path for every helper. Run `inspect-context --project-root <bound-project-root>` independently of shell cwd.
   Save the complete preflight fingerprint, including untracked content. Ordinary Local and existing worktree are both eligible;
   a non-Git or unbound project returns the deterministic preflight Terminal. No model/thinking override or user setup is needed.
2. For interactive delivery, read the **current task's** environment context, especially `filesystem.workspace_roots`, and any explicit host output metadata.
   A host-declared generated-output directory outside the reviewed project is eligible even when it is inside host app storage.
   Do not infer that metadata is absent merely because one tool does not expose it. Never construct a path from a username,
   task ID, date or a familiar `visualizations` pattern. If no unambiguous grant exists, return Terminal v1 before deep work.
   Run `inspect-output --artifact-dir <host-output-root> --protected-root <bound-project-root>` and check file-preview availability.
3. Execute all seven phases in `references/deep-review-protocol.md`. Use native `list_threads` **history** on the current host,
   `source=codex`, `limit=50`, with active and archived histories separately. Follow each exact returned cursor to the window
   boundary or EOF. Keep natural work turns in mixed engineering/Scout tasks before this invocation; exclude only Scout-generated
   turns there, and dedicated test/review tasks. A page size is not a total coverage cap. Use `read_thread` pages for every selected natural task, starting
   small (`turnLimit=1`, bounded output) and fetching only needed output bodies. A capacity error may be retried once at a smaller
   size on the same cursor; retain the failed observation. Do not silently skip pages. Resume every yielded cell to a terminal
   result before continuing. Explicit terminal failures degrade the affected evidence; abandoned execution is a protocol failure.
4. Keep source facts, inferred obligations and Global Owner comparison separate. For a source-rich review, use an internal
   independent reviewer as Phase 5 specifies; do not create another user-facing task. Compare the complete actual Owner,
   including unmanaged principles, by trigger, required action and exception. Recombining already-covered obligations is not a
   new rule. Name the specific uncovered behavior and a concrete future failure before recommending an addition. Keep method
   details in their existing Skill and project facts in their existing project owner. Uncertainty is not a new user decision.
5. Freeze and validate Project v5, resolve Owner parity through `resolve-owner-parity`, then read only the returned host-local
   Owner and verify its hash. Never guess or search for the canonical Owner. Build Review Pack v6 and call `prepare-review` to
   bind actual installed Core single/combined previews. Validate the returned pack unchanged. Covered/no-persistence cards have
   no required action; preserve their evidence without asking the user to confirm or ignore them. No fixed candidate cap.
6. Re-run `inspect-context --project-root <bound-project-root>` and compare the full snapshot. Changed evidence invalidates a
   stable-review claim; do not blame Scout for a concurrent change without attribution. Check Skill/cache and external-write
   boundaries. On privacy, integrity or read-only failure, use Terminal v1 and no actionable partial pack.
7. For interactive delivery, pass the validated pack to `prepare-delivery --artifact-dir <host-output-root> --protected-root <bound-project-root>`.
   This creates the single immutable file, verifies its bytes and emits Delivery v1. Pre-render opened, queued and failed receipts
   with `render-receipt`, passing exact artifact/root arguments for opened or queued. Open the same artifact once using the native
   file tool. Return the appropriate deterministic receipt unchanged; never copy the full pack into chat or invent an opened state.
   A host returning `queued` has accepted the request, not proved a displayed file. Do not poll or ask the user to switch windows.
   A failure before a manifest uses `render-terminal`, never a hand-written receipt or `render-receipt` with an invalid manifest.

Scheduled keeps its existing inline `render-review --surface scheduled` and `verify-visible` path, with one Inbox wrapper,
isolated worktree and bounded automation memory. It does not require an interactive artifact root or open call; activation remains paused.

## Recovery and completion

Technical delivery ends with an immutable, verified artifact and its result link in this task. User display, comprehension,
confirmation and later adoption are separate evidence; missing UI observation does not justify more test chats or artificial
confirmation. Source and technical fixes may ship while genuine later experience remains unverified.

On continuation, read the actual previous final and run `verify-final --artifact-root <original-host-output-root>` with that final
on stdin. It reconstructs and returns the manifest from the original file, verifies direct-child containment, read-only bytes and
all card/action hashes. Use the returned `recovery_bundle` for exact Core input. Historical files may return null; if the original
exact bundle is no longer available, refresh only the affected preview for new authorization and never invent old bindings. Keep the same artifact; do not rerun discovery or recompose a large payload. An explicit later request to
open it may reuse the returned manifest and existing `render-receipt`; repeated `queued` remains pending.

If the user sends an exact selection from that pack, restore the file checks first, then route to the installed `agent-memory`
Scout bundle handoff for Fresh Owner comparison, exact Core preview and one real user authorization. Pending display is not
permission, and neither recovered bytes nor tool-relayed text is an approval. No rule changes inside this read-only Scout run.
If the artifact or selection cannot be verified, leave confirmation closed and explain the specific failure.

After the host open, emit only the pre-rendered receipt. No separate memory audit or tail note is needed. A later controller may
read the actual final with `verify-final`; it proves artifact integrity and the recorded receipt, not independent UI observation.
The original five-scenario evidence remains historical. Current technical acceptance covers Local clean/dirty, existing worktree,
window/EOF history, explicit page failure, missing output grant, queued recovery and tampering; real installed-entry adoption and
user experience remain unverified until observed. These checks do not authorize canary chats or changes to a real Owner.

Python bytecode caches are external writes. Always use `-B`; never create or clean `__pycache__` during a Scout run. Bootstrap owns
cache-free installation. Preserve all independently supported evidence under degraded coverage and all frozen prior artifacts.

## Entry-specific resource policy

- Interactive entry: fixed `manual_30d`; never prompt for or inject model/thinking overrides. Use the current task's
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
