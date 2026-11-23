from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from .errors import CoreError
from .file_security import (
    assert_physical_directory_chain,
    assert_physical_regular_file,
    logical_absolute,
    read_physical_regular_bytes,
)


SKILL_NAME = "agent-memory"
CLI_ENTRY = "scripts/agent-memory.py"
CLI_COMMAND = '"<python>" -B "<skill-dir>/scripts/agent-memory.py"'
DAILY_SKILL_EXCLUDED_MODULES = frozenset({"core_cutover.py", "instruction_sync.py"})


@dataclass(frozen=True)
class SkillPlan:
    path: Path
    action: str
    canonical_sha256: str
    installed_sha256: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "path": str(self.path),
            "action": self.action,
            "canonical_sha256": f"sha256:{self.canonical_sha256}",
            "installed_sha256": (
                f"sha256:{self.installed_sha256}"
                if self.installed_sha256
                else None
            ),
        }


@dataclass(frozen=True)
class SkillSnapshot:
    path: Path
    existed: bool
    backup_root: Path
    backup_path: Path


def default_user_skill_root() -> Path:
    configured = os.environ.get("CODEX_HOME")
    codex_home = logical_absolute(configured if configured else Path.home() / ".codex")
    return codex_home / "skills"


def legacy_shared_skill_root() -> Path:
    return logical_absolute(Path.home() / ".agents" / "skills")


def skill_tree_sha256(path: Path) -> str | None:
    logical = logical_absolute(path)
    if _assert_skill_directory_chain(logical.parent, allow_missing_tail=True) is None:
        return None
    if not _physical_skill_directory_exists(logical):
        return None
    values: dict[str, str] = {}
    for item in _skill_tree_files(logical):
        existed, data = read_physical_regular_bytes(
            item,
            allow_missing_parent=False,
            unsafe_code="skill_target_unsafe",
            unsafe_message="Skill tree contains an unsafe file",
            unavailable_message="Skill file cannot be read",
        )
        if not existed:
            return None
        try:
            values[item.relative_to(logical).as_posix()] = data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return skill_package_sha256(values)


def looks_like_sidecar_skill(path: Path) -> bool:
    logical = logical_absolute(path)
    try:
        if _assert_skill_directory_chain(logical.parent, allow_missing_tail=True) is None:
            return False
        if not _physical_skill_directory_exists(logical):
            return False
        existed, data = read_physical_regular_bytes(
            logical / CLI_ENTRY,
            allow_missing_parent=True,
            unsafe_code="skill_target_unsafe",
        )
        if not existed:
            return False
        text = data.decode("utf-8", errors="ignore")
        return "agent_memory_sidecar.cli" in text and "daily_only=True" in text
    except CoreError:
        return False


def _create_staging_dir(parent: Path, *, prefix: str) -> Path:
    """Create a sibling staging directory inheriting parent ACLs/umask.

    Avoids ``tempfile.mkdtemp()`` because Python 3.12+ applies a protected
    owner-only DACL on Windows that strips inherited ``CodexSandboxUsers`` read
    permissions when swapped into ``$CODEX_HOME/skills/agent-memory``.
    """
    for _ in range(64):
        candidate = parent / f"{prefix}{secrets.token_hex(8)}"
        try:
            os.mkdir(candidate)
            return candidate
        except FileExistsError:
            continue
    raise CoreError(
        "skill_target_unsafe",
        "Skill staging directory cannot be created exclusively",
        path=str(parent),
    )


def stage_legacy_skill_removal(path: Path) -> SkillSnapshot:
    logical = logical_absolute(path)
    _assert_skill_directory_chain(logical.parent, allow_missing_tail=False)
    if not _physical_skill_directory_exists(logical):
        backup_root = _create_staging_dir(
            logical.parent,
            prefix=f".{SKILL_NAME}.legacy-migration.",
        )
        return SkillSnapshot(logical, False, backup_root, backup_root / SKILL_NAME)
    backup_root = _create_staging_dir(
        logical.parent,
        prefix=f".{SKILL_NAME}.legacy-migration.",
    )
    backup_path = backup_root / SKILL_NAME
    snapshot = SkillSnapshot(logical, True, backup_root, backup_path)
    try:
        os.replace(logical, backup_path)
    except BaseException:
        discard_skill_snapshot(snapshot)
        raise
    return snapshot


def _assert_skill_directory_chain(path: Path, *, allow_missing_tail: bool) -> os.stat_result | None:
    return assert_physical_directory_chain(
        path,
        allow_missing_tail=allow_missing_tail,
        missing_code="skill_target_unsafe",
        unsafe_code="skill_target_unsafe",
        missing_message="Skill directory is missing",
        unsafe_message="Skill directory contains a filesystem alias",
        unavailable_message="Skill directory metadata is unavailable",
    )


def _skill_tree_files(path: Path) -> list[Path]:
    _assert_skill_directory_chain(path, allow_missing_tail=False)
    files: list[Path] = []

    def failed(exc: OSError) -> None:
        raise CoreError(
            "skill_target_unsafe",
            "Skill tree cannot be enumerated safely",
            path=str(path),
        ) from exc

    for current_raw, directory_names, file_names in os.walk(
        path,
        topdown=True,
        onerror=failed,
        followlinks=False,
    ):
        current = Path(current_raw)
        _assert_skill_directory_chain(current, allow_missing_tail=False)
        for name in sorted(directory_names):
            _assert_skill_directory_chain(
                current / name,
                allow_missing_tail=False,
            )
        for name in sorted(file_names):
            item = current / name
            assert_physical_regular_file(
                item,
                allow_missing=False,
                allow_missing_parent=False,
                missing_code="skill_target_unsafe",
                unsafe_code="skill_target_unsafe",
                unsafe_message="Skill tree contains an unsafe file",
                unavailable_message="Skill file metadata is unavailable",
            )
            files.append(item)
    return files


def _physical_skill_directory_exists(path: Path) -> bool:
    logical = logical_absolute(path)
    _assert_skill_directory_chain(logical.parent, allow_missing_tail=False)
    return _assert_skill_directory_chain(logical, allow_missing_tail=True) is not None


def build_skill_files() -> dict[str, str]:
    return {
        "SKILL.md": _skill_markdown().replace("agent-memory ", CLI_COMMAND + " "),
        "agents/openai.yaml": (
            "interface:\n"
            "  display_name: Agent Memory\n"
            "  short_description: Publish authorized collaboration rules.\n"
        ),
        CLI_ENTRY: (
            "import sys\n"
            "sys.dont_write_bytecode = True\n"
            "from agent_memory_sidecar.cli import main\n"
            "raise SystemExit(main(daily_only=True))\n"
        ),
        **{
            f"scripts/agent_memory_sidecar/{path.name}": path.read_text(encoding="utf-8")
            for path in sorted(Path(__file__).parent.glob("*.py"))
            if path.name not in DAILY_SKILL_EXCLUDED_MODULES
        },
    }


def skill_package_sha256(files: dict[str, str] | None = None) -> str:
    digest = hashlib.sha256()
    for relative, content in sorted((files or build_skill_files()).items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def installed_skill_sha256(path: Path) -> str | None:
    logical = logical_absolute(path)
    if _assert_skill_directory_chain(logical.parent, allow_missing_tail=True) is None:
        return None
    if not _physical_skill_directory_exists(logical):
        return None
    expected = build_skill_files()
    values: dict[str, str] = {}
    for relative in expected:
        existed, data = read_physical_regular_bytes(
            logical / relative,
            allow_missing_parent=True,
            unsafe_code="skill_target_unsafe",
            unsafe_message="Skill tree contains an unsafe file",
            unavailable_message="Skill file cannot be read",
        )
        if not existed:
            return None
        try:
            values[relative] = data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if set(
        item.relative_to(logical).as_posix()
        for item in _skill_tree_files(logical)
    ) != set(expected):
        return None
    return skill_package_sha256(values)


def plan_skill_install(*, root: Path | None = None) -> SkillPlan:
    skill_root = logical_absolute(root or default_user_skill_root())
    _assert_skill_directory_chain(skill_root, allow_missing_tail=True)
    target = skill_root / SKILL_NAME
    canonical = skill_package_sha256()
    installed = installed_skill_sha256(target)
    return SkillPlan(
        path=target,
        action="noop" if installed == canonical else "install",
        canonical_sha256=canonical,
        installed_sha256=installed,
    )


def snapshot_skill(*, root: Path | None = None) -> SkillSnapshot:
    path = plan_skill_install(root=root).path
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_skill_directory_chain(path.parent, allow_missing_tail=False)
    backup_root = _create_staging_dir(
        path.parent,
        prefix=f".{SKILL_NAME}.setup-snapshot.",
    )
    backup_path = backup_root / SKILL_NAME
    existed = _physical_skill_directory_exists(path)
    if existed:
        shutil.copytree(path, backup_path, symlinks=True)
    return SkillSnapshot(path, existed, backup_root, backup_path)


def restore_skill(snapshot: SkillSnapshot) -> None:
    if _physical_skill_directory_exists(snapshot.path):
        shutil.rmtree(snapshot.path)
    if snapshot.existed:
        _physical_skill_directory_exists(snapshot.backup_path)
        os.replace(snapshot.backup_path, snapshot.path)
    discard_skill_snapshot(snapshot)


def discard_skill_snapshot(snapshot: SkillSnapshot) -> None:
    if _physical_skill_directory_exists(snapshot.backup_root):
        shutil.rmtree(snapshot.backup_root, ignore_errors=True)


def install_skill(*, root: Path | None = None) -> SkillPlan:
    plan = plan_skill_install(root=root)
    if plan.action == "noop":
        return plan
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    _assert_skill_directory_chain(plan.path.parent, allow_missing_tail=False)
    backup = plan.path.parent / f".{SKILL_NAME}.previous"
    if _physical_skill_directory_exists(backup):
        if _physical_skill_directory_exists(plan.path):
            shutil.rmtree(backup)
        else:
            os.replace(backup, plan.path)
    stage: Path | None = _create_staging_dir(
        plan.path.parent,
        prefix=f".{SKILL_NAME}.",
    )
    _physical_skill_directory_exists(stage)
    installed_new = False
    try:
        for relative, content in build_skill_files().items():
            assert stage is not None
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        if _physical_skill_directory_exists(plan.path):
            os.replace(plan.path, backup)
        assert stage is not None
        os.replace(stage, plan.path)
        stage = None
        installed_new = True
        if installed_skill_sha256(plan.path) != plan.canonical_sha256:
            raise RuntimeError("installed Agent Memory Skill checksum mismatch")
        if _physical_skill_directory_exists(backup):
            shutil.rmtree(backup)
        return plan_skill_install(root=root)
    except BaseException:
        if installed_new and _physical_skill_directory_exists(plan.path):
            shutil.rmtree(plan.path)
        if _physical_skill_directory_exists(backup) and not _physical_skill_directory_exists(plan.path):
            os.replace(backup, plan.path)
        raise
    finally:
        if stage is not None and _physical_skill_directory_exists(stage):
            shutil.rmtree(stage, ignore_errors=True)


def _skill_markdown() -> str:
    return """---
name: agent-memory
description: Manage collaboration rules when the user asks to remember, view, audit, edit or revoke one, or replies to a pending memory proposal. Also use after a concrete correction or stated preference applies to future tasks, even without a remember command. Do not use for one-off instructions, project-owned facts, transient failures, guesses, secrets, ordinary continuation, status, or routine Git work.
---

# Agent Memory

North star: `discover -> authorize -> deploy -> later-task behavior -> revoke`.

## Installed command entry

Resolve `<skill-dir>` from the actual loaded path of this SKILL.md and `<python>` from an available
Python 3.11+ interpreter on this host. Use command lookup and check its version first; do not guess a system path.
Replace both placeholders with observed absolute paths in every command below. Execute from the current
primary project directory and preserve its active CODEX_HOME. In PowerShell, prefix each quoted interpreter
command with the call operator `&`; POSIX shells execute the quoted path directly. The installed script includes the Core;
do not depend on a global console command, pip installation, source checkout or PYTHONPATH injection.
Keep `-B` so running the Skill does not change its installed content. This entry uses the existing Store,
authorization and Owner contracts; it does not grant permission to modify a real Owner during testing.
Only rule, proposal and doctor operations are available here. Installation and instruction synchronization
remain with the verified Bootstrap; do not run setup from this installed projection.

## Task boundary and visibility

Finish the current task before any Agent Memory process commentary. The description above is the single admission rule; if it does not apply, remain completely silent and do not create a proposal.

Once this Skill is invoked, or the Agent tells the user that Agent Memory will be, is being, or was used, the final reply must end with exactly one real terminal artifact from **Terminal outcomes**. Commentary, capability delivery, a command starting, or a future-tense promise is never a result. If the host requires announcing implicit Skill use, announce it only after the current task is complete, then immediately continue through classification and zero or one mutation; the announcement never replaces the final artifact.

Never expose event refs, tokens, internal commands, raw JSON, or diagnostic labels to the user.

## Admission

Mechanism development and its design corrections belong to project authority. Approval to improve or test the mechanism, or agreement with a candidate's value, does not authorize a formal Owner update. During engineering validation, exercise writes and revocation against isolated Owner, Store and test-event fixtures. If the user defers real use or acceptance, stop at technical delivery and do not reuse an earlier candidate confirmation to continue deployment. A test result neither grants production permission nor proves user acceptance.

Distinguish a future collaboration preference from an instruction for this output only. A concrete future preference can qualify for a proposal without the word "remember"; it does not itself authorize deployment. Finish the ordinary task, inspect current coverage, then preview and create at most one proposal. Do not ask the user to repeat the preference as a remember command before showing that proposal.

Requests to view, edit or revoke existing rules and replies to the current proposal are operations, not new candidates. Read current state and use the matching explicit or proposal command below. Resolve a natural-language revocation against the actual rules; an unambiguous request authorizes that scoped removal once, without another confirmation or a new proposal. Ambiguous targets remain unresolved. Confirm a pending proposal with the same rule content and the current reply's event; never replace confirmation with direct deployment. After mutation, read the actual target before reporting success.

Before classifying an eligible candidate, including `already_covered`, inspect the actual rules with `agent-memory rule list`; when the target is already known, use `--target global_agents|project_agents` so an unrelated target cannot block the Fresh read. Reread any actual authority used to claim coverage; earlier conversation text or a previous file read does not prove its current contents. Compare only with the current instruction chain and project-authority documents already required for the task. Do not scan the whole project.

Classify the candidate once:

- `no_candidate`: an explicit audit found no evidenced reusable behavior. Do not create a token or write a file.
- `already_covered`: the behavior is already enforced by an actual rule or loaded project authority. Do not create a token or write a file.
- `add`: a genuinely independent collaboration behavior.
- `replace`: a correction to one existing rule; bind that rule with one `--supersedes`.
- `consolidate`: one rule replaces multiple overlapping rules; bind every affected rule with repeated `--supersedes` and show one exact before/after card.
- `route_to_owner`: project facts, design, status, safety boundaries, or current plans belong to their project owner, not the managed block.

If the relation is uncertain, show a clarification draft only. Never create a token for `no_candidate`, `already_covered`, or `route_to_owner`, and never delete or consolidate rules without explicit authorization. Because invoking the Skill makes the mechanism user-visible, every classification must use its matching terminal outcome; do not silently exit after `rule list`.

## Capacity preflight and formal Owner delivery

Owner placement follows the content's authority, not spare bytes. An independent must-apply behavior belongs in `AGENTS.md`; project facts, specifications and detailed procedures belong in their existing formal Owner or Skill. Capacity alone never justifies moving mandatory behavior to optional memory or appending it outside the managed block.

1. Resolve the actual target from `rule list` and the current binding. For global changes, verify canonical/local parity and preview the effective host `AGENTS.md` target so override checks use the same context as deployment. The canonical source checkout is the publication Owner, not the host override context; an arbitrary `--target-file` is not proof of binding or authorization.
2. Before creating or confirming a proposal or performing an explicit deploy, run `agent-memory rule preview --target-file <observed-owner> --from-json '<same-json>' [--supersedes <rule-id>]...`. For a selected bundle, use `agent-memory rule preview-bundle --target-file <observed-owner> --from-json '<same-bundle-json>'` with the exact selection. Both entries are read-only: no Store, token, approval consumption or file mutation.
3. Read both `capacity.rules` and `capacity.managed_block`; a blocked result is not deployable. Rule bytes use normalized UTF-8 LF; block bytes use the target's physical LF/CRLF, including markers, headings and separators. The 1,024/8,192-byte budgets are revisitable engineering limits, not host document limits or proven optimal values.
4. For consolidation or routing, map every old obligation, trigger and exception to its exact retained rule or Owner section. Preserve independently applicable requirements and all exceptions; shorter wording and a passing byte count do not prove semantic equivalence. Do not split rules, drop boundaries or force an unrelated Owner just to fit. If the necessary set still exceeds budget, report it undeployed and propose an explicit budget/design review.
5. `route_to_owner` is only a placement decision. Complete authorized ordinary project edits in the formal Owner and read back its exact path/section. For mandatory behavior, also deploy or verify an applicable, unshadowed `AGENTS.md` trigger that requires reading that Owner before acting. A link without a mandatory trigger is insufficient. Reuse existing authorization within its scope; ask only if the new content, superseded set, Owner scope or operation materially exceeds it. Owner routing does not create a second memory-governance service.
6. After authorized deployment, read back the actual instruction target and routed Owner, checking the obligation map, untouched rules and outside bytes. Report routing proposed, Owner content landed, mandatory entry deployed, and later adoption separately. For facts or specifications without mandatory behavior, Owner read-back completes content delivery without claiming a deployed rule. Preview is not deployment, publication, model adoption or continuity; the mutating command replans under its existing authorization and lock checks.

Never substitute optional Memories, a local note, a summary, a saved draft, or a direct AGENTS.md edit for formal behavior-rule deployment. Use the Core commands below for these rules; `route_to_owner` is not a fallback for a missing event or failed command. If the current host event is unavailable, leave rule storage unchanged and report that the actual user entry remains unverified; do not reconstruct an event or approval from logs or Store rows. If any Owner or note was nevertheless changed, report that exact mutation instead of using an unchanged-state receipt. Do not change live Owners or installations during mechanism engineering validation.

## Proposal

Build exactly these seven fields: `trigger`, `action`, `skip_boundary`, `scope`, `why`, `evidence`, `instruction_target`.

- Default to `scope=project` and `instruction_target=project_agents`.
- Use `global/global_agents` only after explicit cross-project authorization.
- Do not persist prompt text, response text, `why`, or `evidence`.
- If any field needs inference, show a clarification draft only. It is not `待确认`.

Use one standalone command in the current primary project directory:

- Create: `agent-memory proposal create --source-event user_prompt:<event-id> --from-json '<json>' [--supersedes <rule-id>]...`
- Replace: `agent-memory proposal replace --source-event user_prompt:<event-id> --from-json '<json>' [--supersedes <rule-id>]...`
- Confirm: `agent-memory proposal confirm --approval-ref user_prompt:<event-id> --from-json '<same-json>' [--supersedes <same-rule-id>]...`
- Discard: `agent-memory proposal discard --approval-ref user_prompt:<event-id>`

Show at most one card, after create succeeds:

> **记忆建议**（本项目 / 跨项目）
> {action}（适用：{trigger}；不适用：{skip_boundary}）
> 回复 **记住** / **修改：…** / **忽略**。当前尚未写入，现有规则未变更。

## Scout bundle handoff

When the user confirms one or more cards from the current Global Owner Scout Review Pack, treat the exact selected card set as one operation. A single selected card is a bundle of size one.

For an interactive task-artifact selection, use the installed Scout's `recover-delivery --artifact-root <original-host-output-root>` with the original native `prepare-delivery` manifest. Its `verify-final` entry remains a legacy adapter for the original artifact link and manifest hash. Bind an explicitly selected report with `--report-hash` (the Review Pack hash), then use the recovered `recovery_bundle` and read selected cards from that same immutable artifact. Do not regenerate discovery, manufacture provenance from a candidate file or trust a copied summary. Recovery only attests artifact data; titles, formatting, surface claims and confirmation hints neither block valid recovery nor grant approval. Correct inaccurate copy without discarding verified evidence. Preserve actual queued/display observations separately. Only a new explicit human selection of the exact content-bound pairs may resume this handoff after artifact verification; apply every Fresh Owner and Core check below. Do not ask the user to switch windows or send an additional acknowledgement. A missing, changed, unrelated or ambiguously selected artifact blocks the affected selection, and tool-relayed text is not a human approval event. Scheduled inline selections retain their original validated Review Pack and visible-output verification; they do not require an interactive artifact. If exact original bundle bindings are unavailable, do not guess or reuse old tokens: refresh only the affected preview and obtain authorization for that changed content.

1. Accept only the exact `card_id@selection_token` pairs from the same Review Pack, scope, and instruction target. The current user reply must be the canonical `确认 <card_id>@<token>[、...]` command or that complete command with every `@` escaped once as Markdown `\\@`. Preserve the original user event; do not rewrite the prompt or mix confirmation with edit, routing, or ignore actions.
2. Reread that target with `agent-memory rule list --target <instruction-target>`, verify canonical/local parity when global, and jointly recompute every selected card against the same Owner snapshot and against the other selected cards.
3. Run the exact bundle preflight above. If blocked, execute no mutation and report its precise failure. If any relation, rule text, superseded set, or Owner target changes materially, execute no mutation. Show one refreshed aggregate before/after and ask once for confirmation of that changed bundle.
4. Otherwise execute exactly one standalone command: `agent-memory rule deploy-bundle --approval-ref user_prompt:<event-id> --from-json '<rule_revision_bundle_v2-json>'`. Include each card/project claim, proposal, sorted supersedes and selection token plus the complete target before hash; Core recomputes all bindings.
5. Never loop over `rule deploy`, derive child approvals, or leave a partially deployed selected set. The bundle succeeds completely or changes no Owner bytes.
6. After success, unselected Project Cards keep their immutable project evidence; only their integration previews are stale. Rebase them when later selected. Do not rerun project discovery unless project evidence itself changed.

## Explicit operations

- Deploy: `agent-memory rule deploy --approval-ref user_prompt:<event-id> --from-json '<json>'`
- Deploy selected Scout cards atomically: `agent-memory rule deploy-bundle --approval-ref user_prompt:<event-id> --from-json '<rule_revision_bundle_v2-json>'`
- Edit: add one `--supersedes <rule-id>` to deploy.
- Consolidate: repeat `--supersedes <rule-id>` for every replaced rule.
- View: `agent-memory rule list`
- Revoke: `agent-memory rule revoke <rule-id> --approval-ref user_prompt:<event-id>`

An unambiguous explicit remember utterance is the one authorization; do not ask twice. Echo the final `When / Do / Skip / scope`, preflight and deploy within that authorization, and use the deployed terminal outcome only after the actual target is parsed and unshadowed. A proposal confirmation follows the same success outcome. For global results, complete the ordinary private-Git commit/push workflow when `publication_required=true`; local effect and cross-device publication are separate evidence.

On failure, preserve the completed task result and state only `未保存`, `未部署`, or `未证明` as supported. Exception: `instruction_cleanup_required` with `operation_committed=true` means the mutation and approval consumption completed. Read actual targets with `rule list`, report their actual state plus pending transaction cleanup, and never retry the consumed approval or claim unchanged/undeployed. A current task may retain already-loaded instructions after revoke; verify a new task before claiming continuity.

## Terminal outcomes

The terminal artifact is the last user-facing Agent Memory block in the final reply. Keep ordinary work completely silent. When a visible flow runs, use one concise plain-Chinese outcome below (replace only braced user-readable summaries; never leak internal tokens, hashes, or raw JSON):

- Explicit audit with no candidate: `本次核查未发现需要沉淀的新规则，未创建建议，现有规则未变更。`
- Covered by actual authority: `该要求已被当前规则覆盖，未创建建议，现有规则未变更。`
- Routing proposed but not implemented: `该内容更适合留在{正式 owner}，未新增长期行为规则，现有规则未变更。`
- Owner content landed, mandatory entry still missing or failed: `交付未完成：已写入{正式 owner}，但必需的行为入口尚未部署。`
- Owner content landed with no mandatory behavior required: `已写入{正式 owner}，无需新增行为规则。`
- Proposal created: show the confirmation card above (its final line explicitly states `当前尚未写入，现有规则未变更。`).
- Explicit deploy or proposal confirmation succeeded: after echoing `When / Do / Skip / scope`, `已写入{范围}规则，当前生效中（后续新任务采用待观察；随时可说“查看/撤销规则”）。`
- Atomic Scout bundle succeeded: after echoing every selected `When / Do / Skip / scope`, `已整包写入 {数量} 条{范围}规则，当前生效中（后续新任务采用待观察）。`
- Revoke succeeded: `已从{范围}规则撤销（当前会话可能仍保留先前已加载的指令，新任务起生效）。`
- Clarification required: after the draft, `需要确认：{待澄清内容}。当前未创建建议，现有规则未变更。`
- Proposal or classification failed: `未保存：{已证明事实}，现有规则未变更。`
- Deploy, edit, consolidate, or revoke failed: `未部署：{已证明事实}，现有规则未变更。`
- Committed mutation with incomplete cleanup: `规则操作已提交，但事务清理待完成；当前目标状态：{实际 target 读回状态，无法读回则未证明}。` This takes precedence over the generic failure receipt.

For routed mandatory behavior, use the deployed outcome only after both Owner content and the mandatory entry are verified. A no-op outcome proves only that the Agent surfaced a classification; it does not prove persistence, adoption, continuity, or product effect.
"""
