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
- `canonical_owner=null` means the public artifact does not distribute an Owner. On a fresh host this selects public Core. During
  explicit workstation reconcile, an existing clean Owner may remain only when its managed checkout exactly matches Core's bound
  root and commit. It is not permission to search for, synthesize, detach, or publish another Owner.

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

The tag workflow remains draft-only. The only supported publication transition is
[`release-promotion-v1`](release-promotion-v1.md): a separately authorized operator first generates a read-only, commit- and
asset-bound plan hash, then applies that exact plan and verifies the Release plus every asset attestation before accepting
`non-draft + immutable`. Publication never implies workstation deployment or later-task adoption.

The repository marketplace and both byte-identical Bootstrap Anchors are discovery surfaces. The Anchor's Release Resolver accepts
the latest stable immutable GitHub Release or an explicit version and verifies the release tag/commit, GitHub asset digests,
`SHA256SUMS`, release/source manifests, and portable embedded manifests before installation. Resolution failure is
`release_resolution_blocked`; it never falls back to `main`, a private repository, or an unverified local checkout. The resolver
manually materializes only validated regular-file entries under a new `portable_root`, rejecting absolute/traversal paths,
case-collisions, symlink/device metadata, encryption, and expansion beyond its bound. Anchor executes the formal Bootstrap from that
verified root in the same deployment task, including requested read-only consumer checks. Automatic Skill discovery and natural
adoption remain separate observations; refresh is only a recovery step for missing discovery or an explicit host requirement. The
resolver contract begins with `v0.3.1`; earlier public releases remain historical artifacts and are not valid inputs for this cold-start path.
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

The Plugin also owns the optional `engineering-contract-review` Skill under its `skills/` tree. Its entrypoint and referenced
methods travel in the same Plugin/portable payload and are identified by the existing Plugin version and content hash. They do
not enter Core wheel/sdist or introduce a separate service, Store, version field, or automatic Owner update. Method maintenance
and standalone-copy handoff follow the [method SOP](../docs/specs/interface.md#按需方法的维护与交接).

The Codex manifest and Claude Code manifest live under the same Plugin root and must agree on Plugin name, version and Skill
directory for the legacy subtree. The root Pi package points directly at that Plugin's Anchor and engineering method directories.
Claude's root marketplace explicitly selects those same directories plus the shared Scout source. The portable archive includes
these discovery manifests, projected root Claude metadata and the same method
files; no new implementation, Store, version authority or updater is introduced. Native package/plugin managers own installed
caches and enablement. They do not authorize instruction synchronization or source/Store mutations. The
[user entry](../README.md#optional-engineering-methods-on-codex-pi-and-claude-code) owns installation and invocation guidance.

### Scout host qualification

The existing qualified Scout entry is Codex Desktop-bound. Additional native hosts must meet the same binding, coverage and
output-grant obligations through their actual CLI/SDK/API entry; Desktop UI is not a universal prerequisite.
A method file, SDK symbol, empty session list or successful source import does not
establish the complete native contract. Evaluate each host independently:

| Requirement | Codex Desktop | Pi | Local Claude Code |
|---|---|---|---|
| Current project identity | Same-host project inventory plus native task cwd/Git identity | Current ExtensionContext/header/session identity reaches the native/Git preflight; released entry adoption remains unverified | Current native init adapter plus native/Git preflight; historical SDK metadata alone is not a current invocation; Desktop association is separate when relevant |
| Project history | Native active/archived listing and per-task reads, with exact cursors | Native `SessionManager.list(cwd)` and `open(...).getEntries()` exist; complete-coverage/error semantics need qualification | Native SDK `listSessions({dir, includeWorktrees:false})` and `getSessionMessages(id,{dir,...})` exist; complete-coverage/error and native termination semantics need qualification; Desktop coverage is separate when relevant |
| Artifact authorization | Explicit current task metadata or an explicitly user-selected root; original native request checked before deep work | Same current-request consent rule and immutable containment checks; installed natural entry not yet verified | Same current-request consent rule and immutable containment checks; installed natural entry not yet verified |
| Product qualification | Existing Project v7 / Review Pack v8 / Delivery v2 contracts | Project v8 / Pack v9 bounded review reaches formal delivery/recovery; the Pi entry ships in v0.6.2. Installation and natural acceptance require per-host evidence | Project v8 / Pack v9 bounded source consumers reach formal delivery/recovery; an ordinary Claude Scout entry is not included |

Primary interface owners are [Codex App Server](https://developers.openai.com/codex/app-server/),
[Pi SessionManager](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/session-manager.ts),
[Pi extension context](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md) and the
[Claude Agent SDK reference](https://code.claude.com/docs/en/agent-sdk/typescript#listsessions).
These references establish available primitives, not Sidecar adoption. The Pi 1.5.2 installed SDK was exercised with an explicit
current-project directory and returned a scoped empty list; this proves the call shape only. Claude's directory options must
always be explicit: omitting `dir` searches across projects, and worktree inclusion defaults to true. Neither interface permits
Sidecar to expand an authorized project, parse raw private transcripts itself, invent a Desktop project ID, or treat a writable
directory as a task output grant. A future adapter must preserve current context, source provenance, coverage/error states,
artifact containment and deterministic terminal behavior through its real native entry before qualification. Full Scout support
must not be inferred from the independently portable engineering method.

The native-source component can mechanically export the current Pi read-only session manager and seal its header/entries
through Scout's existing importer; see [native source snapshots](../skills/global-owner-scout/references/contracts.md#native-session-source-snapshots).
Its scope is one SDK session object, not project enrollment, a complete history index, a task terminal or an output grant.
Pi 1.5.2's native parser skips malformed lines and its scoped list can hide directory errors as an empty result. This blocks a
complete-history claim until a native diagnostic/coverage interface or an explicitly approved contract change addresses it.
Do not compensate with a private transcript parser or silently convert a snapshot to a complete Scout review.
Claude's source bridge calls scoped `getSessionInfo`/`getSessionMessages`, checks identity before fetching messages and seals
the original page plus its request. It does not fabricate EOF or task termination. SDK source validation does not prove a
Desktop session association; require that association only when the claim concerns Desktop.

#### Adapter work and decisions

Method portability and host qualification are independent work. The following gaps are not permanent unsupported-host labels:

| Boundary | Work within the current project | Additional requirement before full qualification |
| --- | --- | --- |
| Current Pi source | Export the host-supplied read-only SessionManager header/entries and reuse immutable sealing; validate exact session/root and reject conflicting objects. | Observe that component through the real host entry. A current native session is a source identity, not a fabricated Desktop project ID or project-inventory proof. |
| Project binding | The session-host contract binds actual current Pi ExtensionContext/header or Claude system/init to the Git root, rejecting conflicting native identities and historical-summary substitutions. | A released entry must actually supply that live native object. A frozen old object proves only its original invocation; it is not permission to scan other projects. |
| History coverage and task terminal | Reproduce native API error/record-loss behavior on isolated fixtures; keep snapshots and observed assistant stop reasons separate from complete-index/task-terminal claims. | A strict native coverage/error and terminal interface, or a separately approved equivalent contract. Do not add a private transcript parser to compensate for silently lost native data. |
| Artifact output | Reuse existing explicit-grant containment, immutable write and readback checks. A parent Codex task may grant its own isolated verification output without proving a Pi-native grant. | The native caller must supply actual task output metadata or the user's explicit selection in that current invocation. A model declaration, stale request, writable directory or agent state root is insufficient; containment alone does not authenticate consent. |
| Local Claude source | Exercise the official SDK with an explicit project `dir`, `includeWorktrees:false` for indexing, and system-boundary messages requested. The source bridge retains native session/page identity; CLI method use is verified through the CLI, not gated on UI. | Complete history/errors and task termination remain separate from a source page. Desktop association is required only for a Desktop claim. Installing a test SDK is not permission to change login, security or model configuration. |

The [official Claude SDK reference](https://code.claude.com/docs/en/agent-sdk/typescript)
documents optional system-message inclusion; its default user/assistant-only view cannot stand in for an unqualified full history.

Current SDK omissions do not block every useful review: the native-session Project v8 / Pack v9 lane represents actual observed
scopes with unknown/degraded history and independent current-Owner corroboration. It never awards complete history. Codex v7/v8
and historical artifacts retain their interpretation. The existing protocol permits a frozen active-turn snapshot, so neither
host must wait for the entire chat to end. Native turn observations remain distinct from business success and user adoption.
The Pi package exposes the shared Scout source and its read-only native context tool. Its Git manifest uses `skills/`;
the deterministic portable producer projects those managed Skill/extension references to the existing `.agents/skills/` layout.
Both consumers validate actual referenced files. This is one method source with a package-path projection, not a second Skill copy.
Claude's root marketplace entry selects the same two plugin methods and the shared Scout source through explicit native
Skill paths. The portable producer projects those paths and root plugin metadata, without copying method text.
Its ordinary entry forwards native Skill substitutions as a distinct caller context, never a fabricated init event;
the pinned official SDK is a separate deployment prerequisite under native plugin data. Ordinary Scout does not run npm.
See [the caller and runtime contract](../skills/global-owner-scout/references/contracts.md#native-session-source-snapshots).
This source entry does not itself qualify a released installation or natural invocation.
The Pi source entry's qualification does not qualify an installed release or natural model routing. Follow the same versioned
release and native package installation paths as the engineering method; report each host's observed scope independently.
No additional account access, production write, global-rule change, background collector or permanent capability registry follows
from this adapter work. A genuine missing output authorization or a product-contract choice is reported separately from an SDK
capability gap; neither should be replaced with a generic permission request.

### Release source identity

The release manifest's `source` object has exact fields:

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
