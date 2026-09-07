from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .database import CoreDatabase
from .errors import CoreError
from .identity import ProjectIdentity
from .runtime_ledger import EVENT_RETENTION_DAYS, PromptEvent, RuntimeLedger


@dataclass(frozen=True)
class Approval:
    approval_ref: str
    approval_ref_sha256: str
    event: PromptEvent


class AuthorizationLedger:
    def __init__(self, db: CoreDatabase, runtime: RuntimeLedger) -> None:
        self.db = db
        self.runtime = runtime

    def validate(
        self, *, approval_ref: str, identity: ProjectIdentity
    ) -> Approval:
        event = self.runtime.resolve_approval_event(
            approval_ref=approval_ref,
            identity=identity,
        )
        canonical_ref = f"user_prompt:{event.event_id}"
        digest = hashlib.sha256(canonical_ref.encode("utf-8")).hexdigest()
        row = self.db.conn.execute(
            """
            SELECT operation FROM approval_consumptions
            WHERE source_event_id = ?
            """,
            (event.event_id,),
        ).fetchone()
        if row is not None:
            raise CoreError(
                "approval_invalid",
                "approval ref has already been consumed",
                prior_operation=str(row["operation"]),
            )
        return Approval(canonical_ref, digest, event)

    def consume(
        self,
        *,
        approval: Approval,
        operation: str,
        request_sha256: str | None,
        result_rule_id: str | None,
        transaction_id: str | None,
        consumed_at: str | None = None,
    ) -> None:
        timestamp = consumed_at or datetime.now(UTC).replace(
            microsecond=0
        ).isoformat()
        try:
            cursor = self.db.conn.execute(
                """
                INSERT INTO approval_consumptions (
                    approval_ref_sha256, source_event_id, source_session,
                    scope_key, operation, request_sha256, result_rule_id,
                    transaction_id, consumed_at
                ) SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM approval_consumptions WHERE source_event_id = ?
                )
                AND EXISTS (
                    SELECT 1 FROM prompt_events e
                    JOIN runtime_sessions s ON s.source_session = e.source_session
                    WHERE e.event_id = ? AND s.last_prompt_event_id = e.event_id
                      AND e.source_session = ? AND e.scope_key = ? AND s.scope_key = e.scope_key
                      AND julianday(e.created_at) >= julianday(?)
                )
                """,
                (
                    approval.approval_ref_sha256,
                    approval.event.event_id,
                    approval.event.source_session,
                    approval.event.scope_key,
                    str(operation),
                    request_sha256,
                    result_rule_id,
                    transaction_id,
                    timestamp,
                    approval.event.event_id,
                    approval.event.event_id,
                    approval.event.source_session,
                    approval.event.scope_key,
                    (datetime.fromisoformat(timestamp) - timedelta(days=EVENT_RETENTION_DAYS)).isoformat(),
                ),
            )
            if cursor.rowcount != 1:
                raise CoreError("approval_invalid", "approval event is no longer current, eligible, or unused")
        except Exception as exc:
            raise CoreError(
                "approval_invalid",
                "approval ref could not be consumed exactly once",
            ) from exc

    def validate_prompt_content(
        self, *, approval: Approval, expected_prompt: str
    ) -> None:
        expected_sha256 = hashlib.sha256(
            expected_prompt.encode("utf-8")
        ).hexdigest()
        if (
            approval.event.prompt_sha256 != expected_sha256
            or approval.event.prompt_bytes
            != len(expected_prompt.encode("utf-8"))
        ):
            raise CoreError(
                "approval_content_mismatch",
                "current approval prompt does not exactly confirm the selected rule bundle",
            )

    def transaction_committed(self, transaction_id: str) -> bool:
        row = self.db.conn.execute(
            """
            SELECT 1 FROM approval_consumptions
            WHERE transaction_id = ?
            """,
            (transaction_id,),
        ).fetchone()
        return row is not None
