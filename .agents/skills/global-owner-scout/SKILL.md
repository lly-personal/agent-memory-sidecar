---
name: global-owner-scout
description: Run an explicitly requested, evidence-first, project-read-only 30-day review in the currently bound Codex project and deliver a complete Chinese Review Pack through a task-scoped host artifact. Use only when the user invokes $global-owner-scout or for a separately configured Scheduled experiment; never trigger for ordinary project work.
---

# Global Owner Scout

## Contract

- Skill version: `5.6.0`
- Project result: `global_owner_scout_project_v4`
- User review: `global_owner_scout_review_pack_v4`
- Mode: `project_scout`; interactive-only `central_review` remains optional.
- Read [references/contracts.md](references/contracts.md) and execute
  [references/deep-review-protocol.md](references/deep-review-protocol.md) completely.

This Skill creates project-read-only review drafts. It never creates proposals, approval refs, Owner mutations, project files,
database rows, commits, pushes, or external-system writes. Its only output write is an immutable Review Pack artifact under the
current task's explicit host-generated output root, outside the reviewed project and every capability/state root not explicitly
granted as that task output surface. The formal product entry is the exact explicit invocation
`$global-owner-scout 复盘当前项目` in a new independent worktree task. It always uses `manual_30d`, never reads automation memory,
and inherits that task's model, reasoning, and Speed. The current Desktop project binding is authoritative; no Prompt may contain a
project name, path, project ID, candidate hint, or the deep-review procedure.

## Mode: `project_scout`

1. Derive the current project label, host project reference, primary folder, Git eligibility, and content identity from the bound
   Desktop task. Record only privacy-safe opaque identity fields in the result.
2. Capture HEAD, status, staged/unstaged fingerprints and external-write baseline. Resolve canonical/local global Owner hashes only
   through `scripts/resolve_owner_parity.py`; never search for or guess a canonical path.
3. Execute all seven deep-review phases. Enumerate same-project tasks with one native index request at limit 50. If the tool yields
   a cell, resume that exact cell to a terminal result before any other index call. Page every selected natural task to the window
   boundary or EOF with native `read_thread` requests capped at `turnLimit=10` and `maxOutputCharsPerItem=20000`; report only
   terminally proven complete, bounded, degraded, or failed coverage.
4. Build every qualified Project Card in Simplified Chinese plus its abstract Rule Projection. Freeze the full card in
   `project_claim_hash`; no global comparison may rewrite project semantics.
5. Validate `global_owner_scout_project_v4`, then run `python -B scripts/resolve_owner_parity.py`. When parity is `matched`, read
   the active host-local global Owner and verify its bytes against the returned hash; the equal canonical hash proves the canonical
   bytes are identical without disclosing or guessing its physical path. For `drift/unavailable`, mark the Owner comparison
   incomplete, remove confirmation, and never use a project-root fallback. Build one integration preview per card and validate
   `global_owner_scout_review_pack_v4`. Every confirmable card must carry its deterministic `selection_token` from the current
   canonical source hash and exact integration preview.
6. Re-capture read-only proof. Any project mutation, privacy leak, integrity failure, or unauthorized external write fails closed.
7. From the Skill `scripts` directory, execute every Python helper with bytecode writes disabled (`python -B`). For the formal user
   entry, resolve an explicit host-generated output root from the current task context and require it to be outside the reviewed
   project. If none exists, return `interactive_host_blocked`; do not guess a temp, project, or arbitrary Codex-home path. A host may
   physically place its declared output root inside host-managed app storage; the explicit task grant, not the path prefix, is the
   authority. Pass the validated
   Review Pack to `prepare_delivery.py --artifact-dir <host-output-root> --protected-root <project-root>`. This creates and reads
   back the exact renderer bytes, verifies them, and returns `global_owner_scout_delivery_v1` without an absolute path.
8. Before the final host call, use the manifest with `prepare_delivery.py --render-receipt open_succeeded --artifact-path
   <host-output-root>/<artifact_name> --artifact-root <host-output-root>` and also pre-render the `open_queued` receipt with the same
   artifact arguments plus the path-free `open_failed` receipt. This step
   rechecks the artifact root, read-only state, bytes, hash and visible-output conservation. Recheck the project/Skill read-only baseline,
   then open the artifact in the current Codex task with the host file-preview tool. This open is the final tool call. On success,
   return the pre-rendered compact success receipt unchanged only for an explicit terminal opened/success state. An exact host
   `queued` result returns only the content-bound queued receipt with the artifact link, `surface_observation=open_queued` and
   `confirmation_eligible=false`; it is externally verifiable as `surface_pending` but does not qualify the host. `pending`, missing,
   failed, or unobservable results use only the pre-rendered blocked receipt. Never copy
   the full Review Pack into chat, dynamically import the renderer, hand-write replacement Markdown, append a tail note, or expose
   raw JSON as the user interface. The paused Scheduled experiment retains its existing renderer/verifier path.

The interactive host artifact open is the final tool call. After it returns, invoke no other Skill or tool and emit no independent
memory audit. A higher-level Agent Memory requirement is satisfied by the artifact cards and compact receipt; it remains silent.
An external controller task—not the Scout itself—must read the actual final and run `prepare_delivery.py --verify-final
--artifact-root <host-output-root>` before any production claim. `surface_pending` proves artifact discoverability and integrity only;
only `surface_observed` can count. Until three real worktree canaries pass, report
`interactive_project_scout=production_unproven / interactive_host_blocked`.
Before creating a canary, the controller must bind the formal entry's actually installed Scout Skill version and content identity.
A worktree containing newer Skill source does not make that source the runtime consumer. Any task that resolves a different Skill
version, omits Delivery v1, or returns the legacy inline Review Pack is `ineligible / runtime_skill_identity_mismatch` and does not
count toward the three canaries.

Python bytecode caches are external writes. Do not import helper modules through an inline interpreter without `-B`, and do not
create or clean `__pycache__` during a Scout run. Any new cache is a read-only failure; installation excludes caches atomically.

Coverage degradation is visible and cannot hide cards independently supported by Owners, ADRs, Git, tests, or acceptance. User
confirmation remains the only path to persistence. The exact action semantics and output schemas are in `contracts.md`.

## Entry-specific resource policy

- Interactive entry: fixed `manual_30d`; inherit the current task model, reasoning, and Speed. If runtime metadata is observable,
  actual values must equal requested values. Manual runs never read or update automation memory and never count toward `0/14`.
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
