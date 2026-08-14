---
name: global-owner-scout
description: Run an explicitly requested, evidence-first, read-only 30-day review in the currently bound Codex project and render a directly visible Chinese Review Pack. Use only when the user invokes $global-owner-scout or for a separately configured Scheduled experiment; never trigger for ordinary project work.
---

# Global Owner Scout

## Contract

- Skill version: `5.5.0`
- Project result: `global_owner_scout_project_v4`
- User review: `global_owner_scout_review_pack_v4`
- Mode: `project_scout`; interactive-only `central_review` remains optional.
- Read [references/contracts.md](references/contracts.md) and execute
  [references/deep-review-protocol.md](references/deep-review-protocol.md) completely.

This Skill creates read-only review drafts. It never creates proposals, approval refs, Owner mutations, files containing review
results, database rows, commits, pushes, or external writes. The formal product entry is the exact explicit invocation
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
   entry run `render_review.py --surface interactive` and `verify_visible_output.py --surface interactive`; for the paused
   Scheduled experiment use `--surface scheduled` for both. Pass the validated Review Pack on stdin, then return renderer bytes
   unchanged. Interactive output has no Inbox wrapper or 14-run copy; Scheduled output has exactly one final wrapper. Never
   dynamically import the renderer, hand-write replacement Markdown, append a tail note, or use raw JSON as the user interface.

The verifier is the final tool call. After it passes, invoke no other Skill or tool and emit no independent memory audit. A
higher-level Agent Memory requirement is satisfied by the already-rendered cards and receipt; it remains silent and may not append
text after the wrapper.

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
