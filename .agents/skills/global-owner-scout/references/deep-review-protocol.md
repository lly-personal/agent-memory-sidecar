# Deep Review Protocol 5.3

## Evidence posture

Session content discovers leads; current project Owners, ADR/specs, Git, tests, runtime facts, and acceptance corroborate them. A
summary is not proof. Missing Session access is a coverage limitation, not evidence that no learning exists. Keep fact, inference,
and unproven claim separate.

## Phase 1: identity and task census

1. Derive the project from the current Desktop binding. Compute opaque content/host identity; never trust a Prompt-supplied name,
   path, ID, or allowlist.
2. Call the native task index once with `limit=50`. Run its enclosing execution cell with a 60-second initial yield. If it returns a
   `cell_id`, call `wait` on that same cell up to two times, 60 seconds each, until terminal. Do not issue a second index call while
   the cell is running; `Script running` is not unavailable or timeout evidence.
3. An unresumed cell, invalid request, or interrupted execution is `failed / execution_protocol_failed`. Only an explicit terminal
   native error is `degraded / native_index_terminal_failure`; an explicit host cap is `bounded / native_index_host_cap`.
4. Associate tasks through native identity, current primary folder, or isolated-worktree origin. Exclude Scheduled, Scout, test, and
   delegated tasks. For every selected natural task, use native `read_thread` pages with `turnLimit=10` and
   `maxOutputCharsPerItem=20000` to the evidence-window boundary or EOF. Do not probe larger values. Any yielded execution cell
   follows the same resume-to-terminal rule.
5. Count discovered, in-window, selected, fully read tasks and pages; list exclusions and reasons. Use `complete` only with
   `native_index_completed + native_thread_pages_completed`; use `bounded` only with
   `native_index_host_cap + native_thread_pages_completed`. The current active-task snapshot is sufficient; record concurrent
   later changes and never wait for another project task to end.
6. Never use transcript storage, file bridges, automation memory, or databases as a Session substitute.

## Phase 2: project fact reconstruction

Read the project instruction chain, L1/L2/L3 or equivalent Owners, current-status Owner, relevant ADR/specs, windowed Git changes,
tests, failures, acceptance, and isolated snapshot. Recheck Session leads against these sources. Record each source's availability.

## Phase 3: contrastive causal review

For each high-signal event answer:

- 用户反复纠正或解释了什么？
- 哪个后续失败推翻了先前的成功判断？
- 哪项设计或行为最终获得正式接受或真实验收？
- 哪条更早存在的行为原则可以避免重复成本？
- 哪些只有机制证据，哪些已经达到用户或产品结果？

Prefer belief-before, observed contradiction, accepted change, and current boundary over generic lessons.

## Phase 4: candidate exhaustion

Search independently for repeated correction, failed recovery, premature success, Owner drift, acceptance-boundary mistakes,
durable design decisions, and reusable analysis methods. Do not read global-owner wording until this inventory is complete. Do not
cap candidates or manufacture cards. E2 requires repetition, formal acceptance, or real acceptance; E3 requires independent
evidence from at least two projects and names only opaque project refs.

## Phase 5: counterevidence and two projections

For every E2/E3 candidate find conflict, legitimate exception, project-only constraint, stronger existing Owner, and harmful
global interpretation. Require meaningful counterevidence and a concrete Skip boundary.

Create two projections from the same evidence:

- Human Context: Simplified Chinese, familiar privacy-safe project vocabulary, concrete event/cost/recommendation/before-after and
  strongest counterpoint.
- Rule Projection: remove project names, paths, commands, product labels, local thresholds, identifiers, raw dialogue, and private
  diagnostics; retain precise `When / Do / Skip` behavior.

Route project architecture to Project Owner, repeatable methods to Skill, cross-project behavior to global candidates, and weak or
risky ideas to no persistence.

## Phase 6: freeze project semantics

Create all complete Project Cards, validate privacy/Chinese narrative/evidence refs, compute normalized evidence hash, then compute
`project_claim_hash` over every semantic field. Validate the entire Project result before global comparison.

## Phase 7: integration and visible completion

Run `python -B scripts/resolve_owner_parity.py`. With matched parity, read the active host-local global Owner and verify its bytes
against the returned hash; the equal canonical hash proves identical canonical content without revealing its physical path. With
drift or unavailable parity, mark Owner comparison incomplete and remove confirmation. Compare semantics when proved, and use
official/first-party research only to support or challenge existing candidates. Add one integration preview per frozen card. Recheck count/order conservation,
privacy, and read-only fingerprints. Validate Project and Review Pack objects, then invoke `render_review.py` directly from the
Skill scripts directory with the Review Pack on stdin and the selected surface. Every Python helper uses `python -B`; never use a dynamic import or an
inline import that can create `__pycache__`.

If the resolver returns `unavailable`, remove confirmation and report the limitation. Never search upward, inspect the project-root
`AGENTS.md` as a substitute, or guess a canonical path from the current checkout.

Choose one surface before rendering: the explicit user entry uses `render_review.py --surface interactive` and
`verify_visible_output.py --surface interactive`; only the optional Scheduled experiment uses `--surface scheduled`. Pass the exact
renderer output to the matching verifier. Only a matching visible-body SHA-256, conserved cards/actions, surface-correct wrapper
count, no raw JSON, and no trailing text complete the run. Return the renderer bytes unchanged after verification. If the
renderer fails, tool output truncates, or the final bytes cannot be preserved, return `render_integrity_failed` or
`output_budget_exceeded`; never manufacture partial or replacement Markdown.

`verify_visible_output.py` is the final tool call. Do not invoke `agent-memory`, another Skill, another tool, or a post-render audit
after it passes. The Review Pack and receipt are already the terminal memory-review artifact. Any mandatory higher-level audit stays
silent; on Scheduled the final wrapper remains the last bytes visible to the user, while interactive output has no wrapper.

Capture the user-level Skill directory bytecode-cache baseline before helper execution and recheck it afterward. A new or changed
`__pycache__`, `.pyc`, or `.pyo` is an external side effect and fails the run; do not delete it from inside the Scout to hide the
failure. The Bootstrap installer, not the Scout, owns cache-free atomic installation.

Terminal meanings:

- `ok`: at least one card plus complete/bounded coverage.
- `degraded`: material coverage gap; supported cards remain visible and the run does not count.
- `no_material_delta`: complete/bounded census and all search lenses produced no E2/E3 delta.
- `failed`: execution protocol, privacy, integrity, mutation, required-source, render, or read-only failure; no cards.
- `output_budget_exceeded`: not every card fits; no partial cards.
