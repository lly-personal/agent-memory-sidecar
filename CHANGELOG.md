# Changelog

All notable user-visible changes are recorded here. This project uses semantic versions for Core; Plugin, Bootstrap, and Scout keep
their own component versions in `COMPATIBILITY.md`.

## 0.3.6 (2026-08-21)

### Fixed

- Release publication no longer depends on an unbound prose-only operator sequence. A deterministic inspect/apply gate binds the
  commit, tag, Changelog, immutable-release policy, and complete local/remote asset digests before publication, then requires
  Release and per-asset attestation verification plus immutable readback.
- Global Owner Scout no longer treats a pre-delivery Markdown verifier as proof of the actual user-visible final. Interactive
  delivery now fails closed unless the complete Review Pack is created outside the reviewed project as an immutable current-task
  artifact and the real task surface is externally read back and verified.
- A real background-worktree canary showed that the Desktop host may return `queued` for a valid task artifact. Scout now preserves
  the content-bound artifact link as externally verifiable `surface_pending`, while keeping confirmation disabled and Production
  qualification blocked until an explicit opened surface is observed.
- A foreground canary showed that a worktree-local Scout 5.6 source does not override the formally installed Scout 5.5 consumer.
  Canary qualification now requires the actual installed Skill version/content identity; legacy inline results are ineligible and
  cannot be counted as Delivery v1 evidence.

### Added

- `agent_memory_release_promotion_plan_v1` and `agent_memory_release_promotion_receipt_v1` for the separately authorized
  `verified draft -> attested immutable Release` transition.
- `global_owner_scout_delivery_v1`, task-artifact creation/readback, compact delivery receipts, and controller-side verification for
  realistic 0/1/3/6/7/8/24-card Review Packs.

### Changed

- The component set is Core 0.3.6, Plugin 1.4.0, Workstation Bootstrap 1.9.0, and Scout 5.6.0. Review Pack remains v4;
  Scheduled Scout remains production-blocked.

## 0.3.5 (2026-08-14)

### Changed

- The public Plugin now verifies and safely materializes the portable release, then runs the formal Workstation Bootstrap in the
  same deployment task. One Codex refresh/new task remains only for automatic Skill discovery, not for deferred host setup.
- Workstation Bootstrap now uses one fresh-plan reconcile path for fresh, update, and legacy hosts. A public manifest preserves an
  existing private Owner only when its clean managed checkout exactly matches Core's bound root and commit; ambiguous state fails
  closed and Owner removal remains a separate decision.
- Release versions are Core 0.3.5, Plugin 1.3.0, Workstation Bootstrap 1.8.0, and Scout 5.5.0.

## 0.3.3 (2026-08-14)

### Fixed

- Source Authority Cutover now consumes Core setup through the real `agent_memory_result_v1.data` boundary. This prevents a successful
  Core setup from being falsely reported as `core_setup_doctor_missing` and leaving source rollback behind an already-updated runtime.
- The materialization regression test now uses the real CLI result envelope and rejects the former mock-only raw result shape.

### Changed

- Core is 0.3.3 and Workstation Bootstrap is 1.7.1; Plugin remains 1.2.1 and Scout remains 5.5.0.

## 0.3.2 (2026-08-14)

### Fixed

- Release Resolver metadata requests now use an explicit `GITHUB_TOKEN`/`GH_TOKEN` or existing non-interactive `gh` authentication
  when available, so an exhausted anonymous GitHub API quota does not block an otherwise valid public cold start.
- GitHub API rate limiting, invalid authentication, and missing release metadata now remain distinguishable fail-closed errors instead
  of collapsing into a generic availability failure.

### Changed

- Core is 0.3.2 and Plugin is 1.2.1; Bootstrap remains 1.7.0 and Scout remains 5.5.0.

## 0.3.1 (2026-08-14)

### Added

- Explicit Source Authority Cutover v1 with a read-only plan hash, `keep_owner` boundary, atomic source/Skill rollback, and success receipt.
- Public Release Resolver that rejects mutable or incomplete Releases and verifies tag/commit, GitHub asset digests, checksums, manifests, and portable contents.
- Tagged repository Marketplace and byte-identical repository/plugin Bootstrap Anchors.

### Changed

- Workstation Bootstrap is 1.7.0; Plugin is 1.2.0; Scout remains 5.5.0.
- Public `main` is documented as the sole engineering authority; consumer release installation and contributor editable setup are separate paths.

## 0.3.0 (2026-08-14)

### Added

- Atomic multi-card Review Pack confirmation with exact visible-selection binding.
- Physical containment and private-permission checks for instruction and Store targets.
- Commit-bound public source manifests with an optional private Global Owner.
- Allowlisted public-export and artifact verification design.
- Public engineering-authority cutover contract with a one-time seed, explicit activation gate, and private-repository archive boundary.

### Changed

- Global Owner Scout Review Pack contract is v4 and Scout is 5.5.0.
- Workstation Bootstrap is 1.6.0; Plugin is 1.1.0.
- Cross-platform containment accepts only OS-owned top-level POSIX directory mappings while continuing to reject user-controlled aliases.
- Recursive public allowlists have runtime-independent semantics; CI separates repeated hosted-runner performance observations from the functional matrix and adds a positive synthetic release consumer, while the hard budget remains owned by the supported local acceptance environment.
- Public release tooling distinguishes an exact pre-cutover export snapshot from post-cutover public-native development and prepares a public-only verified draft; immutable publication remains a separately authorized administrator operation.
- Public-facing license and release-boundary guidance now describes the exported checkout's actual SPDX metadata instead of retaining private Phase A status text.
- Public export normalizes all selected UTF-8 source and license bytes to LF, so the initial public snapshot is independent of the private checkout's line-ending policy.
- Contract tests distinguish the private export-authority surface from the exported public checkout, so public CI validates portable consumers without requiring intentionally excluded private templates or marketplace files.
- Release archives prune ignored interpreter and log noise created by prior validation while still rejecting the same paths when they are tracked source, so the test-to-release sequence remains composable without weakening the artifact boundary.
- The positive release smoke follows the active authority context: private engineering validates export through consumption, an initial public checkout validates its own tagged snapshot through consumption, and a public-active checkout validates the tracked authority marker without requiring private export templates.
- Public exports include an LF-enforcing `.gitattributes`, keeping the receipt-bound snapshot stable when Windows consumers clone under a global `core.autocrlf=true` policy.
- The release draft job checks out the tagged repository before `gh release create --verify-tag`, so the independent job can verify the tag instead of failing outside a Git worktree.

### Security

- Approval content, target-before identity, symlink/reparse points, hardlinks, Store ancestry, and platform permissions fail closed.
- Core and Bootstrap Skill installation, privacy scans, and portable archive traversal reject nested aliases instead of following or silently omitting them; Windows Store ACL verification checks protected-DACL principals semantically.

## 0.2.0

- Historical rollback release. Core v1 is a breaking replacement and does not restore the former five-verb lifecycle.
