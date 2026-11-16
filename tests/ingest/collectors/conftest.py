"""Settings for the collector tests, built from the documented environment."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from finops_core.config import Settings, load_settings

ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
VARIABLE = re.compile(r"^(METER_[A-Z0-9_]+)=(.*)$", re.MULTILINE)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for key, value in VARIABLE.findall(ENV_EXAMPLE.read_text(encoding="utf-8")):
        monkeypatch.setenv(key, value)
    return load_settings()
