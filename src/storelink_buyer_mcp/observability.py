"""Two logs for two readers.

``trace.jsonl`` — structured events for the FDE debugging at 11pm: every
tool call, every StoreLink request, latency, outcome, error class, and a
trace_id that ties one tool call to its upstream requests. Mirrored to
stderr so container logs capture it (stdout is reserved for the MCP
stdio transport).

``audit.log`` — plain sentences for the Korral buyer the next morning:
what the agent looked at, what it decided, and exactly what it wrote to
StoreLink, in order.

Secrets never appear in either log; keys are shown only as SHA-256
fingerprints (see ``credentials.key_fingerprint``).

The log directory comes from ``STORELINK_MCP_LOG_DIR`` (default
``./logs``) and is resolved on every write so tests and rotations do not
require a restart.
"""

from __future__ import annotations

import contextvars
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

_current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "storelink_trace_id", default=None
)


class Observability:
    def __init__(self, log_dir: str | None = None):
        self._log_dir_override = log_dir
        self._lock = threading.Lock()

    def _dir(self) -> Path:
        path = Path(self._log_dir_override or os.environ.get("STORELINK_MCP_LOG_DIR", "logs"))
        path.mkdir(parents=True, exist_ok=True)
        return path

    def begin_trace(self, trace_id: str) -> contextvars.Token:
        return _current_trace_id.set(trace_id)

    def end_trace(self, token: contextvars.Token) -> None:
        _current_trace_id.reset(token)

    def trace(self, event: str, **fields) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "trace_id": _current_trace_id.get(),
            "event": event,
            **fields,
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            with (self._dir() / "trace.jsonl").open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        print(line, file=sys.stderr)

    def audit(self, message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        with self._lock:
            with (self._dir() / "audit.log").open("a", encoding="utf-8") as f:
                f.write(f"{stamp}  {message}\n")
