"""The restore drill's guard, and the shape of what it restores. TASK-P0-028.

The drill creates and drops databases. Everything in it is tidiness except the
refusal to run against anything that is not local, and that refusal is tested
here the way `seed_demo`'s is, for the same reason: a tool like this ends up
pointed somewhere it should not be.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Loaded by path, because `scripts/` deliberately is not a package. See
# tests/scripts/test_seed_demo.py.
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "restore_drill.py"
_spec = importlib.util.spec_from_file_location("restore_drill", SCRIPT)
assert _spec is not None and _spec.loader is not None
restore_drill = importlib.util.module_from_spec(_spec)
sys.modules["restore_drill"] = restore_drill
_spec.loader.exec_module(restore_drill)

REMOTE = "postgresql+psycopg://meter:secret@meter-prod.eu-west-2.rds.amazonaws.com:5432/meter"
LOCAL = "postgresql+psycopg://meter:meter_local_only@localhost:5432/meter"


class TestItRefusesAnythingNotLocal:
    def test_a_remote_host_is_refused(self) -> None:
        with pytest.raises(restore_drill.NotLocalError):
            restore_drill.require_local(REMOTE)

    def test_every_local_host_is_allowed(self) -> None:
        for host in sorted(restore_drill.LOCAL_HOSTS - {""}):
            restore_drill.require_local(f"postgresql+psycopg://meter:x@{host}:5432/meter")

    def test_the_refusal_names_the_host_it_refused(self) -> None:
        # An operator who typed the wrong thing needs to see what was read, not
        # that something was wrong.
        with pytest.raises(restore_drill.NotLocalError, match="meter-prod"):
            restore_drill.require_local(REMOTE)


def test_a_scratch_database_is_never_the_source() -> None:
    """The drill restores beside the database it copied, never over it.

    A restore that overwrites its own source cannot be undone if the copy turns
    out to be the problem, which is the moment a restore is most likely to be
    running.
    """
    scratch = restore_drill.with_database(LOCAL, "meter_restore_drill_20260101000000")
    assert scratch.endswith("/meter_restore_drill_20260101000000")
    assert scratch != LOCAL
    assert scratch.startswith("postgresql+psycopg://meter:meter_local_only@localhost:5432/")


def test_the_scratch_name_is_recognisable_as_one() -> None:
    # A database found months later should identify itself without a lookup.
    assert restore_drill.SCRATCH_PREFIX.startswith("meter_restore_drill")


def test_psql_directives_are_dropped_rather_than_sent_to_the_server() -> None:
    """`\\connect` and friends are psql commands, not SQL.

    Sending one to the server produces a syntax error that reads like a corrupt
    dump, which is a bad half hour for whoever is running a restore at the time.
    """
    dump = "\n".join(
        [
            "-- a comment",
            "\\connect meter",
            "CREATE TABLE thing (id int);",
            "INSERT INTO thing VALUES (1);",
        ]
    )
    statements = restore_drill._statements(dump)
    assert any("CREATE TABLE thing" in statement for statement in statements)
    assert not any("\\connect" in statement for statement in statements)
    assert not any(statement.startswith("--") for statement in statements)
