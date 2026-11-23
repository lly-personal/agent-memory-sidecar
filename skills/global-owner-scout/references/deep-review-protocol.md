# Deep Review Protocol

## Evidence posture

Session content discovers leads; current project Owners, ADR/specs, Git, tests, runtime facts, and acceptance corroborate them. Summaries are never proof. Missing Session access is a coverage limitation, not proof that no learning exists. Keep facts, inferences, and unproven claims separate.

## Phase 0: current-task context

- Before deep reads, run `python -B scripts/scout.py preflight-summary --host codex|pi|claude|antigravity --purpose review|inspect` for deterministic contract versions and command order without reading files or Git.
- Capture the user-level Skill directory bytecode-cache baseline before the first helper. Always pass `python -B`; attributable helper cache writes fail read-only validation, while missed initial baselines leave the past window unverified without blocking unaffected reads. Never delete caches or replace baselines.
- Resolve native project binding, installed Skill, explicit external output grant (`filesystem.workspace_roots`, host output metadata, or explicit current-turn user selection), and Python 3 runtime once. Run `inspect-context --project-root <bound-project-root>` (never infer project from helper `cwd`) and `inspect-output --artifact-dir <granted-root> --protected-root <bound-project-root>` before deep work. Missing binding, Git eligibility, or output grant returns `Terminal v1` immediately.
- Pi/Claude/Antigravity use `inspect-native` with live `ExtensionContext` / `system/init` / `claude_skill_substitution` / `antigravity_runtime_info` (never `cd` to hide startup-vs-current Git root drift), Project v8 / Pack v9 (`degraded`, `observed_only` native scopes), and `observePiTurn`/`observeClaudeTurn` where applicable (active-turn snapshots remain usable).
- Scheduled (paused) retains isolated worktree + inline/Inbox verification and needs no artifact root or file preview.

## Phase 1: identity and task census

1. Derive `project_identity` (`enrollment.py inspect-project`) and freeze the 30-day window from Desktop binding (`projectId` or unique native `cwd` / worktree origin match against same-host inventory Git root; reject conflicting non-null IDs or ambiguous matches).
2. Codex lists `list_threads(source=codex, limit=50)` across `active` and `archived` separately to the proved window boundary or EOF (`limit=50` is per-page, never a total cap). Stop early only when page ordering proves all relevant entries precede window start. Deduplicate task IDs and record `index_pages_read` + `index_terminals.active/archived`.
3. Resume every yielded cell to termination before advancing. Retain recoverable call/transfer errors and retry within the same source, cursor, and authorization; unrecovered cells, lost provenance, or interruptions fail with `execution_protocol_failed`. Explicit index terminal failures record `native_index_terminal_failure`.
4. Associate natural tasks by native identity or proved worktree origin; exclude dedicated Scout, test, Scheduled, and delegated tasks. Keep prior natural work turns in mixed engineering/Scout chats (exclude Scout-generated turns). Page selected tasks with `read_thread` starting at `turnLimit=1` and bounded output:
   - **Clipped successful page**: retain it and re-read the same cursor with outputs included and a larger valid per-item allowance (reducing turns/page if needed). Compare stable item IDs/truncation flags and retain both observations. If fields stay unrecoverably clipped, record `native_thread_pages_terminal_failure` with the actual cause and unread scope (`degraded`), not a claimed native exception.
   - **Explicit capacity error**: retry the same cursor once with a smaller valid request; preserve earlier failed attempts even after recovery; if still rejected, record `native_thread_pages_terminal_failure` and unread scope.
5. `complete` requires both partitions at boundary/EOF and all selected tasks read without truncation; `bounded` means unfinished partition + all selected tasks read; `degraded` exposes explicit failures or unrecoverable truncation. Remaining pages or imported bytes are work to continue, not an external blocker. Never substitute transcript parsers, databases, or automation memory.
6. Retain every raw return object immediately in host code (`store("scout-native-page", result)` or native data writer) before summarizing. Feed thread pages through `import-history --input-file`, validate via `--input-file`, and query `describe-input` for required fields. Never transcribe large JSON via model chunks or split executable code to evade host size limits.

### Mechanical native-object transfer

Resolve `pythonExecutable`, `scoutScript`, `artifactRoot`, `projectRoot`, and `commandShell` (`posix` or `powershell`) from current runtime, loaded Skill, output grant, and native binding. All JSON passes through owned stdin (`--input-line` disables echo/line clipping temporarily and restores on exit/Ctrl-C/SIGTERM; on forced termination close the owned terminal):

```javascript
const page = load("scout-native-page");
if (page === undefined) throw new Error("native return object was not retained");
if (!["posix", "powershell"].includes(commandShell)) throw new Error("command shell is not resolved");
const quote = commandShell === "powershell"
  ? value => "'" + value.replaceAll("'", "''") + "'"
  : value => "'" + value.replaceAll("'", "'\\''") + "'";
const argv = [pythonExecutable, "-B", scoutScript, "capture-native", "--input-line",
              "--artifact-dir", artifactRoot, "--protected-root", projectRoot];
const cmd = (commandShell === "powershell" ? "& " : "") + argv.map(quote).join(" ");
let state = await tools.exec_command({cmd, tty: true, yield_time_ms: 1000, max_output_tokens: 1600});
if (Number.isInteger(state.session_id)) store("scout-capture-session", state.session_id);
let opening = state.output || "";
while (Number.isInteger(state.session_id) && !opening.includes('"status":"awaiting_native_object"')) {
  state = await tools.write_stdin({session_id: state.session_id, chars: "", yield_time_ms: 1000, max_output_tokens: 1600});
  opening += state.output || "";
}
if (!Number.isInteger(state.session_id) || !opening.includes('"status":"awaiting_native_object"')) {
  text(state);
  throw new Error("capture input did not become ready; retain the original object");
}
let result = await tools.write_stdin({session_id: state.session_id, chars: JSON.stringify(page) + "\n",
                                    yield_time_ms: 1000, max_output_tokens: 1600});
let output = result.output || "";
while (result.exit_code === undefined && Number.isInteger(result.session_id)) {
  result = await tools.write_stdin({session_id: result.session_id, chars: "", yield_time_ms: 1000, max_output_tokens: 1600});
  output += result.output || "";
}
if (result.exit_code !== undefined) store("scout-capture-session", null);
text({...result, output});
```

Verify actual completion and `raw_file` before sealing. Interrupted partial files mismatching bytes stay blocked (do not overwrite). Always read selected bounded passages for meaning (`capture-native` and counts never prove comprehension).

## Phase 2: project fact reconstruction

Reconstruct the engineering map (`project_map`: nodes, typed edges, connected directed journeys, coverage dimensions) before selecting lessons:
- Start from user outcomes (`goal -> actor & task -> action -> system effect -> downstream feedback -> recovery`), separating design, implementation, observed, inferred, and unknown claims plus counterevidence. Sidecar owns Scout implementation only — derive all labels, steps, owners, and environments from target evidence.
- Distinguish structural containment (`contains`), prerequisites/constraints (`depends_on`, `constrains`), execution handoffs (`handoff`), and state authority. Order journeys by main user outcome first, overviewing whole-system responsibilities before detail.
- For reuse/drift questions, trace natural task -> routing Owner -> formal tool -> actual consumer without launching evaluation batches or modifying target files.
- Choose presentation by explanatory fit (prose, tables, Mermaid, `visualize`, optional `assets/project-map.html`, or custom `--visual-input`), preserving native controls/contrast and keeping the core narrative legible without interaction. Presentation approval is independent of content depth. Follow the [presentation contract](https://github.com/lly-personal/agent-memory-sidecar/blob/main/docs/specs/interface.md#project-scout-global_owner_scout_project_v7).
- **`inspect` ends here**: skip Sessions (`session_coverage=null`), Owner resolution, and Core preview; freeze `view_ready` or `degraded`.
- **`review` reads the active knowledge floor**: build the six-category `evidence_sources` inventory (`sessions, owners, decisions, successes, failures, acceptance`). Inventory active behavior Owner headings/numbered clauses and accepted/reversed decisions first, then read full contexts in bounded non-truncated sections (the 30-day window never clips active knowledge). Whole-project depth requires covering the active behavior axioms floor; report unread gaps explicitly.

## Phase 3: contrastive causal review

Trace goals and constraints across boundaries, consumers, recovery, and decisions (comparing effective designs as well as failures). For engineering advice (including multi-layer refactoring/removal hypotheses, E1 allowed), compare retention, integration, replacement, and refactoring alternatives with benefit hypothesis, migration cost, counterexamples, owner, and validation conditions (`parent_card_id` optional, unbounded).

For each high-signal event answer:
- 用户反复纠正或解释了什么？
- 哪个后续失败推翻了先前的成功判断？
- 哪项设计或行为最终获得正式接受或真实验收？
- 哪条更早存在的行为原则可以避免重复成本？
- 哪些只有机制证据，哪些已经达到用户或产品结果？

Compare failed and successful paths under matching conditions; never infer causality from frequency alone.

## Phase 4: candidate exhaustion

Independently scan for repeated corrections, failed recovery, premature success, Owner drift, acceptance mistakes, durable decisions, and reusable methods **before** reading Global Owner wording. Never cap candidates or invent cards. Rule candidates require E2 (repetition, formal acceptance, or real acceptance) or E3 (2+ independent projects via opaque refs).

## Phase 5: counterevidence and two projections

- Challenge every rule candidate and projected obligation against legitimate successful paths under differing preconditions: separate accepted outcomes from one project's chosen means, narrow `When`, keep concrete `Skip`, and keep per-action exceptions distinct inside compound clauses.
- **Independent source-first review (source-rich reviews)**: Before freezing, run an internal reviewer subagent (never a user-facing task). Pass ONLY original sources and the source index/read gaps first (never drafts, Global Owner wording, or candidate answers) so it freezes an independent obligation inventory. Then pass the full map and draft cards to audit whole-path omissions, typed edge directions (`depends_on` = dependent -> prerequisite), intervention attribution (supervising continuation != human re-input), and per-obligation counterevidence. Fix evidenced defects and recompute hashes; if unavailable, record that limitation without calling self-review independent.
- **Two projections**:
  - `human_context`: Simplified Chinese, privacy-safe project terms, concrete event/cost/recommendation/before-after/strongest counterpoint.
  - `rule_payload` (rule candidates only): strip project names, paths, commands, local thresholds, IDs, raw dialogue, and private diagnostics; keep exact `When / Do / Skip`.
- **Routing**: Route project architecture to `project_owner`, repeatable methods (with entry, inputs, task, exceptions) to `skill` (see [method handoff SOP](https://github.com/lly-personal/agent-memory-sidecar/blob/main/docs/specs/interface.md#按需方法的维护与交接)), and only necessary cross-task increments to `global_agents`. Compare actual maintained implementations: concrete project/Skill maintenance deltas get `route_to_owner` cards (`route_supported`) even if global rules cover the rule text.
- Record all signals in `observations` and run a reverse omission check from the source index back to observations (checking partially covered compound clauses and keeping local-only rules distinct from cross-project behavior). Order actionable cards by evidenced impact and dependencies.

## Phase 6: freeze project semantics

Freeze `project_map` and `project_cards` together (`source_revision` = read-only HEAD, `observed_at` = freeze timestamp). Run `python -B scripts/scout.py seal-project --input-file <draft-project.json>` (or add `--output-file <new-file-in-granted-root> --artifact-dir <granted-root> --protected-root <bound-root>` for exclusive creation) to compute `normalized_evidence_hash` and `project_claim_hash` on every card and validate the Project result before Global comparison. `no_material_delta` requires nonempty evidenced observations within declared scope.

## Phase 7: integration and task-scoped delivery

- **Global integration (Codex rule candidates only; inspect & native/engineering-only skip)**: Run `python -B scripts/scout.py resolve-owner-parity`. With `matched` parity, read host-local Owner and verify its byte hash (never guess/search canonical paths or fall back to project `AGENTS.md`). Map every trigger/obligation/exception against the full Owner (including unmanaged principles); reworded/recombined clauses stay `already_covered_exact`. Add one integration preview per rule candidate; engineering cards use `discuss` with no rule actions/token.
- **Preflight recheck, preview & one-step delivery**: Re-run `inspect-context --project-root <bound-project-root>` and check Phase 0 cache baseline. Deliver via `python -B scripts/scout.py seal-delivery --artifact-dir <granted-root> --protected-root <bound-root> --host <host> --input-file <draft-pack.json>` (automatically computes `review_pack_hash`, runs Core `prepare-review` when Codex rule candidates are present, validates Review Pack, writes immutable Delivery v2 artifacts with built-in Mermaid map + collapsible card evidence, and renders the host-safe Chinese receipt; pass `--with-visual` only on Codex when interactive HTML drill-down is warranted). Open once only if requested. Never rewrite frozen artifacts or hand-write receipts; pre-manifest failures use `render-terminal` (`Terminal v1`). Scheduled keeps `render-review --surface scheduled` + `verify-visible --surface scheduled`.
- **Continuation from native page**: Select one exact non-truncated final without retyping using `python -B` and `(native_page_file, turn_id, out_file)`:

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

Pass `<out_file>` to `scout.py verify-final --input-file` with `--artifact-root` and `--project-root` (or prefer `recover-delivery` with the native manifest). Valid receipts never prove unclipped surrounding prose.

## Terminal meanings

- `interactive_entry_blocked`: preflight failed project binding or Git eligibility (`Terminal v1`, zero reads).
- `interactive_host_blocked`: no safe external task output root (`Terminal v1`, zero partial cards/confirmation).
- `ok`: at least one card + `complete|bounded` coverage.
- `degraded`: coverage gap (missing/failed/unrecoverably clipped Session or non-Session source gap); supported cards stay visible, Scheduled run does not count.
- `no_material_delta`: `complete|bounded` census with zero evidenced engineering or rule-candidate deltas.
- `failed`: `execution_protocol_failed`, privacy, integrity, mutation, required-source, render, or read-only failure (`Terminal v1`, zero cards).
- `output_budget_exceeded`: pack exceeds budget (`Terminal v1`, zero partial cards).
- Native `queued` preserves `surface_pending` (`artifact_verified` on recovery, `confirmation_eligible=false`); report display separately and never infer approval.
