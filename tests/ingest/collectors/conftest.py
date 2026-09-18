"""Shared fixtures for the collector suites.

One thing lives here, and it is here rather than in each module because two
copies of a teardown is two places it can drift, and this one is the difference
between a green suite and a suite that measures the order pytest happened to
run its files in.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

#: The tables `partitions.py` manages. Partitions on them are not tenant
#: scoped, so every test in the run shares them.
PARTITIONED = ("cost_focus_daily", "cost_provider_extra")


@pytest.fixture(scope="module")
def partition_sandbox(engine: Engine) -> Iterator[None]:
    """Leave the partitions as the module found them.

    `test_maintenance_creates_the_months_and_is_then_a_no_op` in the retention
    suite asserts an exact count of the partitions it creates. A module that
    creates partitions for the months a fake estate bills in, and leaves them
    behind, makes that assertion pass or fail depending on which file pytest
    reached first. That is a test measuring the ordering rather than the code,
    and it is how the cost collector's first suite broke two retention tests.

    Only partitions the module added are removed, by difference against a
    snapshot taken before it ran, and only ever inside the throwaway container
    the `engine` fixture starts.
    """
    from finops_ingest.collectors.partitions import existing_partitions

    with engine.connect() as connection:
        before = {parent: set(existing_partitions(connection, parent)) for parent in PARTITIONED}
    yield
    with engine.begin() as connection:
        for parent, names in before.items():
            for name in set(existing_partitions(connection, parent)) - names:
                connection.execute(text(f"DROP TABLE IF EXISTS {name}"))
