# Global instruction synchronization v1

Status: implementation contract; production rollout requires separate deployment authorization.

## Scope

`同步并部署本机 Agent Memory` may synchronize the complete approved global document to Codex and Pi on the current workstation. This is instruction distribution, not Pi Core Hook, Scout, or model-adoption support. Existing AGENTS.md files are not edited during mechanism development.

The canonical Git source remains the only editing authority. Host files are exact projections; each host's existing-format Installation Registry stores its own binding and last deployed hash, never rule content. Codex retains its existing Store and schema. Pi uses the same registry schema in its agent directory without installing Codex Hooks. No cross-host runtime events or credentials are copied.

## Operation

`agent-memory instructions sync --source <bound-checkout> [--codex-home <observed-home>] [--pi-agent-dir <observed-directory>]` previews. `--apply --plan-hash <preview-hash>` recomputes and applies that exact plan. With no explicit target options, inspect existing configured/default Codex and Pi directories only; never install a missing host. Explicit directories enroll selected hosts. Repeated calls must supply non-default inactive-host directories from actual host authority; do not infer another process's environment.

Source must be a clean main checkout with origin. Read origin/main into a fresh isolated clone, fix the commit, and read the committed global/AGENTS.md bytes, independently of the local checkout's age. Never pull/reset/clean a working project. Git credentials stay in the existing Git credential provider. A source-access error preserves all targets; no cached-latest claim.

Preview is read-only with respect to all persistent installation and project state; temporary Git resolution is cleaned. Local `instruction-sync.json` stores enrolled host directories and source-discovery identity only; the host registry remains the sole baseline owner. Source/target arguments can be omitted after first enrollment. Apply retains a verified reconstructable source snapshot under the workstation's explicit state directory (default ~/.agents/agent-memory). Source snapshots are bound by remote and commit. Source identity replacement is blocked, not implicitly authorized by synchronization.

All target paths and current source bindings are inspected before any target write. Empty/missing targets and exact desired bytes are admissible; otherwise current bytes must equal that target's last deployed hash. First-use nonempty divergence is blocked. After the user reviews the exact local/published difference and approves replacement, `--adopt-existing HOST=SHA256` admits only that unbound host's exact reviewed local bytes into a fresh preview; apply still binds both the before hash and published commit. It is rejected for already-bound targets and is not a drift-bypassing force switch. Any existing AGENTS.override.md blocks qualification. Aliases, hard links, duplicate targets, dirty bound sources, or identity mismatches fail closed. Existing Core runtime records remain unchanged.

Apply locks the state and target paths, refreshes the plan, and rejects stale hashes. File writes and binding updates are verified. An exception restores touched files and registry rows; a restoration failure is explicitly partial, never unchanged. An interruption journal blocks further application until reviewed recovery; no automatic overwrite of potentially newer user edits. Recovery material is private, local, and never committed. Successful completion removes transient recovery data.

## Evidence

Report source commit, content hash, and per-host changed/noop plus reload_required. File readback is not loaded-context or behavioral-adoption evidence. Pi reload/new session and Codex refresh/new task are separate consumer checks. No one-device result proves another device.

## Acceptance

Test real CLI preview/apply, idempotence, remote updates in both directions, stale preview, local drift, first-use divergence, override, explicit/custom homes, missing hosts, identity mismatch, network failure, bound-source dirtiness, write failure rollback, registry preservation and interruption blocker. Run platform tests on Windows and macOS; isolated paths on one OS do not prove the other OS. Existing Core/Scout regressions must remain passing.
