"""The evaluation sets create the fake bill's month, so they give it back.

See `partition_sandbox` in `tests/conftest.py` for why that matters.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """Every set module seeds a partition, and leftovers change what other suites count."""


@pytest.fixture(autouse=True)
def _split_gap(clear_split_gap: None) -> None:
    """A bill seeded with no split data records the gap, and the gap blocks a downgrade."""
