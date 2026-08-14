# Agent Memory Public Authority Cutover v1

Status: Accepted

Owner: project_docs

## Purpose

This contract moves the public product from a one-time allowlisted seed to one unambiguous long-term engineering authority. It is a
repository-governance contract, not a Core runtime state machine, CLI, database schema, or behavior owner.

## Authority epochs

Exactly one repository owns public product development in each epoch:

| Epoch | Engineering authority | Public repository role | Private repository role |
| --- | --- | --- | --- |
| `private_engineering` | The history-bearing private engineering repository | Absent or a seeded release candidate; no independent product changes | Active development and evidence source |
| `public_candidate` | The history-bearing private engineering repository | Allowlisted candidate used for CI, release, and clean-install qualification | Active development and evidence source |
| `public_active` | The independent public repository `main` | Unique source for public code, specifications, issues, pull requests, tags, and releases | Frozen, archived history and rollback evidence only |

`public_candidate` is not a dual-authority period. Until cutover, any correction to public product content returns to the private
engineering authority and produces a new allowlisted candidate. After cutover, the private repository must not export, mirror, or
publish later public product changes.

## Cutover gate

The transition to `public_active` requires all of the following for one exact public commit and release:

1. an allowlisted seed with a valid `PUBLIC_EXPORT_RECEIPT.json` that binds the engineering source commit and public snapshot;
2. a public repository readback with the intended visibility, default branch, governance files, required checks, security intake,
   and immutable-release policy;
3. `public_artifact_verified` for a `v<Core>` tag that resolves exactly to public `HEAD`;
4. `public_install_verified` from built release assets in clean environments without private credentials or a canonical Owner;
5. `public_published` from a readback of the immutable GitHub Release, tag, assets, checksums, and attestations;
6. a separate explicit human decision to activate the public repository as the engineering authority.

No lower evidence state implies authority activation. A real new Codex Desktop task may separately prove adoption, but adoption,
cross-host continuity, and product effect remain outside this cutover gate.

## Active authority marker

After the cutover decision, the first public `main` commit after the qualified release adds `PUBLIC_AUTHORITY.json` with exact fields:

```json
{
  "contract_version": "agent_memory_public_authority_v1",
  "status": "public_active",
  "repository": "https://github.com/example/agent-memory-sidecar",
  "engineering_source_commit": "<40 lowercase hex>",
  "initial_public_release": {
    "ref": "v0.3.0",
    "commit": "<40 lowercase hex>",
    "snapshot_sha256": "<64 lowercase hex>"
  },
  "activated_at": "2026-08-14T00:00:00Z"
}
```

The marker is repository evidence, not authorization by itself. Release tooling accepts it only when:

- the repository identity matches the current origin and requested public repository;
- the marker is tracked, has the exact schema above, and uses a UTC `Z` timestamp;
- the initial release ref still resolves to the recorded commit;
- the recorded initial release commit is an ancestor of current public `HEAD`;
- the engineering source commit and initial snapshot digest are well formed.

Before this marker exists, release tooling requires the original export receipt and exact seeded snapshot. After it exists, future
releases build directly from public Git history; they do not require a refreshed private export receipt.

## Publication workflow

The tag workflow runs only in a public repository. With the minimum `contents: write` token it:

1. builds and verifies artifacts from an existing version tag;
2. attests the exact files;
3. creates or resumes a draft Release;
4. uploads the complete verified asset set and compares the remote asset names with the local set; and
5. proves the Release remains a draft.

Checking repository immutable-release settings requires administration-read authority that the standard workflow token does not
have. The workflow therefore never receives or stores an administrator token and never publishes the draft. In the separately
authorized publication operation, an administrator checks that immutable releases are enabled, re-reads the draft asset set,
publishes it, verifies each local asset against the release attestation, and reads back the Release as non-draft and immutable.

A failed workflow may leave a draft for an idempotent retry. Once an immutable Release is published, its tag or assets must not be
moved, replaced, or reused; a correction uses a new semantic version.

## Ongoing development

After `public_active`:

- all public code, specifications, tests, issues, pull requests, CI, tags, and releases evolve in the public repository;
- private observations enter the public project only as sanitized issues or pull requests;
- the private engineering repository is archived instead of deleted, rewritten, or used as a hidden upstream;
- an optional private Global Owner remains a separately configured backend and never becomes public Core authority;
- PyPI remains a separately authorized distribution channel and is not implied by GitHub publication.

## Stop and recovery rules

- Before public repository creation, any legal, privacy, identity, or content failure is zero-disclosure and blocks the next stage.
- After repository seeding but before cutover, the private repository remains authority; fix the private source and create a new
  candidate. Making a disclosed repository private does not revoke copies already obtained by others.
- After a published Release but before cutover, do not move the released tag; publish a new patch release if qualification changes.
- After cutover, rollback and fixes occur in the public repository. Reactivating the private repository would create dual authority
  and requires a new explicit architecture decision.

## Acceptance

- Tests prove that an unmarked seed requires an exact export receipt and that tracked snapshot drift fails closed.
- Tests prove that a valid `public_active` marker permits later public commits only when its initial release is an ancestor.
- Tests reject wrong repository identity, malformed provenance, untracked markers, missing tags, and non-ancestor release commits.
- The release workflow is public-only, uploads and verifies a complete draft, and cannot publish. The separately authorized admin
  operation checks immutable-release policy before publication and reads back the immutable result.
- L1, L2, L3, ADRs, operator guidance, and the public allowlist identify the same unique authority in every epoch.
