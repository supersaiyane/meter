"""What the P2 tests are given, now that the prototype is gone.

Until TASK-P2-003 this file built the prototype's own config dict and imported
its module. Both are deleted, and the replacement is the thing that had to be
true for the deletion to be safe: the golden files reproduce from `Settings`,
which is where every rate now lives, rather than from a dict of literals.

`Rates` is built from the same `settings` fixture the rest of the suite uses,
which is itself built from `.env.example`. So a value changed in `.env.example`
and not in the code fails here, and a golden file that only reproduces under
one developer's environment cannot exist.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from finops_core.config import Settings
from finops_query.cost_model import IngestRate, Rates

REGION = "eu-west-1"


@pytest.fixture
def rates(settings: Settings) -> Rates:
    """Every price and threshold, from the documented environment."""
    return Rates.from_settings(settings)


@pytest.fixture
def fallback_ingest(rates: Rates) -> IngestRate:
    """Ingestion when it cannot be measured, which is what the goldens record.

    The prototype fell back to `default_ingest_gb_per_day / 24` whenever
    `measure_ingestion` was off, and every golden file was generated that way.
    Passing it as a function is what lets the whole model run with no CloudWatch
    client anywhere near it.
    """

    def rate(region: str, log_group: str) -> float:  # noqa: ARG001
        return rates.default_ingest_gb_per_day / 24.0

    return rate


@pytest.fixture
def ingest_cache() -> Iterator[dict[tuple[str, str], float]]:
    """Empty per test. A shared cache would make the order matter."""
    yield {}
