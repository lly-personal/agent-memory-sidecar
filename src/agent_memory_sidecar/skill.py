from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import CoreError
from .file_security import _is_trusted_host_directory_alias, logical_absolute


SKILL_NAME = "agent-memory"


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
    return Path.home() / ".agents" / "skills"


def _is_reparse_point(value: os.stat_result) -> bool:
    return bool(
        getattr(value, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _assert_skill_directory_chain(path: Path, *, allow_missing_tail: bool) -> None:
    logical = logical_absolute(path)
    cursor = Path(logical.anchor)
    for part in logical.parts[1:]:
        cursor = cursor / part
        try:
            value = cursor.lstat()
        except FileNotFoundError:
            if allow_missing_tail:
                return
            raise CoreError(
                "skill_target_unsafe",
                "Skill directory is missing",
                path=str(cursor),
            )
        except OSError as exc:
            raise CoreError(
                "skill_target_unsafe",
                "Skill directory metadata is unavailable",
                path=str(cursor),
            ) from exc
        alias = stat.S_ISLNK(value.st_mode) or _is_reparse_point(value)
        if alias and _is_trusted_host_directory_alias(cursor, value):
            try:
                resolved_value = cursor.resolve(strict=True).stat()
            except OSError as exc:
                raise CoreError(
                    "skill_target_unsafe",
                    "trusted host directory mapping cannot be resolved",
                    path=str(cursor),
                ) from exc
            if not stat.S_ISDIR(resolved_value.st_mode):
                raise CoreError(
                    "skill_target_unsafe",
                    "trusted host directory mapping is not a directory",
                    path=str(cursor),
                )
            continue
        if not stat.S_ISDIR(value.st_mode) or alias:
            raise CoreError(
                "skill_target_unsafe",
                "Skill directory contains a filesystem alias",
                path=str(cursor),
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
            try:
                value = item.lstat()
            except OSError as exc:
                raise CoreError(
                    "skill_target_unsafe",
                    "Skill file metadata is unavailable",
                    path=str(item),
                ) from exc
            if (
                not stat.S_ISREG(value.st_mode)
                or stat.S_ISLNK(value.st_mode)
                or _is_reparse_point(value)
                or value.st_nlink != 1
            ):
                raise CoreError(
                    "skill_target_unsafe",
                    "Skill tree contains an unsafe file",
                    path=str(item),
                )
            files.append(item)
    return files


def _physical_skill_directory_exists(path: Path) -> bool:
    logical = logical_absolute(path)
    _assert_skill_directory_chain(logical.parent, allow_missing_tail=False)
    try:
        value = logical.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise CoreError(
            "skill_target_unsafe",
            "Skill directory metadata is unavailable",
            path=str(logical),
        ) from exc
    if (
        not stat.S_ISDIR(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _is_reparse_point(value)
    ):
        raise CoreError(
            "skill_target_unsafe",
            "Skill directory is not physical",
            path=str(logical),
        )
    _assert_skill_directory_chain(logical, allow_missing_tail=False)
    return True


def build_skill_files() -> dict[str, str]:
    return {
        "SKILL.md": _skill_markdown(),
        "agents/openai.yaml": (
            "interface:\n"
            "  display_name: Agent Memory\n"
            "  short_description: Publish authorized collaboration rules.\n"
        ),
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
    _assert_skill_directory_chain(logical.parent, allow_missing_tail=True)
    if not logical.parent.exists():
        return None
    if not _physical_skill_directory_exists(logical):
        return None
    expected = build_skill_files()
    try:
        values = {
            relative: (logical / relative).read_text(encoding="utf-8")
            for relative in expected
        }
    except OSError:
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
    backup_root = Path(
        tempfile.mkdtemp(
            prefix=f".{SKILL_NAME}.setup-snapshot.",
            dir=path.parent,
        )
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
    stage: Path | None = Path(
        tempfile.mkdtemp(
            prefix=f".{SKILL_NAME}.",
            dir=plan.path.parent,
        )
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
description: Use after the user explicitly establishes a reusable future collaboration rule, corrects Agent behavior in a way that may apply again, explicitly asks to remember a rule, audits whether Agent Memory triggered or saved anything, or replies to the current memory proposal. Do not use for one-off instructions, project-owned facts, transient failures, guesses, secrets, ordinary continuation, status, or routine Git work.
---

# Agent Memory

North star: `discover -> authorize -> deploy -> later-task behavior -> revoke`.

## Task boundary and visibility

Finish the current task before any Agent Memory process commentary. After the task, invoke this Skill only for an explicit remember, an explicit audit of whether memory triggered or saved anything, an evidenced reusable correction or stable preference, or a reply to the current proposal. Without one of those conditions, remain completely silent and do not create a proposal.

Once this Skill is invoked, or the Agent tells the user that Agent Memory will be, is being, or was used, the final reply must end with exactly one real terminal artifact from **Terminal outcomes**. Commentary, capability delivery, a command starting, or a future-tense promise is never a result. If the host requires announcing implicit Skill use, announce it only after the current task is complete, then immediately continue through classification and zero or one mutation; the announcement never replaces the final artifact.

Never expose event refs, tokens, internal commands, raw JSON, or diagnostic labels to the user.

## Admission

Before creating a proposal, inspect the actual rules with `agent-memory rule list`; when the target is already known, use `--target global_agents|project_agents` so an unrelated target cannot block the Fresh read. Compare the candidate only with the current instruction chain and project-authority documents already required for the task. Do not scan the whole project.

Classify the candidate once:

- `no_candidate`: an explicit audit found no evidenced reusable behavior. Do not create a token or write a file.
- `already_covered`: the behavior is already enforced by an actual rule or loaded project authority. Do not create a token or write a file.
- `add`: a genuinely independent collaboration behavior.
- `replace`: a correction to one existing rule; bind that rule with one `--supersedes`.
- `consolidate`: one rule replaces multiple overlapping rules; bind every affected rule with repeated `--supersedes` and show one exact before/after card.
- `route_to_owner`: project facts, design, status, safety boundaries, or current plans belong to their project owner, not the managed block.

If the relation is uncertain, show a clarification draft only. Never create a token for `no_candidate`, `already_covered`, or `route_to_owner`, and never delete or consolidate rules without explicit authorization. Because invoking the Skill makes the mechanism user-visible, every classification must use its matching terminal outcome; do not silently exit after `rule list`.

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

> **记忆建议**
> 规则：{action}
> 适用：{trigger}
> 不适用：{skip_boundary}
> 范围：本项目 | 跨项目
> 回复：**记住** / **修改：…** / **忽略**
>
> 记忆检查：已完成｜结论：发现新的可复用规则｜动作：已创建确认建议｜长期状态：待确认

## Scout bundle handoff

When the user confirms one or more cards from the current Global Owner Scout Review Pack, treat the exact selected card set as one operation. A single selected card is a bundle of size one.

1. Accept only the exact `card_id@selection_token` pairs from the same Review Pack, scope, and instruction target. The current user reply must be the canonical `确认 <card_id>@<token>[、...]` command. Do not mix confirmation with edit, routing, or ignore actions.
2. Reread that target with `agent-memory rule list --target <instruction-target>`, verify canonical/local parity when global, and jointly recompute every selected card against the same Owner snapshot and against the other selected cards.
3. If any relation, rule text, superseded set, or Owner target changes materially, execute no mutation. Show one refreshed aggregate before/after and ask once for confirmation of that changed bundle.
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

An unambiguous explicit remember utterance is the one authorization; do not ask twice. Echo the final `When / Do / Skip / scope`, deploy directly, and use the deployed terminal outcome only after the actual target is parsed and unshadowed. A proposal confirmation follows the same success outcome. For global results, complete the ordinary private-Git commit/push workflow when `publication_required=true`; local effect and cross-device publication are separate evidence.

On failure, preserve the completed task result and state only `未保存`, `未部署`, or `未证明` as supported. A current task may retain already-loaded instructions after revoke; verify a new task before claiming continuity.

## Terminal outcomes

The terminal artifact is the last user-facing Agent Memory block in the final reply. Use these exact four-part receipt lines; replace only braced user-readable summaries:

- Explicit audit with no candidate: `记忆检查：已完成｜结论：没有合格的可复用规则｜动作：未创建建议｜长期状态：未变更`
- Covered by actual authority: `记忆检查：已完成｜结论：当前规则已经覆盖｜动作：未创建建议｜长期状态：未变更`
- Routed to a formal owner: `记忆检查：已完成｜结论：内容应归入{正式 owner}｜动作：未创建长期规则｜长期状态：未变更`
- Proposal created: use the confirmation card above, including its `待确认` receipt as the last line.
- Explicit deploy or proposal confirmation succeeded: after the rule echo, `记忆检查：已完成｜结论：规则已部署｜动作：已写入{范围}规则｜长期状态：生效中`
- Atomic Scout bundle succeeded: after echoing every selected `When / Do / Skip / scope`, `记忆检查：已完成｜结论：已原子部署{数量}条规则｜动作：选中规则已整包写入{范围}｜长期状态：生效中`
- Clarification required: after the draft, `记忆检查：需要澄清｜结论：尚不能确定{待澄清内容}｜动作：未创建建议｜长期状态：未变更`
- Proposal or classification failed: `记忆检查：执行失败｜结论：{已证明事实}｜动作：未保存｜长期状态：未变更`
- Deploy, edit, consolidate, or revoke failed: `记忆检查：执行失败｜结论：{已证明事实}｜动作：未部署｜长期状态：未变更`
- Adoption is not yet observed: `记忆检查：已完成｜结论：规则已部署但后续采用尚未观察｜动作：未证明行为采用｜长期状态：生效中`

For discard, edit, consolidate, and revoke, use the same four-part shape with the operation actually completed and the actual parsed target state. A no-op receipt proves only that the Agent surfaced a classification; it does not prove persistence, adoption, continuity, or product effect.
"""
