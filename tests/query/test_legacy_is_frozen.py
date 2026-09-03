"""The prototype copy is not edited, and this is what says so.

`finops_query/_legacy/` is excluded from ruff and from mypy, because 44 lint
findings and 290 type errors in an unmodified prototype are a description of the
prototype rather than a list of work. The cost of those exclusions is that
nothing else in the build would notice the file being changed, and a golden file
regenerated alongside an edit would hide it too.

So the file is pinned by its hash. When TASK-P2-003 deletes the directory, this
test goes with it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

LEGACY = Path(__file__).resolve().parents[2] / "finops_query" / "_legacy" / "sample_lambda.py"

#: The file as it arrived in publicsampledashboard.zip, imported 2026-09-02.
EXPECTED_SHA256 = "80854e42cf588d2bf286262cca68c510e4bdd656efdc0fd2a8de182f28ea6f68"
EXPECTED_LINES = 2740


def test_the_prototype_copy_is_byte_identical_to_the_one_that_arrived() -> None:
    """A baseline that already contains your fixes is not a baseline."""
    digest = hashlib.sha256(LEGACY.read_bytes()).hexdigest()

    assert digest == EXPECTED_SHA256, (
        "finops_query/_legacy/sample_lambda.py has been edited. It is the "
        "baseline the golden files were taken from and it is not changed. "
        "Record what looks wrong as an ISS entry and fix it in a later task, "
        "where the golden file change is visible in the diff."
    )


def test_the_copy_is_the_size_it_was() -> None:
    """A second, weaker check that reads in a failure message. The hash says
    something changed; this says how much."""
    assert len(LEGACY.read_text(encoding="utf-8").splitlines()) == EXPECTED_LINES
