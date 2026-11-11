# Global instruction synchronization v1

Status: implementation contract; production rollout requires separate deployment authorization.

## Scope

`同步并部署本机 Agent Memory` may synchronize the complete approved global document to enrolled Codex, Pi, and Claude Code hosts on the current workstation. Codex and Pi receive `AGENTS.md`; Claude Code receives `CLAUDE.md` in its explicitly observed user configuration directory. This is instruction distribution, not Claude/Pi Core Hook, Scout, project-instruction loading, or model-adoption support. Existing host instruction files and synchronization configuration are not edited during mechanism development.

The canonical Git source remains the only editing authority. Host files are exact projections; each host's existing-format Installation Registry stores its own binding and last deployed hash, never rule content. Codex retains its existing Store and schema. Pi uses the same registry schema in its agent directory without installing Codex Hooks. No cross-host runtime events or credentials are copied.

## Operation

`agent-memory instructions sync --source <bound-checkout> [--codex-home <observed-home>] [--pi-agent-dir <observed-directory>] [--claude-home <observed-directory>]` previews. `--apply --plan-hash <preview-hash>` recomputes and applies that exact plan. With no explicit target options, inspect existing configured/default Codex and Pi directories and already-enrolled Claude only; never silently enroll Claude merely because its directory or environment variable exists. `--claude-home` first enrolls the observed Claude Code user configuration directory, and any persistent host enrollment or instruction change requires its separately authorized deployment. Repeated calls must supply non-default inactive-host directories from actual host authority; do not infer another process's environment. An observed `CLAUDE_CONFIG_DIR` differing from an enrolled Claude directory blocks the operation.

Source must be a clean main checkout with origin. Read origin/main into a fresh isolated clone, fix the commit, and read the committed global/AGENTS.md bytes, independently of the local checkout's age. Never pull/reset/clean a working project. Git credentials stay in the existing Git credential provider. A source-access error preserves all targets; no cached-latest claim.

Preview is read-only with respect to all persistent installation and project state; temporary Git resolution is cleaned. Local `instruction-sync.json` stores enrolled host directories and source-discovery identity only; the host registry remains the sole baseline owner. Source/target arguments can be omitted after first enrollment. Apply retains a verified reconstructable source snapshot under the workstation's explicit state directory (default ~/.agents/agent-memory). Source snapshots are bound by remote and commit. Source identity replacement is blocked, not implicitly authorized by synchronization.

All target paths and current source bindings are inspected before any target write. Empty/missing targets and exact desired bytes are admissible; otherwise current bytes must equal that target's last deployed hash. First-use nonempty divergence is blocked. After the user reviews the exact local/published difference and approves replacement, `--adopt-existing HOST=SHA256` admits only that unbound host's exact reviewed local bytes into a fresh preview; apply still binds both the before hash and published commit. It is rejected for already-bound targets and is not a drift-bypassing force switch. Existing `AGENTS.override.md` blocks Codex and Pi; Claude does not use that override. Aliases, hard links, physically duplicate host directories (including trusted OS alternate spellings), dirty bound sources, or identity mismatches fail closed. Existing Core runtime records remain unchanged.

Claude Code may interpret `@` imports and strip HTML comments in `CLAUDE.md`; byte-identical files do not prove identical effective context. Its project `AGENTS.md` discovery depends on the actual engine version, settings, and competing project instructions. Check the active local consumer and conflicts separately; a desktop application version, synthetic test, or Pi using a Claude model does not prove Claude Code loading. Skills, plugins, project files, and the Desktop-bound Scout are outside this synchronization operation.

## Claude exit and runtime downgrade

Ordinary instruction-content rollback remains a published revert in the canonical source followed by normal synchronization. This is separate from removing a host or downgrading the sync runtime.

Older releases that only recognize Codex/Pi reject a Claude-enrolled configuration. Before such a downgrade, run the new runtime's `instructions sync --unenroll-claude [--claude-home <observed-directory>] [--state-dir <state>]` to preview, then repeat with `--apply --plan-hash <fresh-hash>` after explicit approval of that removal. Do not combine exit with source, Codex/Pi target, or adoption options; it never fetches or changes the canonical source. The saved Claude directory is authoritative, and a conflicting explicit directory or `CLAUDE_CONFIG_DIR` blocks the operation.

Exit requires an existing enrollment and a regular `CLAUDE.md` whose bytes exactly match its bound deployment and source identity. It removes that file, clears only Claude's `global_instruction_binding`, and removes only the Claude enrollment. Codex/Pi files, bindings, source snapshots, all other Claude files, and the Store itself are retained. It does not restore pre-enrollment content that the user previously approved replacing. Missing, changed, linked, or mismatched files/bindings block removal; there is no force option and no hand-edit of saved configuration. A preview or a stale plan never removes anything.

Before capture, the recovery journal and a unique same-filesystem removal stage receive the existing private-file/ACL preflight.
The selected file moves into that stage through held physical directories: POSIX mutations use directory descriptors; Windows
holds physical ancestor handles against replacement. The moved object must match the approved inode/file identity and bytes
before deletion. A save or replacement at capture is retained with the journal instead of deleted. Rollback restores by a
no-clobber link; an independently recreated destination or unsupported restoration leaves recovery material and blocks apply.
State reads, atomic writes, rollback and cleanup use that same held directory; a moved state directory retains recovery
instead of overwriting its replacement. Store removal retains one existing database connection and compares the approved
binding inside its write transaction; rollback restores only a binding this operation successfully removed.
This protects the selected path and capture boundary, not cooperation from a process continuing to write through an already-open handle.

The operation uses the existing lock and interruption-journal boundary. Failure restores only states still matching this operation's known before/after values; concurrent user edits are preserved and incomplete recovery blocks further apply. After committed removal, a journal-cleanup failure is reported as committed with cleanup pending, never as unchanged. Successful readback returns `unenrolled`; a fresh Claude session is needed to observe that this projection is absent. This does not uninstall Claude, its plugins, or other independent instruction sources. Only then may an older Codex/Pi runtime be used for the remaining enrollment; release-specific installation and account/session acceptance are still separate.

The exit receipt has exact fields `contract_version, host, plan_hash, remaining_hosts, applied, adoption, status`;
`contract_version=global_instruction_unenroll_v1`, `host=claude`, `status=planned|unenrolled`, and `adoption=unverified`.
`remaining_hosts` is the sorted saved host set excluding Claude. Its plan binds the complete enrollment-before hash, exact
instruction-before hash, binding row, target directory, and Store file identity. An absent enrollment is a refusal rather than
permission to delete an independently created `CLAUDE.md`.

Apply locks the state and target paths, refreshes the plan, and rejects stale hashes. File writes and binding updates are verified. An exception restores touched files and registry rows; a restoration failure is explicitly partial, never unchanged. An interruption journal blocks further application until reviewed recovery; no automatic overwrite of potentially newer user edits. Recovery material is private, local, and never committed. Successful completion removes transient recovery data.

## Evidence

Report source commit, content hash, and per-host changed/noop plus reload_required. File readback is not loaded-context or behavioral-adoption evidence. Pi reload/new session, Codex refresh/new task, and a fresh Claude Code session in its actual project context are separate consumer checks. No one-device result proves another device.

## Acceptance

Test real CLI preview/apply, idempotence, remote updates in both directions, stale preview, local drift, first-use divergence, override, explicit/custom homes, missing hosts, identity mismatch, network failure, bound-source dirtiness, write failure rollback, registry preservation and interruption blocker. Claude exit also covers no-write preview, drift/context rejection, exact removal, other-host preservation, rollback, concurrent-edit recovery, committed cleanup failure, and subsequent compatibility with an actual prior Codex/Pi CLI. Run platform tests on Windows and macOS; isolated paths on one OS do not prove the other OS. Existing Core/Scout regressions must remain passing.
