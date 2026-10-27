# Codex configuration field reconciliation v1

Status: implementation contract; host deployment and real consumer behavior unverified.

## Ownership and decision

`codex-instructions` owns configuration policy, its justification, exact platform/version applicability,
and decisions to enroll non-secret fields. Sidecar consumes a selected committed JSON blob and owns
read-only discovery, exact preview, approval binding, bounded mutation, readback, and latest-delta recovery.
The caller explicitly chooses the source checkout, full commit, policy path and existing target file.
No polling, cross-repository coordinator, daemon, database, implicit host scan or default target is added.
Existing release packaging includes the Python module and CLI; this contract is included in the public
export allowlist. Existing release verification, installation and workstation reconciliation remain separate
operations; none is run or implied by `config` commands. Whole-document [instruction synchronization](global-instruction-sync-v1.md)
continues to own AGENTS distribution only. The [Core Store](agent-memory-core-v1.md) is unchanged.

Facts determining this boundary: current instruction synchronization replaces whole documents; a user's
TOML contains unknown keys, comments and independent customizations; file values can be overridden by
other configuration sources. The rejected assumption is that distributing AGENTS or rewriting TOML
proves configuration effectiveness. No live security change, Windows diagnosis or consumer success is
proven by implementing this contract. Windows cleanup policy blocks are evidence for investigation,
not a reason to hard-code a candidate setting or replay a denied operation.

## Policy source interface

The source owner can publish this exact JSON shape at any explicitly selected repository-relative path:

```json
{
  "contract_version": "codex_config_policy_v1",
  "owner": "codex-instructions",
  "platforms": ["fixture-platform"],
  "codex_versions": ["fixture-version"],
  "fields": [
    {
      "path": ["fixture_option"],
      "value": "fixture-value",
      "non_secret": true,
      "rationale": "Explain the observed problem and why this minimum change is justified.",
      "risk": "Explain security and behavior changes requiring explicit user approval."
    }
  ]
}
```

The CLI reads `git show <full-commit>:<policy-file>` after verifying an ordinary committed blob.
It does not pull, switch branches, read uncommitted policy bytes or execute policy code. Preview binds
the commit, raw blob hash, parsed policy hash, selected source identity, platform, version, physical target
path, entire before/after file hashes, all observations/deltas, rationale, risk and previous transaction hash.
The source choice is an explicit trust boundary; a JSON owner label is not authentication or remote
publication proof. Source repository identity is represented by a local path hash; no remote credentials
are requested. Policy versions/platforms are explicit strings compared exactly, without inferred ranges.
The caller must obtain the real version/platform independently; command-line claims alone do not prove them.

Only bare-key paths and string/bool/integer values are enrolled. Duplicate or parent/child paths,
unknown policy fields, absent risk/rationale and `non_secret != true` fail closed. The source owner must
never enroll secrets: the engine deliberately trusts that reviewed declaration, not a keyword classifier.
Neither public policy nor receipts should contain tokens or credentials. Local files are parsed in memory
to prove preservation, but only explicitly enrolled values appear in plans/journals. No full-file backup,
unmanaged value dump, telemetry, runtime Store or global instruction mutation is made.

## Lifecycle and authorization

1. Investigate the experience problem and locate the owning configuration layer. Preserve unknown causes.
2. `config preview` reads only the explicit existing `config.toml` and transaction metadata. It writes
   nothing. Show the exact path, source, field before/after values and risks to the user.
3. `config apply` requires both `--plan-hash` and `--approval-ref`, regenerates the plan under the shared
   target lock, and rejects any stale bytes, policy, context or transaction. There is no auto approval.
   The approval reference points to explicit user authorization of that exact plan, including any security
   change and supersession of the previous recovery delta. It is caller-supplied authorization evidence,
   not a generated token or cryptographic proof of a human click. Integrators must enforce the user
   boundary; merely running a test or supplying a fabricated reference does not authorize deployment.
   These references are separate from Core rule Hook approval events; this API does not consume those.
   Plans and results explicitly report `authorization_evidence_verification=external_reference_not_verified`;
   a nonempty string is never reported as independently verified human approval.
4. Write durable intent, recheck target bytes, atomically replace, read back exact bytes, mark applied.
   File success is `file_applied`; effective values remain `unknown`, consumer verification `unverified`.
5. Read effective values and validate the actual consumer entrance in a separately authorized run.
   `config verify` reports file match independently and can compare a bounded external observation.
6. Retain justified experience through its actual owner, or preview and approve latest-delta restoration.
   No retained behavioral rule is silently authored by this configuration engine.

Example command forms (placeholders, not deployment authorization):

```text
agent-memory config preview --source <checkout> --source-commit <40-hex> --policy-file <relative.json> --target-file <explicit-config.toml> --platform <exact> --codex-version <exact>
agent-memory config apply <same-source-and-target-arguments> --plan-hash <reviewed-hash> --approval-ref <explicit-approval-evidence>
agent-memory config verify <same-source-and-target-arguments> [--observation-file <non-secret.json>]
agent-memory config reconcile --target-file <explicit-config.toml>
agent-memory config restore-preview --target-file <explicit-config.toml>
agent-memory config restore --target-file <explicit-config.toml> --plan-hash <reviewed-restore-hash> --approval-ref <explicit-restore-approval>
```

Top-level CLI responses retain `agent_memory_result_v1`; the data object's status expresses the evidence
level. CLI errors do not assert zero external effect. After any interrupted mutation, reconcile first.

## Field patch and recovery boundary

The first implementation supports existing single-line scalar assignments at top level or in explicit
simple tables, and insertion of missing fields at top level or into one existing simple table. It does
not create tables/files/homes, normalize the document, edit inline tables/dotted or quoted key spellings,
or rewrite multiline values. Unsupported target syntax fails without mutation. Every candidate patch
is reparsed and compared with the original full TOML tree with type-sensitive values; only the enrolled
path can differ. Unknown arrays, tables, dates, comments, line endings and values remain intact.
Symlink, hardlink, reparse and unsafe parent paths use existing Sidecar physical-file checks.

One shared sibling `.agent-memory-config.lock` serializes Sidecar writers for the target. The sibling
`.agent-memory-config-transaction.json` contains only the latest field delta, original scalar literals,
exact plan binding, state and approval references. Its plan checksum detects corruption (not a malicious
local actor who can rewrite both metadata and hash). It is local recovery material, never a policy owner.
The lock file is retained for stable lock identity; unlinking a live lock can create split ownership.

A `prepared` or `restore_prepared` transaction blocks fresh apply. Restoration writes durable
`restore_prepared` intent, its exact restore plan and external approval reference before changing the
target. A before/after replacement interruption therefore cannot be mistaken for a completed active
configuration revision. `reconcile` is read-only, reports full-file before/after/drifted
and each field's before/after/conflict position, and never replays. After interruption before replacement,
an approved restore can retire the empty effect; after replacement, it can undo the matching fields.
After reconciliation, restoration regenerates an exact plan against current bytes and journal hash;
any new restore plan requires explicit approval of that precise plan. It reverts only fields
still matching the transaction's written value, preserves unrelated later edits, skips already-original
fields and rejects conflicting managed fields as a whole. Original scalar literals are restored; inserted
assignments are removed while preserving user-added inline comments as comment lines.
Changed managed values require a new decision, not a force override.
An applied next revision explicitly binds the previous journal hash and supersedes its recovery delta;
only that latest delta remains restorable. This is a bounded recovery mechanism, not configuration history.
Removing a field from source policy does not silently delete its local value; retiring an installed value
requires an explicitly reviewed restoration or a separately reviewed change by its actual owner.

Atomic replace prevents partial TOML files. Cooperative locking and immediate prewrite checks detect
observed drift; there is no OS-wide compare-and-swap against an uncooperative editor writing in the tiny
check/replace interval. Close other writers for a real approved apply. Readback failure retains recovery
intent and must not trigger automatic overwrite/rollback of a concurrent user's work.

## Effective values and consumer evidence

The engine does not infer Codex precedence or execute a shell probe. Unknown managed policy, profile,
CLI/session overrides remain listed as unobserved sources. An optional external observation has:

```json
{
  "target_sha256": "<observed-file-hash>",
  "platform": "fixture-platform",
  "codex_version": "fixture-version",
  "entrypoint": "specific actual consumer entrance",
  "evidence_ref": "non-secret observation evidence",
  "fields": [{"path": ["fixture_option"], "value": "fixture-value"}]
}
```

The target hash, platform, version, entrypoint, evidence reference and exact enrolled field set must match.
Results are `reported_match` or `reported_differ` and `externally_reported`; they describe caller-supplied
evidence, not an independently attested live observation. Without that evidence, effective values stay
unknown even when file values match. Neither mode asserts later adoption, experience improvement,
installation, publication, diagnosis completion or resolution of a Windows policy block.

## Offline acceptance

[Regression fixtures](../tests/test_config_sync.py) cover committed source selection, CLI lifecycle,
read-only discovery, preservation, applicability, stale approvals, type-sensitive conflicts, unsupported
syntax, physical aliases, corruption, before/after replacement interruption and bounded restoration.
Tests use temporary non-secret repositories/configs and never load the real host configuration.
