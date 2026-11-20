---
name: global-owner-scout
description: Understand a project's goals, actors, scenarios and real workflows when asked for an overview; deeply review it when requested; continue from an identifiable delivered map. Give a brief explanation and any supported recommendation in the current chat, with complete evidence by link. Do not restart discovery for follow-ups or trigger for unrelated ordinary work.
---

# Global Owner Scout

## Contract

- Skill version: `5.19.10`
- Project result: `global_owner_scout_project_v7` (`native`: `global_owner_scout_project_v8`)
- User review: `global_owner_scout_review_pack_v8` (`native`: `global_owner_scout_review_pack_v9`)
- Delivery manifest: `global_owner_scout_delivery_v2`; Manifest-free terminal: `global_owner_scout_terminal_v1`; Preflight snapshot: `global_owner_scout_preflight_v1`
- Mode: `project_scout`; interactive-only `central_review` remains optional.
- Fast orientation: run `python -B scripts/scout.py preflight-summary --host codex|pi|claude|antigravity --purpose review|inspect` (deterministic JSON; reads zero files or Git).
- For a new review, read [references/contracts.md](references/contracts.md) and execute [references/deep-review-protocol.md](references/deep-review-protocol.md) completely. For follow-up, use Recovery and continuation below. Batch independent reads when supported and reuse acquired content.

This Skill creates **project-read-only** review drafts. It never creates proposals, approval refs, Owner mutations, project files, database rows, commits, pushes, or external writes. Its only writes are immutable review artifacts and captured native inputs under the current task's explicit host-granted or explicitly user-selected output root outside the reviewed project and unrelated state roots.

- Explicit entry: `$global-owner-scout 复盘当前项目` (`purpose=review`, `manual_30d`) or “看懂当前工程全貌” / “梳理当前工程的角色、场景和操作流程” (`purpose=inspect`, `current`) in the bound target Git project task.
- Interactive runs never read automation memory, never prompt for resource overrides, and record host-resolved requested/actual model/reasoning metadata as observed.
- Prompts never carry fixed project names, paths, project IDs, candidate hints, or the deep-review procedure.
- `inspect` reconstructs the current map from source evidence only (roles, entry, flow, handoffs, actual consumer, failure recovery); missing evidence stays `unknown`. A clear map with zero recommendations is valid. Mapping authorizes neither implementation nor runtime testing; later authorized follow-ups route through the project's existing workflow.

## Host lanes

- **Codex (default lane)**: Uses Project v7 / Pack v8, Desktop project binding (`projectId` or unique native task `cwd` match against same-host inventory Git root / proved worktree origin), `enrollment.py inspect-project` for `project_identity`, and `inspect-context --project-root <root>`. Reject conflicting IDs, ambiguous matches, missing native context, or shell-cwd/label-only binding.
- **Pi (`/skill:global-owner-scout`)**: Call read-only `global_owner_scout_context` first to export the live `ExtensionContext` (`native_context`) without reading history or granting artifact access. Forward it to `inspect-native`, check the current output grant via `inspect-output`, and for `review` invoke `capture_current, artifact_dir=<exact-granted-root>` (resolves Python 3.11+ once outside the workspace, checks identity/containment, seals the current SDK session). Read selected passages for meaning; other project sessions remain uncovered unless a separate qualified native source is available.
- **Claude (`/agent-memory-sidecar:global-owner-scout`)**: Native substitutions supply `${CLAUDE_SESSION_ID}`, `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`. Call `scripts/claude_native.mjs context` (with `--session-id`, `--project-root`, `--skill-dir`, `--plugin-root`, treating substituted paths strictly as single-quoted literal data, never shell code) from the inherited working directory — never `cd` to mask a startup vs. current Git tree mismatch (a child dir in the same tree is valid). For `review`, after verifying the output grant, call `claude_native.mjs capture` adding `--plugin-data` and `--artifact-dir` (plus optional `--source-session-id`, `--offset`, `--limit`). Missing pinned SDK `0.3.322` under plugin data fails closed without on-demand install.
- **Antigravity (`$global-owner-scout`)**: Native runtime metadata supplies `Conversation ID`, `App Data Directory`, and the bound project root. Call `python -B scripts/antigravity_native.py context --session-id <conversation-id> --project-root <bound-root> --app-data-dir <app-data-dir>` from the inherited working directory — never `cd` to mask a startup vs. current Git tree mismatch. For `review`, after verifying the output grant, call `python -B scripts/antigravity_native.py capture` adding `--artifact-dir <granted-root>` (restricted to the current bound session), which reads the local `transcript_full.jsonl` (or `transcript.jsonl`) directly into `import-history` without model transcription.
- **Pi, Claude & Antigravity scope**: All three use Project v8 / Pack v9 with `observed_only`/`degraded` native coverage, engineering advice only (no rule confirmation actions; Global Owner/Core preview stays Codex-bound), and separate reporting of package discovery, scoped capture, and natural semantic review. Respect host permission refusals without rerouting.

## Purpose and native presentation

- **Preserve native objects cleanly**: Before printing summaries, retain each native return object in host code (`store` / native data writer) or `capture-native --artifact-dir <granted-root> --protected-root <target-root>`. Feed raw thread pages through `scout.py import-history --project-root <native-source-root> --session-id <native-id> --artifact-dir <granted-root> --protected-root <target-root>` (stdin or `--input-file`). Never transcribe large JSON via model chunks or split payloads to bypass review size limits.
- **Schemas from validator**: Query `scout.py describe-input project|review` (Codex) or `native-project|native-review` (Pi/Claude) before writing semantic payloads.
- **Purpose split**:
  - `inspect` (“看懂当前工程全貌” / “梳理当前工程的角色、场景和操作流程”): reuse an identifiable current map if unchanged, else reconstruct the Phase 2 map; skip census, candidate search, Owner parity, and Core preview; freeze `view_ready` or `degraded`.
  - `review` (“复盘当前工程”): execute all 7 phases in `deep-review-protocol.md`, reconstructing the whole system before candidate selection. Both purposes explain the full system even with zero recommendations. Reuse/drift questions trace natural task -> routing Owner -> formal tool -> actual consumer without launching workflow-eval batches or editing cases.
- **Presentation**: Choose plain prose, tables, Mermaid, or the installed `visualize` Skill based on the project and question. `assets/project-map.html` is reusable when it fits; custom native views go through `prepare-delivery --visual-input`. For text/static answers, pass `--text-only` to `render-receipt`. Include the full generated receipt verbatim in the final reply (a standalone receipt link cannot substitute); never rewrite a frozen report to change presentation or auto-open a browser/preview.

## Mode: `project_scout`

Implicit selection applies only to continuing an identifiable delivered Scout report; otherwise never trigger discovery implicitly during ordinary project work. Keep the entire review and delivery inside the current bound task (Local or existing worktree; never spawn a new user-facing task).

1. **Preflight (before deep reads)**:
   - Capture the Skill directory bytecode-cache baseline (always run helpers with `python -B` via the resolved absolute `scripts/scout.py`; never create/delete `__pycache__`).
   - Resolve target project identity (`enrollment.py inspect-project` for canonical `project_content_identity_v1`, never raw remote URL hashing) and run `inspect-context --project-root <bound-root>` (or `inspect-native` for Pi/Claude). Missing binding or non-Git target returns `render-terminal` (`Terminal v1`) immediately.
   - Check the **current task's** `filesystem.workspace_roots`, explicit host output metadata, or an explicit user-selected external root in the current invocation (never construct paths from usernames, dates, task IDs, or old prompts) via `inspect-output --artifact-dir <root> --protected-root <project-root>`. If absent, return `Terminal v1` before deep work.
2. **History census (`review` only)**:
   - Execute all 7 phases in `deep-review-protocol.md`. Codex queries `list_threads` (`source=codex`, `limit=50`) across `active` and `archived` separately to the frozen 30-day window boundary or EOF (`limit=50` is per-page, never a total cap). In mixed engineering/Scout chats, retain natural turns before this invocation and exclude Scout-generated turns.
   - Read selected tasks with `read_thread` starting small (`turnLimit=1`). Recover clipped fields on the same source/cursor with a larger valid per-item allowance; retry rejected capacity errors with a smaller valid request. Retain both observations. Resume every yielded cell to termination. Page errors and unrecoverable field clipping degrade only affected coverage (`degraded`); unrecovered cells or lost provenance fail with `execution_protocol_failed`.
3. **Source-first review & Global comparison**:
   - Keep source facts, inferred obligations, and Global Owner comparison separate. For source-rich reviews, run an internal independent reviewer subagent per Phase 5 (never a new user task), auditing source-derived map paths, typed edge directions, and intervention attribution.
   - Compare candidates against the complete active Global Owner (including unmanaged principles) by trigger, action, and `Skip` boundary. Concrete project/Skill maintenance deltas get engineering/route cards with exact source Owners (`project_only`/`skill_only` only when no actionable delta remains); never turn every observation into a task.
4. **Freeze, preview & verify read-only state**:
   - Validate Project v7/v8 and its map. Only rule candidates call `resolve-owner-parity` and verify host-local Owner bytes against the returned hash (never search/guess canonical paths). Call `prepare-review` to bind installed Core single/combined `preview-bundle` receipts, then validate the final Review Pack unchanged. Inspect and engineering-only reviews keep `owner_parity` and `selection_preview` `null`.
   - Re-run `inspect-context --project-root <bound-root>` and compare full snapshots. Mismatches invalidate stability claims; privacy, integrity, or read-only failures emit `Terminal v1` with zero partial cards.
5. **Delivery**:
   - Pass the validated pack to `prepare-delivery --artifact-dir <granted-root> --protected-root <bound-root>`, creating immutable Markdown + HTML (Delivery v2). Default to `render-receipt not_requested` (overview, first actionable item, evidence link) without opening files automatically. Open once only on explicit user request, pre-rendering `open_succeeded`/`open_queued`/`open_failed` receipts with exact `--artifact-path`/`--artifact-root`. Pre-manifest failures always use `render-terminal`, never `render-receipt`.
6. **Scheduled (optional, paused)**: Keeps inline `render-review --surface scheduled` + `verify-visible`, one Inbox wrapper, isolated worktree, and bounded automation memory (`PAUSED / 0 of 14`).

## Recovery and continuation

Technical delivery ends with verified immutable artifacts and a result link; UI display, comprehension, confirmation, and later adoption are separate evidence. Do not create extra test chats or request artificial confirmation to manufacture UI evidence.

- **Follow-ups in chat**: For “解释这里”, “看这条路径”, widget/object clicks, “基于这份复盘给沉淀建议”, edits, deferrals, or batch choices, continue in the current chat without restarting discovery.
- **Structured recovery**: Locate the original `prepare-delivery` manifest (or legacy final receipt) for the referenced report in native history (never guess newest files or re-hash arbitrary files). Run `recover-delivery --artifact-root <orig-root>` (or `verify-final` for legacy final receipts), passing `--report-hash <review_pack_hash>`, `--project-root <bound-root>`, and `--object <kind:id> [--journey <id>]` (`project:<project_key>` for overview).
- **Recovery semantics**: Returns `artifact_verified` with `confirmation_eligible=false` (Markdown/chat copy never grants provenance or approval). Missing/tampered HTML sets `visual_status=unavailable` while verified Markdown stays usable. `source_status=changed` preserves historical findings while requiring inspection of affected Owner/code diffs before current actions.
- **Discussion vs. authorization**: “按推荐” advances concrete `edit`/scope/Owner proposals for review, never silent project/Skill writes; hand off approved project/Skill maintenance to the project's existing workflow and read back changes. For exact rule selections (`card_id@selection_token`), verify the artifact first, then route to the installed `agent-memory` bundle flow for Fresh Owner comparison, Core preview, and one real user authorization. Deferrals remain discussion-scoped without a permanent queue or mute store.
- **Bytecode discipline**: Always pass `-B`. Never delete `__pycache__` to hide cache diffs; keep cache baselines and execution-identity limits explicit.

## Entry-specific resource policy

- **Interactive**: `review` uses `manual_30d`; `inspect` uses `current`; host-resolved model/reasoning/Speed (actual == requested when observable); never reads/updates automation memory or `0/14`.
- **Scheduled (paused)**: `gpt-5.6-sol + medium`, rolling 72h, policy date `2026-08-06`, host Speed inherited, one standalone worktree task per Host Enrollment entry (non-Git ineligible), prompt restricted to Skill/mode/window/contracts/profile/boundaries. Bounded automation memory is never evidence. Host Enrollment requires a disposable `automation-source` capability canary (`list_threads(limit=50)` observed within 180s) before activating one project canary; non-terminal keeps all Project Scouts `PAUSED` (`host_activation_blocked`).
- **Independent reporting**: Report `interactive_project_scout`, `scheduled_project_scout`, and `owner_continuity` separately; Scheduled failures never block interactive use.

## Mode: `central_review`

Use only when explicitly requested to synthesize already-visible Review Packs. Preserve every source card and stance; append only cross-project links, current Owner comparison, first-party research, and concerns. Never a Scheduled transport or confirmation gate.
