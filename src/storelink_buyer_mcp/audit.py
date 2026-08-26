"""Linked technical traces and buyer-readable audit records."""

from __future__ import annotations

import json
import os
import sys
import contextvars
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditRecorder:
    """Emit durable JSONL records without mixing logs into MCP stdout."""

    def __init__(self) -> None:
        self.technical_events: list[dict[str, Any]] = []
        self.buyer_events: list[dict[str, Any]] = []
        self._operation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            "audit_operation_id", default=None
        )

    def begin_operation(self, operation_id: str) -> contextvars.Token:
        return self._operation_id.set(operation_id)

    def end_operation(self, token: contextvars.Token) -> None:
        self._operation_id.reset(token)

    def technical(self, event: dict[str, Any]) -> None:
        operation = self._operation_id.get()
        correlated = {"operation_id": operation} if operation and "operation_id" not in event else {}
        record = {"timestamp": self._now(), "audience": "technical", **correlated, **event}
        self.technical_events.append(record)
        self._write("technical.jsonl", record)
        print(json.dumps(record, separators=(",", ":")), file=sys.stderr, flush=True)

    def buyer(self, event: dict[str, Any]) -> None:
        record = {"timestamp": self._now(), "audience": "buyer", **event}
        self.buyer_events.append(record)
        self._write("buyer.jsonl", record)

    def recent(self, audience: str) -> dict[str, Any]:
        records = self.technical_events if audience == "technical" else self.buyer_events
        return {"audience": audience, "records": records[-100:]}

    def _write(self, filename: str, record: dict[str, Any]) -> None:
        directory = Path(os.environ.get("STORELINK_AUDIT_DIR", "/tmp/storelink-audit"))
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / filename).open("a", encoding="utf-8") as output:
                output.write(json.dumps(record, separators=(",", ":")) + "\n")
        except OSError as exc:
            print(json.dumps({"event": "audit.persistence_failed", "error_type": type(exc).__name__}), file=sys.stderr)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
