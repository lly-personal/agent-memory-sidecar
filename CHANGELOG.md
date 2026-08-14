# Changelog

All notable user-visible changes are recorded here. This project uses semantic versions for Core; Plugin, Bootstrap, and Scout keep
their own component versions in `COMPATIBILITY.md`.

## Unreleased

No changes have been assigned to a later release.

## 0.3.0 (unreleased public candidate)

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
