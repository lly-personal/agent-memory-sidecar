from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .database import CoreDatabase
from .errors import CoreError
from .identity import ProjectIdentity
from .proposal import RuleProposal


EVENT_RETENTION_DAYS = 7
SESSION_RETENTION_DAYS = 7
PROPOSAL_TTL_HOURS = 24
PRUNE_INTERVAL_HOURS = 1


@dataclass(frozen=True)
class PromptEvent:
    event_id: str
    source_session: str
    scope_key: str
    prompt_sha256: str
    prompt_bytes: int
    created_at: str


@dataclass(frozen=True)
class ProposalToken:
    token_id: str
    source_event_id: str
    source_session: str
    scope: str
    scope_key: str
    instruction_target: str
    proposal_sha256: str
    created_at: str
    expires_at: str


class RuntimeLedger:
    def __init__(self, db: CoreDatabase) -> None:
        self.db = db

    def capture_prompt(
        self,
        *,
        identity: ProjectIdentity,
        source_session: str,
        prompt: str,
        metadata: dict[str, Any],
        now: str | None = None,
    ) -> PromptEvent:
        session = _required(source_session, "source_session")
        timestamp = _timestamp(now)
        encoded = str(prompt).encode("utf-8", errors="replace")
        digest = hashlib.sha256(encoded).hexdigest()
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        envelope = json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(envelope.encode("utf-8")) > 4096:
            raise CoreError(
                "event_envelope_oversize",
                "bounded runtime event metadata exceeds 4 KiB",
            )
        with self.db.transaction():
            current = self.db.conn.execute(
                """
                SELECT scope_key, context_epoch FROM runtime_sessions
                WHERE source_session = ?
                """,
                (session,),
            ).fetchone()
            if current is not None and str(current["scope_key"]) != identity.scope_key:
                raise CoreError(
                    "scope_mismatch",
                    "runtime session was reused across project scopes",
                )
            self.db.conn.execute(
                """
                INSERT INTO prompt_events (
                    event_id, source_session, scope_key, cwd, repo_root, branch,
                    prompt_sha256, prompt_bytes, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session,
                    identity.scope_key,
                    identity.cwd,
                    identity.repo_root,
                    identity.branch,
                    digest,
                    len(encoded),
                    envelope,
                    timestamp,
                ),
            )
            if current is None:
                self.db.conn.execute(
                    """
                    INSERT INTO runtime_sessions (
                        source_session, scope_key, context_epoch,
                        last_prompt_event_id, last_seen_at
                    ) VALUES (?, ?, 0, ?, ?)
                    """,
                    (session, identity.scope_key, event_id, timestamp),
                )
            else:
                self.db.conn.execute(
                    """
                    UPDATE runtime_sessions
                    SET last_prompt_event_id = ?, last_seen_at = ?
                    WHERE source_session = ?
                    """,
                    (event_id, timestamp, session),
                )
            self._prune(timestamp)
        return PromptEvent(
            event_id=event_id,
            source_session=session,
            scope_key=identity.scope_key,
            prompt_sha256=digest,
            prompt_bytes=len(encoded),
            created_at=timestamp,
        )

    def current_event(
        self,
        *,
        source_session: str,
    ) -> PromptEvent:
        row = self.db.conn.execute(
            """
            SELECT e.event_id, e.source_session, e.scope_key, e.prompt_sha256,
                   e.prompt_bytes, e.created_at
            FROM runtime_sessions s
            JOIN prompt_events e ON e.event_id = s.last_prompt_event_id
            WHERE s.source_session = ?
            """,
            (_required(source_session, "source_session"),),
        ).fetchone()
        if row is None:
            raise CoreError(
                "approval_invalid",
                "current prompt event was not found for this session",
            )
        return _event(row)

    def resolve_approval_event(
        self,
        *,
        approval_ref: str,
        identity: ProjectIdentity,
        now: str | None = None,
    ) -> PromptEvent:
        event_id = event_id_from_ref(approval_ref)
        row = self.db.conn.execute(
            """
            SELECT e.event_id, e.source_session, e.scope_key, e.prompt_sha256,
                   e.prompt_bytes, e.created_at,
                   s.last_prompt_event_id
            FROM prompt_events e
            JOIN runtime_sessions s ON s.source_session = e.source_session
            WHERE e.event_id = ?
            """,
            (event_id,),
        ).fetchone()
        if row is None or str(row["last_prompt_event_id"] or "") != event_id:
            raise CoreError(
                "approval_invalid",
                "approval ref is missing, expired, or not the current prompt",
            )
        if _parse_timestamp(str(row["created_at"])) < (
            _parse_timestamp(_timestamp(now))
            - timedelta(days=EVENT_RETENTION_DAYS)
        ):
            raise CoreError(
                "approval_invalid",
                "approval ref is older than the runtime event retention window",
            )
        if str(row["scope_key"]) != identity.scope_key:
            raise CoreError(
                "scope_mismatch",
                "approval ref belongs to a different primary project scope",
                expected_scope=identity.scope_key,
                actual_scope=str(row["scope_key"]),
            )
        return _event(row)

    def create_proposal(
        self,
        *,
        source_event_ref: str,
        identity: ProjectIdentity,
        proposal: RuleProposal,
        proposal_sha256: str | None = None,
        replace: bool = False,
        now: str | None = None,
    ) -> ProposalToken:
        event = self.resolve_approval_event(
            approval_ref=source_event_ref,
            identity=identity,
        )
        timestamp = _timestamp(now)
        expires = (
            _parse_timestamp(timestamp) + timedelta(hours=PROPOSAL_TTL_HOURS)
        ).isoformat(timespec="seconds")
        token = ProposalToken(
            token_id=f"proposal_{uuid.uuid4().hex[:16]}",
            source_event_id=event.event_id,
            source_session=event.source_session,
            scope=proposal.scope,
            scope_key=identity.scope_key,
            instruction_target=proposal.instruction_target,
            proposal_sha256=_proposal_binding(
                proposal_sha256 or proposal.proposal_sha256
            ),
            created_at=timestamp,
            expires_at=expires,
        )
        with self.db.transaction():
            existing = self.db.conn.execute(
                """
                SELECT token_id FROM proposal_tokens
                WHERE source_session = ?
                """,
                (event.source_session,),
            ).fetchone()
            if existing is not None and not replace:
                raise CoreError(
                    "proposal_pending",
                    "one pending proposal already exists for this session",
                )
            if replace:
                self.db.conn.execute(
                    "DELETE FROM proposal_tokens WHERE source_session = ?",
                    (event.source_session,),
                )
            self.db.conn.execute(
                """
                INSERT INTO proposal_tokens (
                    token_id, source_event_id, source_session, scope, scope_key,
                    instruction_target, proposal_sha256, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token.token_id,
                    token.source_event_id,
                    token.source_session,
                    token.scope,
                    token.scope_key,
                    token.instruction_target,
                    token.proposal_sha256,
                    token.created_at,
                    token.expires_at,
                ),
            )
        return token

    def pending_for_approval(
        self,
        *,
        approval_ref: str,
        identity: ProjectIdentity,
        proposal: RuleProposal | None,
        now: str | None = None,
    ) -> tuple[PromptEvent, ProposalToken]:
        approval = self.resolve_approval_event(
            approval_ref=approval_ref,
            identity=identity,
        )
        row = self.db.conn.execute(
            """
            SELECT * FROM proposal_tokens
            WHERE source_session = ?
            """,
            (approval.source_session,),
        ).fetchone()
        token = _token(row) if row is not None else None
        current = _parse_timestamp(_timestamp(now))
        if (
            token is None
            or token.scope_key != identity.scope_key
            or _parse_timestamp(token.expires_at) <= current
        ):
            raise CoreError(
                "proposal_invalid",
                "proposal is missing, expired, or belongs to another scope",
            )
        if proposal is not None and (
            token.proposal_sha256 != proposal.proposal_sha256
            or token.scope != proposal.scope
            or token.instruction_target != proposal.instruction_target
        ):
            raise CoreError(
                "proposal_invalid",
                "proposal content or scope does not match the pending token",
            )
        return approval, token

    def delete_proposal(self, token_id: str) -> None:
        changed = self.db.conn.execute(
            "DELETE FROM proposal_tokens WHERE token_id = ?",
            (token_id,),
        ).rowcount
        if changed != 1:
            raise CoreError(
                "proposal_invalid",
                "pending proposal changed before it could be consumed",
            )

    def pending_count(self, *, scope_key: str, now: str | None = None) -> int:
        current = _timestamp(now)
        row = self.db.conn.execute(
            """
            SELECT COUNT(*) AS count FROM proposal_tokens
            WHERE scope_key = ? AND expires_at > ?
            """,
            (scope_key, current),
        ).fetchone()
        return int(row["count"])

    def _prune(self, now: str) -> None:
        current = _parse_timestamp(now)
        row = self.db.conn.execute(
            "SELECT last_pruned_at FROM core_schema WHERE singleton = 1"
        ).fetchone()
        if row is not None and _parse_timestamp(
            str(row["last_pruned_at"])
        ) > current - timedelta(hours=PRUNE_INTERVAL_HOURS):
            return
        event_cutoff = (
            current - timedelta(days=EVENT_RETENTION_DAYS)
        ).isoformat(timespec="seconds")
        session_cutoff = (
            current - timedelta(days=SESSION_RETENTION_DAYS)
        ).isoformat(timespec="seconds")
        self.db.conn.execute(
            "DELETE FROM proposal_tokens WHERE expires_at <= ?",
            (now,),
        )
        self.db.conn.execute(
            "DELETE FROM runtime_sessions WHERE last_seen_at < ?",
            (session_cutoff,),
        )
        self.db.conn.execute(
            """
            DELETE FROM prompt_events
            WHERE created_at < ?
              AND event_id NOT IN (
                  SELECT source_event_id FROM proposal_tokens
              )
            """,
            (event_cutoff,),
        )
        self.db.conn.execute(
            "UPDATE core_schema SET last_pruned_at = ? WHERE singleton = 1",
            (now,),
        )


def event_id_from_ref(approval_ref: str) -> str:
    value = str(approval_ref or "").strip()
    prefix = "user_prompt:"
    if not value.startswith(prefix):
        raise CoreError(
            "approval_invalid",
            "approval ref must be an opaque user_prompt event reference",
        )
    event_id = value[len(prefix) :].strip()
    if not event_id or any(character.isspace() for character in event_id):
        raise CoreError("approval_invalid", "approval ref is malformed")
    return event_id


def _event(row: Any) -> PromptEvent:
    return PromptEvent(
        event_id=str(row["event_id"]),
        source_session=str(row["source_session"]),
        scope_key=str(row["scope_key"]),
        prompt_sha256=str(row["prompt_sha256"]),
        prompt_bytes=int(row["prompt_bytes"]),
        created_at=str(row["created_at"]),
    )


def _token(row: Any) -> ProposalToken:
    return ProposalToken(
        token_id=str(row["token_id"]),
        source_event_id=str(row["source_event_id"]),
        source_session=str(row["source_session"]),
        scope=str(row["scope"]),
        scope_key=str(row["scope_key"]),
        instruction_target=str(row["instruction_target"]),
        proposal_sha256=str(row["proposal_sha256"]),
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
    )


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise CoreError("invalid_request", f"{name} is required")
    return text


def _proposal_binding(value: Any) -> str:
    text = _required(value, "proposal_sha256")
    if len(text.encode("ascii", errors="ignore")) != len(text) or len(text) > 512:
        raise CoreError(
            "invalid_proposal",
            "proposal hash binding is malformed",
        )
    return text


def _timestamp(value: str | None = None) -> str:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0).isoformat()
    return _parse_timestamp(value).isoformat(timespec="seconds")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise CoreError("invalid_timestamp", "timestamp is invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0)
