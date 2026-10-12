"""The dispatcher and the worker, run as the processes they are. TASK-P12-004, FEAT-079.

Each module is started the way its container starts it, `python -m`, in a directory and an
environment holding nothing of this checkout's, so what is tested is the entry point and not a
fixture standing in for it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from finops_ingest.processes import EXIT_CONFIGURATION

ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINTS = (
    "finops_ingest.dispatcher",
    "finops_ingest.worker",
    "finops_fakes.dispatcher",
    "finops_fakes.worker",
)


def run(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=cwd,
        env={"PATH": os.environ["PATH"], "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize("module", ENTRY_POINTS)
def test_a_process_with_incomplete_settings_refuses_to_start_naming_what_is_missing(
    module: str, tmp_path: Path
) -> None:
    result = run(["-m", module], tmp_path)
    assert result.returncode == EXIT_CONFIGURATION, result.stderr
    assert "cannot start" in result.stderr
    assert "METER_DATABASE_URL" in result.stderr
    assert "METER_QUEUE_URL" in result.stderr


def test_a_deployed_process_never_loads_a_fake(tmp_path: Path) -> None:
    code = (
        "import sys, finops_ingest.processes, finops_ingest.dispatcher, finops_ingest.worker;"
        "print(sorted(m for m in sys.modules if m.startswith('finops_fakes')))"
    )
    result = run(["-c", code], tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
