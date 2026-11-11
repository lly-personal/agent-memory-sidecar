# Global instruction synchronization v1

Status: implementation contract; production rollout requires separate deployment authorization.

## Scope

`同步并部署本机 Agent Memory` may synchronize the complete approved global document to enrolled Codex, Pi, and Claude Code hosts on the current workstation. Codex and Pi receive `AGENTS.md`; Claude Code receives `CLAUDE.md` in its explicitly observed user configuration directory. This is instruction distribution, not Claude/Pi Core Hook, Scout, project-instruction loading, or model-adoption support. Existing host instruction files and synchronization configuration are not edited during mechanism development.

The canonical Git source remains the only editing authority. Host files are exact projections; each host's existing-format Installation Registry stores its own binding and last deployed hash, never rule content. Codex retains its existing Store and schema. Pi uses the same registry schema in its agent directory without installing Codex Hooks. No cross-host runtime events or credentials are copied.

## Operation

`agent-memory instructions sync --source <bound-checkout> [--codex-home <observed-home>] [--pi-agent-dir <observed-directory>] [--claude-home <observed-directory>]` previews. `--apply --plan-hash <preview-hash>` recomputes and applies that exact plan. With no explicit target options, inspect existing configured/default Codex and Pi directories and already-enrolled Claude only; never silently enroll Claude merely because its directory or environment variable exists. `--claude-home` first enrolls the observed Claude Code user configuration directory, and any persistent host enrollment or instruction change requires its separately authorized deployment. Repeated calls must supply non-default inactive-host directories from actual host authority; do not infer another process's environment. An observed `CLAUDE_CONFIG_DIR` differing from an enrolled Claude directory blocks the operation.

Source must be a clean main checkout with origin. Read origin/main into a fresh isolated clone, fix the commit, and read the committed global/AGENTS.md bytes, independently of the local checkout's age. Never pull/reset/clean a working project. Git credentials stay in the existing Git credential provider. A source-access error preserves all targets; no cached-latest claim.

Preview is read-only with respect to all persistent installation and project state; temporary Git resolution is cleaned. Local `instruction-sync.json` stores enrolled host directories and source-discovery identity only; the host registry remains the sole baseline owner. Source/target arguments can be omitted after first enrollment. Apply retains a verified reconstructable source snapshot under the workstation's explicit state directory (default ~/.agents/agent-memory). Source snapshots are bound by remote and commit. Source identity replacement is blocked, not implicitly authorized by synchronization.

All target paths and current source bindings are inspected before any target write. Empty/missing targets and exact desired bytes are admissible; otherwise current bytes must equal that target's last deployed hash. First-use nonempty divergence is blocked. After the user reviews the exact local/published difference and approves replacement, `--adopt-existing HOST=SHA256` admits only that unbound host's exact reviewed local bytes into a fresh preview; apply still binds both the before hash and published commit. It is rejected for already-bound targets and is not a drift-bypassing force switch. Existing `AGENTS.override.md` blocks Codex and Pi; Claude does not use that override. Aliases, hard links, duplicate targets, dirty bound sources, or identity mismatches fail closed. Existing Core runtime records remain unchanged.

Claude Code may interpret `@` imports and strip HTML comments in `CLAUDE.md`; byte-identical files do not prove identical effective context. Its project `AGENTS.md` discovery depends on the actual engine version, settings, and competing project instructions. Check the active local consumer and conflicts separately; a desktop application version, synthetic test, or Pi using a Claude model does not prove Claude Code loading. Skills, plugins, project files, and the Desktop-bound Scout are outside this synchronization operation. An enrolled Claude entry makes old releases that only recognize Codex/Pi reject the configuration: retain the new runtime until an explicitly reviewed rollback or unenrollment procedure exists; do not edit the state file by hand.

Apply locks the state and target paths, refreshes the plan, and rejects stale hashes. File writes and binding updates are verified. An exception restores touched files and registry rows; a restoration failure is explicitly partial, never unchanged. An interruption journal blocks further application until reviewed recovery; no automatic overwrite of potentially newer user edits. Recovery material is private, local, and never committed. Successful completion removes transient recovery data.

## Evidence

Report source commit, content hash, and per-host changed/noop plus reload_required. File readback is not loaded-context or behavioral-adoption evidence. Pi reload/new session, Codex refresh/new task, and a fresh Claude Code session in its actual project context are separate consumer checks. No one-device result proves another device.

## Acceptance

Test real CLI preview/apply, idempotence, remote updates in both directions, stale preview, local drift, first-use divergence, override, explicit/custom homes, missing hosts, identity mismatch, network failure, bound-source dirtiness, write failure rollback, registry preservation and interruption blocker. Run platform tests on Windows and macOS; isolated paths on one OS do not prove the other OS. Existing Core/Scout regressions must remain passing.
