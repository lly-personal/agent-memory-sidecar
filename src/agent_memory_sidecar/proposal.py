from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from .errors import CoreError


Scope = Literal["project", "global"]
InstructionTarget = Literal["project_agents", "global_agents"]

PROPOSAL_FIELDS = frozenset(
    {
        "trigger",
        "action",
        "skip_boundary",
        "scope",
        "why",
        "evidence",
        "instruction_target",
    }
)
BUNDLE_FIELDS = frozenset(
    {"contract_version", "target_before_sha256", "items"}
)
BUNDLE_ITEM_FIELDS = frozenset(
    {
        "card_id",
        "project_claim_hash",
        "proposal",
        "supersedes",
        "selection_token",
    }
)
TARGET_FOR_SCOPE: dict[str, InstructionTarget] = {
    "project": "project_agents",
    "global": "global_agents",
}
MAX_REASON_BYTES = 4096
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_CARD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SELECTION_TOKEN = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class RuleProposal:
    trigger: str
    action: str
    skip_boundary: str
    scope: Scope
    why: str
    evidence: str
    instruction_target: InstructionTarget

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RuleProposal":
        if not isinstance(payload, dict):
            raise CoreError("invalid_proposal", "proposal must be a JSON object")
        missing = sorted(PROPOSAL_FIELDS - set(payload))
        extra = sorted(set(payload) - PROPOSAL_FIELDS)
        if missing or extra:
            raise CoreError(
                "invalid_proposal",
                "proposal must contain exactly the seven Core v1 fields",
                missing=missing,
                extra=extra,
            )
        scope = _scope(payload["scope"])
        target = _target(payload["instruction_target"])
        expected = TARGET_FOR_SCOPE[scope]
        if target != expected:
            raise CoreError(
                "invalid_proposal",
                "scope and instruction_target do not match",
                scope=scope,
                instruction_target=target,
                expected_instruction_target=expected,
            )
        return cls(
            trigger=_behavior_text(payload["trigger"], "trigger"),
            action=_behavior_text(payload["action"], "action"),
            skip_boundary=_behavior_text(
                payload["skip_boundary"], "skip_boundary"
            ),
            scope=scope,
            why=_bounded_text(payload["why"], "why"),
            evidence=_bounded_text(payload["evidence"], "evidence"),
            instruction_target=target,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "trigger": self.trigger,
            "action": self.action,
            "skip_boundary": self.skip_boundary,
            "scope": self.scope,
            "why": self.why,
            "evidence": self.evidence,
            "instruction_target": self.instruction_target,
        }

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def proposal_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuleBundleItem:
    card_id: str
    project_claim_hash: str
    proposal: RuleProposal
    supersedes: tuple[str, ...]
    selection_token: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RuleBundleItem":
        if not isinstance(payload, dict):
            raise CoreError(
                "invalid_rule_bundle",
                "each rule bundle item must be a JSON object",
            )
        missing = sorted(BUNDLE_ITEM_FIELDS - set(payload))
        extra = sorted(set(payload) - BUNDLE_ITEM_FIELDS)
        if missing or extra:
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle item fields do not match rule_revision_bundle_v2",
                missing=missing,
                extra=extra,
            )
        raw_supersedes = payload["supersedes"]
        if not isinstance(raw_supersedes, list):
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle supersedes must be a JSON array",
            )
        supersedes = tuple(str(value).strip() for value in raw_supersedes)
        if any(not value for value in supersedes) or len(set(supersedes)) != len(
            supersedes
        ):
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle supersedes must contain unique non-empty rule IDs",
            )
        card_id = str(payload["card_id"] or "").strip()
        if not _CARD_ID.fullmatch(card_id):
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle card_id is malformed",
                card_id=card_id,
            )
        project_claim_hash = _sha256_text(
            payload["project_claim_hash"], "project_claim_hash"
        )
        selection_token = str(payload["selection_token"] or "").strip()
        if not _SELECTION_TOKEN.fullmatch(selection_token):
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle selection_token must be 32 lowercase hex characters",
                card_id=card_id,
            )
        return cls(
            card_id=card_id,
            project_claim_hash=project_claim_hash,
            proposal=RuleProposal.from_payload(payload["proposal"]),
            supersedes=tuple(sorted(supersedes)),
            selection_token=selection_token,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "project_claim_hash": self.project_claim_hash,
            "proposal": self.proposal.to_dict(),
            "supersedes": list(self.supersedes),
            "selection_token": self.selection_token,
        }


@dataclass(frozen=True)
class RuleBundle:
    target_before_sha256: str
    items: tuple[RuleBundleItem, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RuleBundle":
        if not isinstance(payload, dict):
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle must be a JSON object",
            )
        missing = sorted(BUNDLE_FIELDS - set(payload))
        extra = sorted(set(payload) - BUNDLE_FIELDS)
        if missing or extra:
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle fields do not match rule_revision_bundle_v2",
                missing=missing,
                extra=extra,
            )
        if payload["contract_version"] != "rule_revision_bundle_v2":
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle contract version is not supported",
                contract_version=payload["contract_version"],
            )
        raw_items = payload["items"]
        if not isinstance(raw_items, list) or not raw_items:
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle must contain at least one item",
            )
        target_before_sha256 = _sha256_text(
            payload["target_before_sha256"], "target_before_sha256"
        )
        items = tuple(
            sorted(
                (RuleBundleItem.from_payload(item) for item in raw_items),
                key=lambda item: item.card_id,
            )
        )
        scopes = {item.proposal.scope for item in items}
        targets = {item.proposal.instruction_target for item in items}
        identities = [item.proposal.proposal_sha256 for item in items]
        card_ids = [item.card_id for item in items]
        if len(scopes) != 1 or len(targets) != 1:
            raise CoreError(
                "invalid_rule_bundle",
                "every rule bundle item must use the same scope and instruction target",
            )
        if len(set(identities)) != len(identities):
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle proposals must be unique",
            )
        if len(set(card_ids)) != len(card_ids):
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle card IDs must be unique",
            )
        bundle = cls(
            target_before_sha256=target_before_sha256,
            items=items,
        )
        for item in items:
            expected = review_selection_token(
                card_id=item.card_id,
                project_claim_hash=item.project_claim_hash,
                proposal=item.proposal,
                supersedes=item.supersedes,
                instruction_target=bundle.instruction_target,
                target_before_sha256=target_before_sha256,
            )
            if item.selection_token != expected:
                raise CoreError(
                    "approval_content_mismatch",
                    "rule bundle selection token does not match the selected operation",
                    card_id=item.card_id,
                )
        return bundle

    @property
    def scope(self) -> Scope:
        return self.items[0].proposal.scope

    @property
    def instruction_target(self) -> InstructionTarget:
        return self.items[0].proposal.instruction_target

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "rule_revision_bundle_v2",
            "target_before_sha256": self.target_before_sha256,
            "items": [item.to_dict() for item in self.items],
        }

    @property
    def confirmation_text(self) -> str:
        return "确认 " + "、".join(
            f"{item.card_id}@{item.selection_token}" for item in self.items
        )

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def bundle_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


def review_selection_token(
    *,
    card_id: str,
    project_claim_hash: str,
    proposal: RuleProposal,
    supersedes: tuple[str, ...],
    instruction_target: InstructionTarget,
    target_before_sha256: str,
) -> str:
    canonical = json.dumps(
        {
            "card_id": card_id,
            "contract_version": "review_selection_token_v1",
            "instruction_target": instruction_target,
            "project_claim_hash": project_claim_hash,
            "proposal_sha256": proposal.proposal_sha256,
            "supersedes": list(sorted(supersedes)),
            "target_before_sha256": target_before_sha256,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _sha256_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not _SHA256.fullmatch(text):
        raise CoreError(
            "invalid_rule_bundle",
            f"{field} must be 64 lowercase hex characters",
            field=field,
        )
    return text


def _scope(value: Any) -> Scope:
    text = str(value or "").strip().casefold()
    if text not in TARGET_FOR_SCOPE:
        raise CoreError(
            "invalid_proposal",
            "scope must be project or global",
            scope=text,
        )
    return text  # type: ignore[return-value]


def _target(value: Any) -> InstructionTarget:
    text = str(value or "").strip()
    if text not in {"project_agents", "global_agents"}:
        raise CoreError(
            "invalid_proposal",
            "instruction_target must be project_agents or global_agents",
            instruction_target=text,
        )
    return text  # type: ignore[return-value]


def _behavior_text(value: Any, name: str) -> str:
    text = _normalized_text(value, name)
    if "\n" in text or "\r" in text:
        raise CoreError(
            "invalid_proposal",
            f"{name} must be a single line",
            field=name,
        )
    return text


def _bounded_text(value: Any, name: str) -> str:
    text = _normalized_text(value, name)
    if len(text.encode("utf-8")) > MAX_REASON_BYTES:
        raise CoreError(
            "invalid_proposal",
            f"{name} exceeds the {MAX_REASON_BYTES}-byte proposal budget",
            field=name,
        )
    return text


def _normalized_text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise CoreError(
            "invalid_proposal",
            f"{name} must be a string",
            field=name,
        )
    text = unicodedata.normalize("NFC", value).strip()
    if not text or _CONTROL.search(text):
        raise CoreError(
            "invalid_proposal",
            f"{name} must be non-empty and contain no control characters",
            field=name,
        )
    return text
