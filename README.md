# Agent Memory Sidecar

Agent Memory Sidecar is an authorized bounded collaboration-rule publisher for Codex:

```text
authorize -> validate scope -> publish to AGENTS.md -> adopt in a later task -> revoke
```

It is not a general memory database. The `AGENTS.md` file Codex actually loads is
the only behavior authority. SQLite stores bounded runtime events, ephemeral
proposal tokens, authorization consumption, and installation metadata; it never
stores an approved rule as a second behavior owner.

The managed block is a bounded behavior-delta set, not an append-only rule
history. Before proposing a mutation, the Agent compares the candidate with the
actual rules and project authority already loaded for the task. Existing
coverage is a no-op, corrections replace prior rules, and overlapping rules may
be consolidated only through one exact user-authorized before/after revision.

Read the normative design in [L1 axioms](docs/specs/axioms.md),
[L2 topology](docs/specs/topology.md), and [L3 interface](docs/specs/interface.md).
The detailed machine contract is [Agent Memory Core v1](specs/agent-memory-core-v1.md);
the decisions are [ADR 0057](docs/decisions/0057-agent-memory-core-v1.zh.md),
[ADR 0059](docs/decisions/0059-bounded-behavior-set-evolution.zh.md), and
[ADR 0074](docs/decisions/0074-public-operations-closure.zh.md).

## Product boundary

- Stable Core: explicit authorization, deterministic scope validation, deploy,
  list, edit, and revoke.
- Experimental: ambient discovery and the one-card proposal flow. Failure here
  does not block Core and must not be described as proven.
- Public Core distribution: wheel/sdist contain the deterministic Python Core
  and CLI only. A separate versioned bundle contains Plugin and Skills.
- Optional Owner integration: users may bind their own commit-bound private
  global `AGENTS.md` source; the local `~/.codex/AGENTS.md` remains the runtime
  owner. Public Core mode does not search for or invent an Owner.
- Optional background: native Memories may be disabled without changing
  mandatory rule behavior.

A proposal has exactly seven fields:

```json
{
  "trigger": "when this applies",
  "action": "what to do",
  "skip_boundary": "when not to apply",
  "scope": "project",
  "why": "why this reduces future repetition",
  "evidence": "current-task evidence",
  "instruction_target": "project_agents"
}
```

Only `When / Do / Skip` and the derived `rule_id` are persisted to the managed
instruction block. A rule is `生效中` only when it is parsed from the actual
target and is not shadowed by `AGENTS.override.md`.

## CLI

```powershell
python -m agent_memory_sidecar rule list
python -m agent_memory_sidecar rule list --target global_agents
python -m agent_memory_sidecar rule deploy --from-json .\rule.json --approval-ref <current-ref>
python -m agent_memory_sidecar rule deploy-bundle --from-json .\bundle.json --approval-ref <current-ref>
python -m agent_memory_sidecar rule deploy --from-json .\revised.json --approval-ref <current-ref> --supersedes <rule_id>
python -m agent_memory_sidecar rule deploy --from-json .\merged.json --approval-ref <current-ref> --supersedes <first_rule_id> --supersedes <second_rule_id>
python -m agent_memory_sidecar rule revoke <rule_id> --approval-ref <current-ref>
python -m agent_memory_sidecar setup
python -m agent_memory_sidecar setup --apply
python -m agent_memory_sidecar doctor
```

`approval-ref` is opaque Hook context for the current user prompt. It must not be
invented or shown in normal user interaction. All JSON commands return
`agent_memory_result_v1`; exit code `0` means success/idempotent no-op and `1`
means failure.

`rule list` reports managed-block usage, the unchanged 8 KiB budget, remaining
bytes, complete document bytes, and rule count for both project and global
targets. Complete document size is visibility only and never grants Sidecar
ownership of bytes outside the managed block.

`rule deploy-bundle` accepts one or more unique proposals for the same scope and
instruction target, consumes one approval for the exact aggregate revision, and
applies the complete ruleset change atomically. Any stale, conflicting, invalid,
over-capacity, or failed item leaves every target unchanged.

## Install and use

For normal Codex Desktop use, register the immutable repository Marketplace,
install the Agent Memory plugin, restart Desktop, and begin a new task:

```powershell
codex plugin marketplace add lly-personal/agent-memory-sidecar --ref v0.3.6
codex plugin add agent-memory-sidecar@agent-memory
```

After Codex refreshes the installed Plugin, start one task and send `同步并部署本机 Agent Memory`. The Anchor resolves and
verifies the immutable public Release, safely materializes its portable bundle, and runs the formal Bootstrap in that same task.
Fresh and same-source hosts complete directly; an existing Sidecar identity replacement shows one short plan and consumes one
confirmation. Host source sync, Core/Owner/Skill materialization, and Doctor finish before the result is returned. One later Codex
refresh or new task is needed only for automatic discovery of the newly installed Skills.
Marketplace registration and a repository checkout are discovery surfaces;
they are not source authority and do not by themselves prove host deployment.

For Core-only CLI use, install the wheel from the same Release, then preview and
apply setup:

```powershell
python -m pip install .\agent_memory_sidecar-0.3.6-py3-none-any.whl
agent-memory --help
agent-memory setup
agent-memory setup --apply
agent-memory doctor
```

`setup --apply` without `--global-rules-source` is the supported public Core
profile. Project-scope rules, immutable Runtime installation, Store integrity,
and Doctor remain available; global publication and Scout Owner parity are
explicitly unavailable. Owner-integrated installations provide a separate clean
Git checkout and bind it explicitly.

Workstation Bootstrap 1.9 accepts `agent_memory_source_manifest_v1`. Release
manifests bind each source to both a ref and a full commit SHA; an optional
`canonical_owner` is `null` in the public profile. On an existing host that means “the release does not distribute an Owner”, not
“detach the current Owner”: a clean managed Owner is preserved only when Core is bound to that exact root and commit. Floating branches are a
development convenience and are never accepted as public release evidence.

An existing host that still has a managed Sidecar from another repository must
not use normal sync to replace it. The unified deployment flow reviews and applies the explicit
[`source-authority-cutover-v2`](specs/source-authority-cutover-v2.md) plan; an
existing private Owner remains a separate optional backend unless explicitly
detached.

## Open-source release boundary

Project source was initially published through an allowlisted export from a
separate, history-bearing engineering repository. The public checkout excludes host
state, private Owner identities, historical runtime evidence, and unknown
files. Core packages and the portable Plugin/Skill bundle are separate
artifacts connected by `COMPATIBILITY.md`, a release manifest, checksums, and
installed-runtime smoke tests.

The export was a one-time seed and provenance path, not a permanent mirror.
Public `main` is now the sole home for code, specifications, issues, pull
requests, CI, tags, and releases. The former private engineering repository is
frozen read-only history and rollback evidence; future product changes never
flow from it back into this repository. See
[`specs/public-authority-cutover-v1.md`](specs/public-authority-cutover-v1.md).

## Contribute

Clone public `main`, create a `codex/` or topic branch, and work in that checkout.
Editable installation is contributor-only and must not be used as evidence for
the released consumer path. See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Desktop setup guide](docs/codex-desktop-setup.md).

The public checkout's root `LICENSE` and `pyproject.toml` SPDX metadata are the
authoritative license declaration. The export and release path fails closed
when either is absent or inconsistent; files outside the allowlisted public
checkout are not part of the open-source distribution.

See [SECURITY.md](SECURITY.md), [PRIVACY.md](PRIVACY.md), and [THREAT_MODEL.md](THREAT_MODEL.md) for disclosure, local-data, and
trust boundaries.

## Desktop runtime

`setup --apply` builds a content-addressed zipapp using the Python standard
library, self-tests it, and points exactly two Hook entries at that immutable
artifact:

- `UserPromptSubmit` stores only a bounded envelope and prompt hash, then
  transports the fixed capability.
- `SessionStart(source=compact)` read-only retransports the capability associated
  with the current scope-matching prompt event.

Hooks do not classify prompts, approve rules, store proposal bodies, query
approved memories, or render cards. During Core cutover the maintenance lock
makes normal Hook invocation fail open.

`setup` never upgrades a legacy Store. The migration is an explicit two-step
maintenance operation:

```powershell
python -m agent_memory_sidecar maintenance core-cutover --dry-run
python -m agent_memory_sidecar maintenance core-cutover --apply --plan-hash <hash> --approval-ref <current-ref>
```

Apply requires a separately authorized current prompt. It creates a permanent
full backup plus checksum, builds and verifies the seven-table Core Store beside
the old database, then replaces Store and Hook configuration with rollback on
failure.

## Verification

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -v
python scripts/check_doc_links.py
git diff --check
python -m agent_memory_sidecar doctor
```

Automated checks prove contracts, storage, publication transactions, packages,
and configured runtime at their own evidence layer. Only real new Codex Desktop
tasks can prove rule adoption and post-revoke continuity. Export verification,
repository visibility, a version tag, a Release, registry publication, and
engineering-authority cutover remain separately verified facts.
