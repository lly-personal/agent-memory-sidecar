# Agent Memory Public Distribution v1

Status: Accepted

Owner: project_docs

## Product boundary

Public distribution has two explicit artifacts:

1. `agent-memory-sidecar` wheel and sdist contain Core only: the Python package and CLI.
2. `agent-memory-portable-<version>.zip` contains the versioned Plugin, Bootstrap Anchor, Workstation Bootstrap, Global Owner
   Scout, current public contracts, compatibility matrix, and an immutable source manifest.

The private engineering repository, its Git history, host evidence, canonical Global Owner contents, Store, Host Profile, task
history, credentials, and unconfirmed Review Packs are never implicit inputs to either artifact.

## Source manifest

`agent_memory_source_manifest_v1` has exact top-level fields:

```text
contract_version, distribution, sidecar, canonical_owner
```

`distribution` is `development` or `release`. `sidecar` is required. `canonical_owner` is either `null` or a source object.
Each source object has exact fields:

```text
remote, ref, commit
```

- `remote` must be a credential-free HTTPS, SSH, file URL, SCP-style Git remote, or absolute local test remote.
- `ref` is a non-empty branch/tag/ref used for bounded fetch.
- `commit` is a full lowercase 40-hex Git commit. It is mandatory for `release`; `development` may use `null`.
- A checkout is accepted only when normalized origin, clean status, checked-out commit, and expected commit all match.
- `canonical_owner=null` means public Core mode. It is not permission to search for another Owner or to perform global mutation.

## Two-stage public export

`public_source_export_v1` accepts an explicit public repository URL, engineering source commit, SPDX license expression, and
license file. The destination URL must differ from the history-bearing private engineering repository. It:

1. requires a clean source tree at the declared commit;
2. copies only a repository-owned allowlist into a new output directory and normalizes every selected UTF-8 text file plus the
   license to LF before hashing;
3. maps the public root instructions template and records the engineering commit plus the rewritten public snapshot digest;
4. rejects private paths, thread URIs, credentials, private deny literals, bytecode/cache files, hardlinks, symlinks, junctions,
   reparse points, undecodable text, and binary/NUL-bearing files. Files not selected by the allowlist remain private; a declared pattern that resolves
   to no file fails closed.

The allowlist grammar owns `path/**`: it means every descendant regular file under `path`, independent of the Python runtime's
trailing-`**` glob behavior. Traversal rejects any alias/reparse component rather than following or silently omitting it.

After the exported tree is committed in the independent public repository, `agent_memory_public_release_manifest_v1` accepts that
repository URL and an existing `v<Core>` ref that resolves exactly to public `HEAD`. It generates the commit-bound source manifest,
Core archives, portable bundle, SBOM, checksums, and release manifest. It runs package-boundary, metadata, wheel/sdist clean-install,
reproducible-rebuild, CLI, Skill self-test, source-manifest, portable-content, and document-link checks before reporting
`public_artifact_verified`.

Neither stage changes repository visibility, Git history, tags, Releases, registries, local Codex state, or private Owner state.

The repository marketplace and both byte-identical Bootstrap Anchors are discovery surfaces. The Anchor's Release Resolver accepts
the latest stable immutable GitHub Release or an explicit version and verifies the release tag/commit, GitHub asset digests,
`SHA256SUMS`, release/source manifests, and portable embedded manifests before installation. Resolution failure is
`release_resolution_blocked`; it never falls back to `main`, a private repository, or an unverified local checkout. The resolver
contract begins with `v0.3.1`; earlier public releases remain historical artifacts and are not valid inputs for this cold-start path.
For GitHub API metadata only, the Resolver may use an explicit `GITHUB_TOKEN`/`GH_TOKEN` or existing non-interactive `gh`
authentication before falling back to the anonymous public quota. It never persists or renders that token; rate limiting and invalid
authentication remain distinguishable failure details under `release_resolution_blocked`.

The export stage is a bootstrap and provenance mechanism, not an ongoing mirror. Authority epochs, the one-time cutover gate, and
steady-state public development are owned by `public-authority-cutover-v1.md`:

- before cutover, the public repository is a candidate and an exact export receipt is required for a release build;
- after cutover, tracked `PUBLIC_AUTHORITY.json` must validate as `agent_memory_public_authority_v1`, the initial public release
  must remain an ancestor of `HEAD`, and later releases build directly from public Git history;
- the private engineering repository must not export or synchronize later public product changes after cutover.

Repository seeding, release publication, installation qualification, and authority activation are distinct facts. A public
repository or published Release does not by itself transfer engineering authority.

## Compatibility

The release manifest must name Core, Plugin, Bootstrap, and Scout versions separately. A release is invalid if source metadata,
Plugin manifest, Skill contracts, compatibility matrix, archive names, and generated metadata disagree.

Its `source` object has exact fields:

```text
repository, ref, commit, authority_epoch, engineering_source_commit,
initial_public_release, authority_activated_at
```

`initial_public_release` has exact fields `ref, commit, snapshot_sha256`. `authority_epoch` is `private_engineering` for the initial
seed release and `public_active` for later public-native releases. `authority_activated_at` is `null` before cutover and the marker's
UTC timestamp after cutover.

## Evidence and gates

- `public_export_blocked`: a required legal, privacy, source-identity, version, content, or verification gate failed.
- `public_artifact_verified`: allowlisted artifacts were generated and verified locally.
- `public_install_verified`: those artifacts were installed from their built form in a clean environment and their real entrypoints ran.
- `public_published`: repository/Release/registry state was read back after an explicitly authorized public action.
- `public_active`: a separate human cutover decision activated public `main` as the sole engineering authority after publication and
  installation qualification; it is a governance epoch, not a higher product-adoption evidence claim.

No lower state proves a higher state. In particular, source tests, a private `main` commit, or a generated archive do not prove
public installation or publication.
