# Agent Memory Release Promotion v1

Status: Accepted

Owner: project_docs

## Purpose

`release-promotion-v1` is the sole public `draft -> published immutable` operator contract. It closes the gap between the
tag-triggered workflow, which intentionally stops at a verified draft, and the immutable GitHub Release consumed by the public
Resolver. It does not build artifacts, create or move tags, change repository settings, publish PyPI, or deploy a workstation.

## Plan

`scripts/publish_release.py inspect` is read-only and returns `agent_memory_release_promotion_plan_v1`. It requires:

- a clean public checkout whose `HEAD`, annotated local tag, remote `main`, and peeled remote tag all equal one supplied full commit;
- a versioned Changelog section with no stale `unreleased` copy;
- a local release directory whose regular files, `SHA256SUMS`, release manifest, source repository/ref/commit, sizes, and digests agree;
- an existing stable draft with the exact same uploaded asset set and GitHub SHA-256 digests; and
- repository immutable releases enabled through the current GitHub Administration read API.

The plan fixes `repository`, `tag`, `source_commit`, immutable-policy result, the ordered asset name/size/digest set, and terminal
target `is_draft=false / is_immutable=true`. Canonical JSON of those facts produces `plan_hash`; inspect performs no publish or
remote mutation.

## Apply

`scripts/publish_release.py apply` accepts the same inputs and one exact `plan_hash`. It recomputes the complete plan immediately
before mutation and fails on drift. A valid apply:

1. publishes only the named draft through `gh release edit <tag> --draft=false`;
2. performs a bounded readback until GitHub reports a publication timestamp, non-draft, and immutable;
3. rechecks the exact remote asset set and digests;
4. verifies the Release attestation and every local asset against the Release attestation; and
5. emits `agent_memory_release_promotion_receipt_v1 / public_published` with the source commit, consumed plan hash, publication
   timestamp, release URL, asset count, and terminal flags.

Failure before publication preserves the draft. Failure after the GitHub mutation does not claim rollback: the operator must read
the current Release state, because immutable publication is intentionally irreversible. Once immutable, the tag and assets are not
rebuilt or replaced; corrections use a new semantic version.

## Acceptance criteria

- Inspect cannot call the publish command.
- Stale copy, source/tag drift, disabled immutable releases, prerelease state, missing/extra/changed assets, or an already-published
  Release blocks the plan.
- Apply rejects a stale or malformed plan hash.
- Success requires Release and per-asset attestation verification plus `non-draft + immutable` readback.
- CI retains minimum permissions and remains unable to publish; operator credentials and runtime receipts are never committed.
