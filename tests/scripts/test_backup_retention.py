"""The backup window held against the table policy. TASK-P0-032.

A backup held longer than the table policy holds data that policy says was
removed, which quietly undoes the policy: an erasure request is honoured in the
tables and the same rows come back with the next restore.

The two numbers live in different files and neither is executed by anything in
this repository, so nothing else would notice them drifting apart. This is the
only thing that would, and it is a test rather than a convention for the reason
CLAUDE.md constraint 11 gives about invariants.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VARIABLES = ROOT / "infra" / "terraform" / "hub" / "variables.tf"
ENVIRONMENT = ROOT / ".env.example"

#: AWS will not hold an automated backup longer than this, whatever anybody
#: writes in the variable. It is stated here so the test explains a failure at
#: 36 rather than just refusing it.
AWS_MAXIMUM_DAYS = 35


def terraform_default(name: str) -> int:
    """The default of one Terraform variable, read from the source.

    By text rather than by running Terraform, because this test has to run in a
    pipeline that has no AWS credentials and no state, which is every pipeline
    this repository has ever had.
    """
    block = re.search(
        rf'variable "{name}"\s*{{(.+?)\n}}', VARIABLES.read_text(encoding="utf-8"), re.S
    )
    assert block, f"no variable {name} in {VARIABLES.name}"
    default = re.search(r"^\s*default\s*=\s*(\d+)", block.group(1), re.M)
    assert default, f"variable {name} has no numeric default"
    return int(default.group(1))


def retention_windows() -> dict[str, int]:
    """Every table retention window from the documented environment."""
    found: dict[str, int] = {}
    for line in ENVIRONMENT.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^METER_RETENTION_(\w+)_DAYS=(\d+)$", line.strip())
        if match:
            found[match.group(1).lower()] = int(match.group(2))
    return found


def test_the_environment_states_every_window() -> None:
    """Guards the test itself.

    A regex that stopped matching would make every assertion below pass over an
    empty set, which is the way a check like this dies without anybody noticing.
    """
    windows = retention_windows()
    assert set(windows) == {"principal", "operational", "assistant", "ai_usage", "audit", "cost"}
    assert all(days > 0 for days in windows.values())


def test_a_backup_is_never_held_longer_than_the_shortest_table_window() -> None:
    """The invariant. A backup outliving the policy undoes the policy.

    Shortest, not average: a restore brings back every table, so the window that
    matters is the first one the policy says should have been empty.
    """
    backup = terraform_default("backup_retention_days")
    shortest = min(retention_windows().values())
    assert backup <= shortest, (
        f"backups are held {backup} days and the shortest table window is "
        f"{shortest}. A restore would bring back rows the policy removed."
    )


def test_the_backup_window_is_within_what_aws_allows() -> None:
    # A default above the ceiling is not a policy decision, it is an apply that
    # fails, and nothing else here would catch it before that apply.
    assert terraform_default("backup_retention_days") <= AWS_MAXIMUM_DAYS
