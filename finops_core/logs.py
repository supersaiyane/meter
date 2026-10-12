"""Logs as one JSON object per line, as `docs/10-OBSERVABILITY.md` says they are. TASK-P12-005.

A process configured with `logging.basicConfig` alone writes the message and drops every field a
caller passed in `extra`, so a worker's "running collector" never said which collector, account
or run it meant. Here each field becomes a key, beside the time, the level, the logger, the
message and any traceback, which is what CloudWatch Logs Insights discovers and filters on.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Final

#: The attributes every log record has, so what is left is what the caller added.
STANDARD: Final = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """One record as one JSON object: the caller's fields, then the record's own."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            name: value for name, value in vars(record).items() if name not in STANDARD
        }
        entry.update(
            at=datetime.fromtimestamp(record.created, UTC).isoformat(),
            level=record.levelname,
            logger=record.name,
            message=record.getMessage(),
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure(level: str) -> None:
    """Every logger in the process writes JSON lines to standard error, from `level` up."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
