"""Logs are JSON, one object per line, carrying the caller's fields. TASK-P12-005."""

from __future__ import annotations

import json
import logging
import sys

import pytest

from finops_core.logs import JsonFormatter, configure


def formatted(record: logging.LogRecord) -> dict[str, object]:
    found: dict[str, object] = json.loads(JsonFormatter().format(record))
    return found


def record(**extra: object) -> logging.LogRecord:
    made = logging.makeLogRecord(
        {"name": "meter.ingest.worker", "levelname": "INFO", "msg": "running collector"}
    )
    made.__dict__.update(extra)
    return made


def test_a_line_carries_the_message_level_logger_and_time() -> None:
    line = formatted(record())
    assert line["message"] == "running collector"
    assert line["level"] == "INFO"
    assert line["logger"] == "meter.ingest.worker"
    assert str(line["at"]).endswith("+00:00")


def test_a_callers_fields_become_keys() -> None:
    line = formatted(record(collector="quotas", scope_key="aws:111111111111:eu-west-1"))
    assert line["collector"] == "quotas"
    assert line["scope_key"] == "aws:111111111111:eu-west-1"


def test_a_field_named_like_the_records_own_does_not_replace_it() -> None:
    assert formatted(record(level="spoofed"))["level"] == "INFO"


def test_a_traceback_is_kept() -> None:
    try:
        raise RuntimeError("a bug in a collector")
    except RuntimeError:
        failed = logging.makeLogRecord({"msg": "failed", "exc_info": sys.exc_info()})
    assert "RuntimeError: a bug in a collector" in str(formatted(failed)["exception"])


def test_a_value_json_cannot_hold_is_written_as_text() -> None:
    assert str(formatted(record(window=object()))["window"]).startswith("<object")


def test_configure_writes_json_lines(capsys: pytest.CaptureFixture[str]) -> None:
    configure("INFO")
    try:
        logging.getLogger("meter.test").info("dispatch finished", extra={"published": 3})
        line = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    finally:
        logging.basicConfig(force=True, handlers=[logging.NullHandler()])
    assert (line["message"], line["published"]) == ("dispatch finished", 3)
