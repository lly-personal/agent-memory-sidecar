from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from .codex_integration import doctor, setup, store_path
from .core_cutover import apply_core_cutover, preview_core_cutover
from .database import CoreDatabase
from .errors import CoreError
from .file_security import logical_absolute
from .identity import resolve_identity
from .proposal import RuleBundle, RuleProposal
from .rule_service import RuleService
from .runtime_selftest import run as run_runtime_self_test


RESULT_CONTRACT = "agent_memory_result_v1"


class ResultParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        if message.startswith(
            "argument {rule,setup,doctor}: invalid choice:"
        ):
            message = "unknown command; expected rule, setup, or doctor"
        raise CoreError("invalid_request", message)


def main(argv: Sequence[str] | None = None) -> int:
    _configure_stdio()
    operation = "unknown"
    scope: str | None = None
    target: str | None = None
    try:
        parser = build_parser()
        args = parser.parse_args(
            list(argv) if argv is not None else sys.argv[1:]
        )
        operation = str(args.operation)
        result = args.func(args)
        if isinstance(result, _OperationResult):
            scope = result.scope
            target = result.target
            data = result.data
        else:
            data = result
        print(
            json.dumps(
                _result(
                    operation=operation,
                    status="ok",
                    scope=scope,
                    target=target,
                    data=data,
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except CoreError as exc:
        print(
            json.dumps(
                _result(
                    operation=operation,
                    status="error",
                    scope=scope,
                    target=target,
                    data=None,
                    error=exc.to_dict(),
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    except Exception as exc:
        error = CoreError(
            "internal_error",
            "Agent Memory failed without completing the operation",
            exception_type=type(exc).__name__,
        )
        print(
            json.dumps(
                _result(
                    operation=operation,
                    status="error",
                    scope=scope,
                    target=target,
                    data=None,
                    error=error.to_dict(),
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = ResultParser(
        prog="agent-memory",
        description="Publish user-authorized collaboration rules.",
    )
    parser.add_argument(
        "--store",
        help="Core Store path; defaults to the Codex user Store.",
    )
    parser.add_argument(
        "--cwd",
        help="Primary project directory used for scope resolution.",
    )
    commands = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="{rule,setup,doctor}",
    )

    rule = commands.add_parser("rule", help="List, deploy, or revoke rules.")
    rule_commands = rule.add_subparsers(
        dest="rule_command",
        required=True,
    )
    rule_list = rule_commands.add_parser(
        "list", help="List actual instruction rules."
    )
    rule_list.add_argument(
        "--target",
        choices=("global_agents", "project_agents"),
    )
    _bind(rule_list, "rule.list", cmd_rule_list)
    rule_deploy = rule_commands.add_parser(
        "deploy", help="Deploy one approved rule."
    )
    rule_deploy.add_argument("--from-json", required=True)
    rule_deploy.add_argument("--approval-ref", required=True)
    rule_deploy.add_argument("--supersedes", action="append")
    _bind(rule_deploy, "rule.deploy", cmd_rule_deploy)
    rule_deploy_bundle = rule_commands.add_parser(
        "deploy-bundle", help="Atomically deploy one or more approved rules."
    )
    rule_deploy_bundle.add_argument("--from-json", required=True)
    rule_deploy_bundle.add_argument("--approval-ref", required=True)
    _bind(
        rule_deploy_bundle,
        "rule.deploy_bundle",
        cmd_rule_deploy_bundle,
    )
    rule_revoke = rule_commands.add_parser(
        "revoke", help="Revoke one deployed rule."
    )
    rule_revoke.add_argument("rule_id")
    rule_revoke.add_argument("--approval-ref", required=True)
    _bind(rule_revoke, "rule.revoke", cmd_rule_revoke)

    proposal = commands.add_parser("proposal", help=argparse.SUPPRESS)
    proposal_commands = proposal.add_subparsers(
        dest="proposal_command",
        required=True,
    )
    for name, func in (
        ("create", cmd_proposal_create),
        ("replace", cmd_proposal_replace),
    ):
        command = proposal_commands.add_parser(name, help=argparse.SUPPRESS)
        command.add_argument("--source-event", required=True)
        command.add_argument("--from-json", required=True)
        command.add_argument("--supersedes", action="append")
        _bind(command, f"proposal.{name}", func)
    confirm = proposal_commands.add_parser(
        "confirm", help=argparse.SUPPRESS
    )
    confirm.add_argument("--approval-ref", required=True)
    confirm.add_argument("--from-json", required=True)
    confirm.add_argument("--supersedes", action="append")
    _bind(confirm, "proposal.confirm", cmd_proposal_confirm)
    discard = proposal_commands.add_parser(
        "discard", help=argparse.SUPPRESS
    )
    discard.add_argument("--approval-ref", required=True)
    _bind(discard, "proposal.discard", cmd_proposal_discard)

    setup_parser = commands.add_parser(
        "setup", help="Preview or install the immutable Desktop runtime."
    )
    setup_parser.add_argument("--apply", action="store_true")
    setup_parser.add_argument("--global-rules-source")
    setup_parser.add_argument(
        "--rebind-global-rules-source",
        action="store_true",
        help="Explicitly migrate an existing drift-free global binding to the selected source.",
    )
    _bind(setup_parser, "setup", cmd_setup)

    doctor_parser = commands.add_parser(
        "doctor", help="Verify Core Store and Desktop integration."
    )
    _bind(doctor_parser, "doctor", cmd_doctor)

    maintenance = commands.add_parser("maintenance", help=argparse.SUPPRESS)
    maintenance_commands = maintenance.add_subparsers(
        dest="maintenance_command",
        required=True,
    )
    cutover = maintenance_commands.add_parser(
        "core-cutover", help=argparse.SUPPRESS
    )
    mode = cutover.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    cutover.add_argument("--plan-hash")
    cutover.add_argument("--approval-ref")
    _bind(cutover, "maintenance.core-cutover", cmd_core_cutover)
    self_test = maintenance_commands.add_parser(
        "self-test", help=argparse.SUPPRESS
    )
    self_test.add_argument("--store", dest="self_test_store", required=True)
    _bind(self_test, "maintenance.self-test", cmd_self_test)

    commands._choices_actions[:] = [  # type: ignore[attr-defined]
        item
        for item in commands._choices_actions  # type: ignore[attr-defined]
        if getattr(item, "dest", None) in {"rule", "setup", "doctor"}
    ]
    return parser


class _OperationResult:
    def __init__(
        self,
        *,
        data: dict[str, Any],
        scope: str | None = None,
        target: str | None = None,
    ) -> None:
        self.data = data
        self.scope = scope
        self.target = target


def cmd_rule_list(args: argparse.Namespace) -> _OperationResult:
    identity = resolve_identity(args.cwd)
    with CoreDatabase(_store(args)) as db:
        data = RuleService(db=db, identity=identity).list(
            target=args.target,
        )
    return _OperationResult(data=data)


def cmd_rule_deploy(args: argparse.Namespace) -> _OperationResult:
    identity = resolve_identity(args.cwd)
    proposal = _proposal(args.from_json)
    with CoreDatabase(_store(args)) as db:
        result = RuleService(db=db, identity=identity).deploy(
            proposal=proposal,
            approval_ref=args.approval_ref,
            supersedes=args.supersedes,
        )
    return _OperationResult(
        data=result.to_dict(),
        scope=proposal.scope,
        target=proposal.instruction_target,
    )


def cmd_rule_deploy_bundle(args: argparse.Namespace) -> _OperationResult:
    identity = resolve_identity(args.cwd)
    bundle = _bundle(args.from_json)
    with CoreDatabase(_store(args)) as db:
        result = RuleService(db=db, identity=identity).deploy_bundle(
            bundle=bundle,
            approval_ref=args.approval_ref,
        )
    return _OperationResult(
        data=result.to_dict(),
        scope=bundle.scope,
        target=bundle.instruction_target,
    )


def cmd_rule_revoke(args: argparse.Namespace) -> _OperationResult:
    identity = resolve_identity(args.cwd)
    with CoreDatabase(_store(args)) as db:
        result = RuleService(db=db, identity=identity).revoke(
            rule_id=args.rule_id,
            approval_ref=args.approval_ref,
        )
    scope = "global" if result.rule.target == "global_agents" else "project"
    return _OperationResult(
        data=result.to_dict(),
        scope=scope,
        target=result.rule.target,
    )


def cmd_proposal_create(args: argparse.Namespace) -> _OperationResult:
    return _create_proposal(args, replace=False)


def cmd_proposal_replace(args: argparse.Namespace) -> _OperationResult:
    return _create_proposal(args, replace=True)


def _create_proposal(
    args: argparse.Namespace, *, replace: bool
) -> _OperationResult:
    identity = resolve_identity(args.cwd)
    proposal = _proposal(args.from_json)
    with CoreDatabase(_store(args)) as db:
        token, revision = RuleService(
            db=db,
            identity=identity,
        ).create_proposal(
            source_event_ref=args.source_event,
            proposal=proposal,
            supersedes=args.supersedes,
            replace=replace,
        )
    return _OperationResult(
        data={
            "token_id": token.token_id,
            "proposal_sha256": f"sha256:{proposal.proposal_sha256}",
            "revision_sha256": f"sha256:{revision.revision_sha256}",
            "expires_at": token.expires_at,
        },
        scope=proposal.scope,
        target=proposal.instruction_target,
    )


def cmd_proposal_confirm(args: argparse.Namespace) -> _OperationResult:
    identity = resolve_identity(args.cwd)
    proposal = _proposal(args.from_json)
    with CoreDatabase(_store(args)) as db:
        result = RuleService(db=db, identity=identity).confirm_proposal(
            proposal=proposal,
            approval_ref=args.approval_ref,
            supersedes=args.supersedes,
        )
    return _OperationResult(
        data=result.to_dict(),
        scope=proposal.scope,
        target=proposal.instruction_target,
    )


def cmd_proposal_discard(args: argparse.Namespace) -> _OperationResult:
    identity = resolve_identity(args.cwd)
    with CoreDatabase(_store(args)) as db:
        data = RuleService(
            db=db,
            identity=identity,
        ).discard_proposal(approval_ref=args.approval_ref)
    return _OperationResult(data=data)


def cmd_setup(args: argparse.Namespace) -> _OperationResult:
    identity = resolve_identity(args.cwd)
    return _OperationResult(
        data=setup(
            apply=args.apply,
            identity=identity,
            global_rules_source=args.global_rules_source,
            allow_global_source_rebind=args.rebind_global_rules_source,
        )
    )


def cmd_doctor(args: argparse.Namespace) -> _OperationResult:
    report = doctor(identity=resolve_identity(args.cwd))
    if report["status"] != "ok":
        raise CoreError(
            "doctor_failed",
            "Core Store or Desktop integration is not ready",
            report=report,
        )
    return _OperationResult(data=report)


def cmd_core_cutover(args: argparse.Namespace) -> _OperationResult:
    target = _store(args)
    if args.apply:
        if not args.plan_hash or not args.approval_ref:
            raise CoreError(
                "invalid_request",
                "core-cutover --apply requires --plan-hash and --approval-ref",
            )
        data = apply_core_cutover(
            store_path=target,
            identity=resolve_identity(args.cwd),
            approval_ref=args.approval_ref,
            expected_plan_hash=args.plan_hash,
        )
    else:
        data = preview_core_cutover(store_path=target).to_dict()
    return _OperationResult(data=data)


def cmd_self_test(args: argparse.Namespace) -> _OperationResult:
    return _OperationResult(
        data=run_runtime_self_test(
            store_path=Path(args.self_test_store)
        )
    )


def _bind(
    parser: argparse.ArgumentParser,
    operation: str,
    func: Callable[[argparse.Namespace], Any],
) -> None:
    parser.set_defaults(operation=operation, func=func)


def _store(args: argparse.Namespace) -> Path:
    value = getattr(args, "store", None)
    return (
        logical_absolute(value)
        if value
        else store_path()
    )


def _proposal(value: str) -> RuleProposal:
    return RuleProposal.from_payload(_json_payload(value))


def _bundle(value: str) -> RuleBundle:
    return RuleBundle.from_payload(_json_payload(value))


def _json_payload(value: str) -> dict[str, Any]:
    stripped = str(value).lstrip()
    if stripped.startswith("{"):
        raw = value
    else:
        path = Path(value).expanduser()
        if not path.exists():
            raise CoreError(
                "invalid_request",
                "--from-json must be a JSON object or existing file",
            )
        raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CoreError(
            "invalid_proposal",
            "proposal is not valid JSON",
            line=exc.lineno,
            column=exc.colno,
        ) from exc
    if not isinstance(payload, dict):
        raise CoreError(
            "invalid_request",
            "--from-json must contain a JSON object",
        )
    return payload


def _result(
    *,
    operation: str,
    status: str,
    scope: str | None,
    target: str | None,
    data: Any,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": RESULT_CONTRACT,
        "operation": operation,
        "status": status,
        "scope": scope,
        "target": target,
        "data": data,
        "error": error,
    }


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
