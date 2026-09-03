"""Running the prototype without AWS, and without a clock.

Two things make the prototype's analysis path deterministic, and both are its
own switches rather than anything added to it.

`measure_ingestion` false stops `get_log_group_ingest_gb_per_hour` from calling
CloudWatch and makes it return the configured fallback. That is the only AWS
call reachable from `analyze_dashboard` or `analyze_alert_rules`, which is why
these two functions can be pinned at all and the rest of the file cannot.

`load_config` reads about forty environment variables, so the environment is set
explicitly here rather than inherited. A golden file that depends on the shell
it was generated in is not a baseline, it is a description of one machine.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

#: Every variable the analysis path reads, pinned. Prices and assumptions are
#: the prototype's own defaults, written out so a change to a default is visible
#: in the diff of this file rather than only in the goldens.
FIXED_ENVIRONMENT: dict[str, str] = {
    "AWS_REGION": "eu-west-1",
    "REGIONS": "eu-west-1",
    "GRAFANA_ACCOUNTS": "",
    # The two switches that keep this offline.
    "MEASURE_INGESTION": "false",
    "MEASURE_EXECUTIONS": "false",
    "MEASURE_LOGS_HISTORY": "false",
    # Cost model inputs.
    "VIEWING_HOURS_PER_DAY": "2.0",
    "MANUAL_LOADS_PER_DAY": "4.0",
    "METRICS_PER_CALL": "1.0",
    "DEFAULT_INGEST_GB_PER_DAY": "50.0",
    "ASSUMED_QUERY_SECONDS": "5.0",
    "LOGS_SCAN_PRICE_PER_GB": "0.005",
    "METRICS_PRICE_PER_1000": "0.01",
    # Severity thresholds.
    "REFRESH_WARN_SECONDS": "60",
    "REFRESH_CRIT_SECONDS": "30",
    "TIMERANGE_WARN_HOURS": "24",
    "TIMERANGE_CRIT_HOURS": "168",
    # Delivery, all off. Nothing here should reach S3 or SNS.
    "S3_BUCKET": "",
    "SNS_TOPIC_ARN": "",
    "BILLING_ENABLED": "false",
    "CAPACITY_ENABLED": "false",
    "HISTORY_ENABLED": "false",
}

REGION = "eu-west-1"


@pytest.fixture(scope="session")
def legacy() -> ModuleType:
    """The prototype, imported once.

    Imported rather than exec'd so that a syntax error in the copy is a loud
    import failure, and so the module is the same object every test sees.
    """
    return importlib.import_module("finops_query._legacy.sample_lambda")


@pytest.fixture
def cfg(legacy: ModuleType, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The prototype's own config, built from a pinned environment."""
    for key in list(os.environ):
        if key.startswith(("GRAFANA_", "MEASURE_", "QUOTA_", "TREND_")):
            monkeypatch.delenv(key, raising=False)
    for key, value in FIXED_ENVIRONMENT.items():
        monkeypatch.setenv(key, value)
    return legacy.load_config()


@pytest.fixture
def ingest_cache() -> Iterator[dict[tuple[str, str], float]]:
    """Empty per test. A cache shared across tests would make the order matter."""
    yield {}
